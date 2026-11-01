import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.config import get_database_path, get_database_url
from app.database import initialize_database
from app.postgres_compat import connect_postgres


TRANSIENT_SESSION_TABLES = {"admin_sessions", "seller_sessions"}
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Unexpected database identifier: {value!r}")
    return f'"{value}"'


def _ordered_tables(
    source: sqlite3.Connection, table_names: list[str]
) -> tuple[list[str], dict[str, list[str]]]:
    tables = set(table_names)
    dependencies: dict[str, set[str]] = {table: set() for table in table_names}
    self_references: dict[str, list[str]] = {}
    for table in table_names:
        for foreign_key in source.execute(
            f"PRAGMA foreign_key_list({_identifier(table)})"
        ):
            parent_table = foreign_key["table"]
            if parent_table not in tables:
                continue
            if parent_table == table:
                self_references.setdefault(table, []).append(foreign_key["from"])
            else:
                dependencies[table].add(parent_table)

    ordered: list[str] = []
    remaining = set(table_names)
    while remaining:
        ready = sorted(
            table for table in remaining if not dependencies[table].intersection(remaining)
        )
        if not ready:
            raise RuntimeError(
                "The SQLite schema contains circular foreign keys between tables: "
                + ", ".join(sorted(remaining))
            )
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered, self_references


def _source_tables(source: sqlite3.Connection) -> list[str]:
    return [
        row["name"]
        for row in source.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    ]


def _target_tables(connection: Any) -> list[str]:
    return [
        row["table_name"]
        for row in connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        ).fetchall()
    ]


def _target_table_has_id(connection: Any, table_name: str) -> bool:
    return bool(
        connection.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = ? AND column_name = 'id'
            ) AS has_id
            """,
            (table_name,),
        ).fetchone()["has_id"]
    )


def _ensure_target_is_empty(connection: Any, table_names: list[str]) -> None:
    nonempty = []
    for table in table_names:
        count = connection.execute(
            f"SELECT COUNT(*) AS row_count FROM {_identifier(table)}"
        ).fetchone()["row_count"]
        if count:
            nonempty.append(f"{table} ({count})")
    if nonempty:
        raise RuntimeError(
            "The Supabase app schema is not empty. Refusing to overwrite existing "
            "data. Start with a new/empty app schema before importing. Found rows in: "
            + ", ".join(nonempty)
        )


def migrate_database(
    sqlite_path: Path, database_url: str, *, initialize_schema: bool = True
) -> dict[str, int]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    try:
        source_tables = _source_tables(source)
        tables_to_import = [
            table for table in source_tables if table not in TRANSIENT_SESSION_TABLES
        ]
        ordered_tables, self_references = _ordered_tables(source, tables_to_import)
        if initialize_schema:
            preflight = connect_postgres(database_url)
            try:
                existing_tables = set(_target_tables(preflight))
                _ensure_target_is_empty(
                    preflight,
                    sorted(existing_tables.intersection(tables_to_import)),
                )
            finally:
                preflight.close()
            os.environ["DATABASE_URL"] = database_url
            initialize_database(seed_initial_data=False)

        target = connect_postgres(database_url)
        try:
            destination_tables = set(_target_tables(target))
            missing_tables = sorted(set(tables_to_import) - destination_tables)
            if missing_tables:
                raise RuntimeError(
                    "The Supabase schema is missing tables. Initialize the backend "
                    "schema first. Missing: " + ", ".join(missing_tables)
                )
            _ensure_target_is_empty(target, sorted(set(tables_to_import)))
            counts: dict[str, int] = {}
            deferred_updates: dict[str, list[tuple[Any, Any, str]]] = {}
            try:
                for table in ordered_tables:
                    source_columns = [
                        row["name"]
                        for row in source.execute(
                            f"PRAGMA table_info({_identifier(table)})"
                        )
                    ]
                    destination_columns = {
                        row["name"]
                        for row in target.execute(
                            f"PRAGMA table_info({_identifier(table)})"
                        ).fetchall()
                    }
                    columns = [
                        name for name in source_columns if name in destination_columns
                    ]
                    deferred_columns = [
                        name
                        for name in self_references.get(table, [])
                        if name in columns
                    ]
                    inserted_columns = [
                        name for name in columns if name not in deferred_columns
                    ]
                    quoted_table = _identifier(table)
                    selected_columns = ", ".join(
                        _identifier(name) for name in source_columns
                    )
                    insert_columns = ", ".join(
                        _identifier(name) for name in inserted_columns
                    )
                    placeholders = ", ".join("?" for _ in inserted_columns)
                    insert_query = (
                        f"INSERT INTO {quoted_table} ({insert_columns}) "
                        f"VALUES ({placeholders})"
                    )
                    table_count = 0
                    deferred_updates[table] = []
                    cursor = source.execute(
                        f"SELECT {selected_columns} FROM {quoted_table}"
                    )
                    source_indexes = {
                        name: index for index, name in enumerate(source_columns)
                    }
                    id_index = source_indexes.get("id")
                    for batch in iter(lambda: cursor.fetchmany(500), []):
                        rows = []
                        for source_row in batch:
                            values = [
                                source_row[source_indexes[name]]
                                for name in inserted_columns
                            ]
                            rows.append(tuple(values))
                            if deferred_columns and id_index is not None:
                                for column in deferred_columns:
                                    reference = source_row[source_indexes[column]]
                                    if reference is not None:
                                        deferred_updates[table].append(
                                            (source_row[id_index], reference, column)
                                        )
                        if rows:
                            target.executemany(insert_query, rows)
                            table_count += len(rows)
                    counts[table] = table_count

                for table, updates in deferred_updates.items():
                    for row_id, reference, column in updates:
                        target.execute(
                            f"UPDATE {_identifier(table)} "
                            f"SET {_identifier(column)} = ? WHERE id = ?",
                            (reference, row_id),
                        )

                for table in ordered_tables:
                    if not _target_table_has_id(target, table):
                        continue
                    sequence = target.execute(
                        "SELECT pg_get_serial_sequence(?, 'id') AS sequence",
                        (table,),
                    ).fetchone()["sequence"]
                    if sequence:
                        target.execute(
                            f"""
                            SELECT setval(
                                ?::regclass,
                                COALESCE(MAX(id), 1),
                                MAX(id) IS NOT NULL
                            )
                            FROM {_identifier(table)}
                            """,
                            (sequence,),
                        )
                target.commit()
            except Exception:
                target.rollback()
                raise
            return counts
        finally:
            target.close()
    finally:
        source.close()


def _print_source_preview(sqlite_path: Path) -> None:
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    try:
        tables = _source_tables(source)
        row_count = 0
        for table in tables:
            if table in TRANSIENT_SESSION_TABLES:
                continue
            row_count += source.execute(
                f"SELECT COUNT(*) FROM {_identifier(table)}"
            ).fetchone()[0]
        print(f"SQLite source: {sqlite_path}")
        print(f"Tables found: {len(tables)}")
        print(f"Rows to migrate (excluding active sessions): {row_count}")
        print("No data has been transferred. Pass --apply to start the import.")
    finally:
        source.close()


def main() -> int:
    backend_root = Path(__file__).resolve().parents[1]
    load_dotenv(backend_root / ".env")
    parser = argparse.ArgumentParser(
        description="Copy the local Maison Muse SQLite database into an empty PostgreSQL schema."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=get_database_path(),
        help="Source SQLite database path (defaults to DATABASE_PATH).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create the PostgreSQL schema and import local records.",
    )
    arguments = parser.parse_args()
    if not arguments.apply:
        _print_source_preview(arguments.sqlite_path)
        return 0

    database_url = get_database_url()
    if not database_url:
        print(
            "DATABASE_URL is not set. Add the Supabase connection string to a local "
            "backend .env file or environment variable; do not commit it.",
            file=sys.stderr,
        )
        return 2
    counts = migrate_database(arguments.sqlite_path, database_url)
    print(f"Imported {sum(counts.values())} rows across {len(counts)} tables.")
    for table, count in sorted(counts.items()):
        if count:
            print(f"  {table}: {count}")
    print("Active admin and seller sessions were not imported; sign in again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
