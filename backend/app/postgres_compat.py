import re
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from app.data_encryption import (
    ENCRYPTED_PREFIX,
    SENSITIVE_COLUMNS_BY_TABLE,
    decrypt_result_value,
    decrypt_value,
    encrypt_write_parameters,
    phone_lookup_hash,
)


_INTERNAL_RESULT_COLUMNS = {"customer_phone_lookup_hash"}

_SQLITE_TRIGGER_PATTERN = re.compile(
    r"CREATE\s+TRIGGER\s+IF\s+NOT\s+EXISTS\s+"
    r"prevent_admin_audit_(?:update|delete)\b.*?\bEND\s*;",
    re.IGNORECASE | re.DOTALL,
)
_INSERT_TABLE_PATTERN = re.compile(
    r"^\s*INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+([a-zA-Z_][\w]*)",
    re.IGNORECASE,
)
_STRFTIME_PATTERN = re.compile(
    r"strftime\(\s*'%Y-%m-%dT%H:%M:%fZ'\s*,\s*'now'\s*\)",
    re.IGNORECASE,
)
_DATETIME_INTERVAL_PATTERN = re.compile(
    r"datetime\(\s*'now'\s*,\s*'-(\d+)\s+(day|days|hour|hours|minute|minutes)'\s*\)",
    re.IGNORECASE,
)
_JULIANDAY_DIFFERENCE_PATTERN = re.compile(
    r"julianday\(([\w.]+)\)\s*-\s*julianday\(([\w.]+)\)",
    re.IGNORECASE,
)


class PostgresRow(Mapping[str, Any]):
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = {
            key: decrypt_result_value(key, value)
            for key, value in values.items()
            if key not in _INTERNAL_RESULT_COLUMNS
        }
        self._keys = tuple(self._values)

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[self._keys[key]]
        return self._values[key]

    def __iter__(self):
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._values)

    def keys(self):
        return self._values.keys()


class PostgresCursor:
    def __init__(
        self,
        cursor: Any,
        lastrowid: Any = None,
        has_inserted_row: bool = False,
    ) -> None:
        self._cursor = cursor
        self.lastrowid = lastrowid
        self._has_inserted_row = has_inserted_row
        self.rowcount = cursor.rowcount

    def fetchone(self) -> PostgresRow | None:
        row = self._cursor.fetchone()
        return PostgresRow(row) if row is not None else None

    def fetchall(self) -> list[PostgresRow]:
        return [PostgresRow(row) for row in self._cursor.fetchall()]

    def fetchmany(self, size: int | None = None) -> list[PostgresRow]:
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        return [PostgresRow(row) for row in rows]

    def __iter__(self):
        for row in self._cursor:
            yield PostgresRow(row)


class PostgresConnection:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._tables_with_id: dict[str, bool] = {}

    def execute(
        self, query: str, parameters: Sequence[Any] | Mapping[str, Any] = ()
    ) -> PostgresCursor:
        query, parameters = self._prepare_query(query, parameters)
        parameters = encrypt_write_parameters(query, parameters)
        if not query:
            return PostgresCursor(_empty_cursor())
        try:
            cursor = (
                self._connection.execute(query)
                if not parameters
                else self._connection.execute(query, parameters)
            )
            if _returns_inserted_id(query):
                row = cursor.fetchone()
                inserted_id = row["id"] if row is not None else None
                return PostgresCursor(cursor, lastrowid=inserted_id)
            return PostgresCursor(cursor)
        except self._connection_error_types() as error:
            if self._is_integrity_error(error):
                raise sqlite3.IntegrityError(_integrity_error_message(error)) from error
            raise

    def executemany(
        self,
        query: str,
        parameters: Sequence[Sequence[Any] | Mapping[str, Any]],
    ) -> PostgresCursor:
        if not parameters:
            return PostgresCursor(_empty_cursor())
        first_parameters = parameters[0]
        if isinstance(first_parameters, Mapping):
            if not all(isinstance(row, Mapping) for row in parameters):
                raise TypeError("executemany parameters must use one consistent style")
            query, _ = self._prepare_query(
                query, first_parameters, auto_returning=False
            )
            parameter_rows = [
                encrypt_write_parameters(query, row) for row in parameters
            ]
        else:
            if any(isinstance(row, Mapping) for row in parameters):
                raise TypeError("executemany parameters must use one consistent style")
            query, _ = self._prepare_query(query, (), auto_returning=False)
            parameter_rows = [
                encrypt_write_parameters(query, tuple(row)) for row in parameters
            ]
        if not query:
            return PostgresCursor(_empty_cursor())
        try:
            cursor = self._connection.cursor()
            cursor.executemany(query, parameter_rows)
            return PostgresCursor(cursor)
        except self._connection_error_types() as error:
            if self._is_integrity_error(error):
                raise sqlite3.IntegrityError(_integrity_error_message(error)) from error
            raise

    def encrypt_existing_sensitive_data(self) -> None:
        # Verify the key before touching records; startup must fail closed if absent.
        from app.data_encryption import encrypt_value

        encrypt_value("__key_check__")
        for table, sensitive_columns in SENSITIVE_COLUMNS_BY_TABLE.items():
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = %s
                    """,
                    (table,),
                )
                existing_columns = {row["column_name"] for row in cursor.fetchall()}
            for column in sorted(sensitive_columns.intersection(existing_columns)):
                while True:
                    with self._connection.cursor() as cursor:
                        cursor.execute(
                            f"""
                            SELECT ctid::text AS row_locator, "{column}"
                            FROM "{table}"
                            WHERE "{column}" IS NOT NULL
                              AND "{column}" <> ''
                              AND "{column}" NOT LIKE %s
                            LIMIT 500
                            """,
                            (f"{ENCRYPTED_PREFIX}%",),
                        )
                        rows = cursor.fetchall()
                    if not rows:
                        break
                    self.executemany(
                        f'UPDATE "{table}" SET "{column}" = ? WHERE ctid = ?::tid',
                        [
                            (row[column], row["row_locator"])
                            for row in rows
                        ],
                    )
        while True:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ctid::text AS row_locator, customer_phone
                    FROM orders
                    WHERE customer_phone <> ''
                      AND customer_phone_lookup_hash = ''
                    LIMIT 500
                    """
                )
                rows = cursor.fetchall()
            if not rows:
                break
            self.executemany(
                """
                UPDATE orders
                SET customer_phone_lookup_hash = ?
                WHERE ctid = ?::tid
                """,
                [
                    (
                        phone_lookup_hash(decrypt_value(row["customer_phone"])),
                        row["row_locator"],
                    )
                    for row in rows
                ],
            )

    def executescript(self, script: str) -> None:
        script, trigger_found = _remove_sqlite_triggers(script)
        statements = [statement for statement in script.split(";") if statement.strip()]
        table_statements, other_statements = _order_create_table_statements(statements)
        for statement in (*table_statements, *other_statements):
            self.execute(statement)
        self.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_casefold "
            "ON users (LOWER(email))"
        )
        self.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_seller_team_email_casefold "
            "ON seller_team_members (seller_id, LOWER(email))"
        )
        if trigger_found:
            self.execute(
                """
                CREATE OR REPLACE FUNCTION prevent_admin_audit_mutation()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'Admin audit logs are immutable.';
                END;
                $$
                """
            )
            for operation in ("UPDATE", "DELETE"):
                name = f"prevent_admin_audit_{operation.casefold()}"
                self.execute(f"DROP TRIGGER IF EXISTS {name} ON admin_audit_logs")
                self.execute(
                    f"""
                    CREATE TRIGGER {name}
                    BEFORE {operation} ON admin_audit_logs
                    FOR EACH ROW EXECUTE FUNCTION prevent_admin_audit_mutation()
                    """
                )

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def _prepare_query(
        self,
        query: str,
        parameters: Sequence[Any] | Mapping[str, Any],
        *,
        auto_returning: bool = True,
    ) -> tuple[str, Sequence[Any] | Mapping[str, Any]]:
        query = query.strip().rstrip(";")
        pragma_match = re.fullmatch(
            r"PRAGMA\s+(?:\w+\s*=\s*\w+|legacy_alter_table\s*=\s*\w+)",
            query,
            re.IGNORECASE,
        )
        if pragma_match:
            return "", ()

        table_info_match = re.fullmatch(
            r"PRAGMA\s+table_info\((['\"]?[\w]+['\"]?)\)", query, re.IGNORECASE
        )
        if table_info_match:
            table_name = table_info_match.group(1).strip("'\"")
            query = """
                SELECT column_name AS name
                FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = %s
                ORDER BY ordinal_position
            """
            return query, (table_name.casefold(),)

        if "FROM sqlite_master" in query:
            if parameters:
                table_name = parameters[-1]
            else:
                name_match = re.search(
                    r"\bname\s*=\s*'([^']+)'", query, re.IGNORECASE
                )
                table_name = name_match.group(1) if name_match else ""
            query = """
                SELECT COALESCE(string_agg(pg_get_constraintdef(c.oid), ' '), '')
                       AS sql
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = current_schema() AND t.relname = %s
            """
            return query, (str(table_name).casefold(),)

        query = _rewrite_sql(query)
        if isinstance(parameters, Mapping):
            query = re.sub(r"(?<!:):([a-zA-Z_]\w*)", r"%(\1)s", query)
            return query, parameters
        parameters = tuple(parameters)
        query = _replace_qmark_placeholders(query)

        insert_match = _INSERT_TABLE_PATTERN.match(query)
        if auto_returning and insert_match and "RETURNING" not in query.upper():
            table_name = insert_match.group(1).casefold()
            if self._table_has_id(table_name):
                query = f"{query} RETURNING id"
        return query, parameters

    def _table_has_id(self, table_name: str) -> bool:
        if table_name not in self._tables_with_id:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = %s AND column_name = 'id'
                    ) AS has_id
                    """,
                    (table_name,),
                )
                self._tables_with_id[table_name] = cursor.fetchone()["has_id"]
        return self._tables_with_id[table_name]

    def _connection_error_types(self) -> tuple[type[BaseException], ...]:
        import psycopg

        return (psycopg.Error,)

    def _is_integrity_error(self, error: BaseException) -> bool:
        import psycopg

        return isinstance(error, psycopg.IntegrityError)


def connect_postgres(database_url: str) -> PostgresConnection:
    import psycopg
    from psycopg.rows import dict_row

    database_url = normalize_database_url(database_url)
    connection = psycopg.connect(
        database_url,
        row_factory=dict_row,
        prepare_threshold=None,
        connect_timeout=10,
    )
    return PostgresConnection(connection)


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url.removeprefix("postgres://")
    if "sslmode=" not in database_url and "localhost" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"
    return database_url


def _integrity_error_message(error: BaseException) -> str:
    import psycopg

    constraint_name = getattr(getattr(error, "diag", None), "constraint_name", None)
    if isinstance(error, psycopg.errors.UniqueViolation):
        return f"UNIQUE constraint failed: {constraint_name or 'unknown constraint'}"
    if isinstance(error, psycopg.errors.ForeignKeyViolation):
        return f"FOREIGN KEY constraint failed: {constraint_name or 'unknown constraint'}"
    if isinstance(error, psycopg.errors.CheckViolation):
        return f"CHECK constraint failed: {constraint_name or 'unknown constraint'}"
    if isinstance(error, psycopg.errors.NotNullViolation):
        return f"NOT NULL constraint failed: {constraint_name or 'unknown constraint'}"
    return str(error)


def _rewrite_sql(query: str) -> str:
    query = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\bINTEGER\b", "BIGINT", query, flags=re.IGNORECASE)
    query = re.sub(r"\bREAL\b", "DOUBLE PRECISION", query, flags=re.IGNORECASE)
    query = _STRFTIME_PATTERN.sub(
        """to_char(timezone('UTC', now()), 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')""",
        query,
    )
    query = _DATETIME_INTERVAL_PATTERN.sub(
        lambda match: f"NOW() - INTERVAL '{match.group(1)} {match.group(2)}'",
        query,
    )
    query = _JULIANDAY_DIFFERENCE_PATTERN.sub(
        lambda match: (
            "EXTRACT(EPOCH FROM ("
            f"{match.group(1)}::timestamptz - {match.group(2)}::timestamptz"
            ")) / 86400.0"
        ),
        query,
    )
    query = re.sub(
        r"\b((?:\w+\.)?email)\s*=\s*(\?)",
        r"LOWER(\1) = LOWER(\2)",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"(?<![\w.])((?:\w+\.)?\w+)\s+LIKE\s+(\?)\s+COLLATE\s+NOCASE",
        r"\1 ILIKE \2",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"((?:\w+\.)?\w+)\s*=\s*(\?|(?:\w+\.)?\w+)\s+COLLATE\s+NOCASE",
        r"LOWER(\1) = LOWER(\2)",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"((?:\w+\.)?\w+)\s+LIKE\s+'([^']*)'\s+COLLATE\s+NOCASE",
        r"\1 ILIKE '\2'",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\s+COLLATE\s+NOCASE\b", "", query, flags=re.IGNORECASE)
    query = re.sub(
        r"((?:\w+\.)?created_at)\s*>=\s*(NOW\(\)\s*-\s*INTERVAL\s+'[^']+')",
        r"\1::timestamptz >= \2",
        query,
        flags=re.IGNORECASE,
    )
    if re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO\b", query, re.IGNORECASE):
        query = re.sub(
            r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
            "INSERT INTO",
            query,
            count=1,
            flags=re.IGNORECASE,
        )
        if "ON CONFLICT" not in query.upper():
            query += " ON CONFLICT DO NOTHING"
    if re.match(r"\s*BEGIN\s+IMMEDIATE\b", query, re.IGNORECASE):
        query = re.sub(r"BEGIN\s+IMMEDIATE", "BEGIN", query, count=1, flags=re.IGNORECASE)
    query = re.sub(r"\browid\b", "id", query, flags=re.IGNORECASE)
    return query


def _replace_qmark_placeholders(query: str) -> str:
    if "?" not in query:
        return query
    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(query):
        character = query[index]
        if quote:
            if character == "%":
                result.append("%%")
            else:
                result.append(character)
            if character == quote:
                if index + 1 < len(query) and query[index + 1] == quote:
                    result.append(query[index + 1])
                    index += 1
                else:
                    quote = None
        elif character in {"'", '"'}:
            quote = character
            result.append(character)
        elif character == "?":
            result.append("%s")
        elif character == "%":
            result.append("%%")
        else:
            result.append(character)
        index += 1
    return "".join(result)


def _returns_inserted_id(query: str) -> bool:
    return bool(
        _INSERT_TABLE_PATTERN.match(query)
        and re.search(r"\bRETURNING\s+id\b", query, re.IGNORECASE)
    )


def _remove_sqlite_triggers(script: str) -> tuple[str, bool]:
    cleaned, count = _SQLITE_TRIGGER_PATTERN.subn("", script)
    return cleaned, count > 0


def _order_create_table_statements(
    statements: Sequence[str],
) -> tuple[list[str], list[str]]:
    create_table_pattern = re.compile(
        r"^\s*CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_]\w*)",
        re.IGNORECASE,
    )
    references_pattern = re.compile(
        r"\bREFERENCES\s+([a-zA-Z_]\w*)\s*\(",
        re.IGNORECASE,
    )
    table_statements: dict[str, str] = {}
    other_statements: list[str] = []
    for statement in statements:
        match = create_table_pattern.match(statement)
        if match:
            table_statements[match.group(1).casefold()] = statement
        else:
            other_statements.append(statement)

    dependencies = {
        table: {
            reference.casefold()
            for reference in references_pattern.findall(statement)
            if reference.casefold() in table_statements
            and reference.casefold() != table
        }
        for table, statement in table_statements.items()
    }
    ordered_tables: list[str] = []
    remaining = set(table_statements)
    while remaining:
        ready = sorted(
            table for table in remaining if not dependencies[table].intersection(remaining)
        )
        if not ready:
            raise RuntimeError(
                "PostgreSQL table creation has circular foreign-key dependencies: "
                + ", ".join(sorted(remaining))
            )
        ordered_tables.extend(ready)
        remaining.difference_update(ready)
    return [table_statements[table] for table in ordered_tables], other_statements


class _EmptyCursor:
    rowcount = -1

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def fetchmany(self, size: int | None = None):
        return []

    def __iter__(self):
        return iter(())


def _empty_cursor() -> _EmptyCursor:
    return _EmptyCursor()
