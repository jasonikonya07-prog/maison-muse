import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app.database import initialize_database
from app.data_encryption import (
    ENCRYPTED_PREFIX,
    _fernet_for_key,
    decrypt_result_value,
    decrypt_value,
    encrypt_value,
    encrypt_write_parameters,
    phone_lookup_hash,
)
from app.migrate_sqlite_to_postgres import (
    _ordered_tables,
    _target_table_has_id,
)
from app.postgres_compat import (
    PostgresConnection,
    PostgresRow,
    _order_create_table_statements,
    _remove_sqlite_triggers,
    _replace_qmark_placeholders,
    _rewrite_sql,
)


class PostgresCompatibilityTests(unittest.TestCase):
    def test_rewrites_sqlite_schema_types_and_timestamps(self) -> None:
        query = _rewrite_sql(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                commission REAL NOT NULL DEFAULT 10,
                created_at TEXT NOT NULL DEFAULT
                    (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        self.assertIn("id BIGSERIAL PRIMARY KEY", query)
        self.assertIn("commission DOUBLE PRECISION", query)
        self.assertNotIn("COLLATE NOCASE", query)
        self.assertIn("email TEXT NOT NULL UNIQUE", query)
        self.assertNotIn("LOWER(UNIQUE)", query)
        self.assertIn("to_char(timezone('UTC', now())", query)

    def test_sqlite_trigger_removal_preserves_other_schema_statements(self) -> None:
        schema, trigger_found = _remove_sqlite_triggers(
            """
            CREATE TABLE admin_audit_logs (id INTEGER PRIMARY KEY);
            CREATE TRIGGER IF NOT EXISTS prevent_admin_audit_update
            BEFORE UPDATE ON admin_audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'Admin audit logs are immutable.');
            END;
            CREATE TABLE store_settings (key TEXT PRIMARY KEY);
            """
        )
        self.assertTrue(trigger_found)
        self.assertIn("CREATE TABLE admin_audit_logs", schema)
        self.assertIn("CREATE TABLE store_settings", schema)
        self.assertNotIn("CREATE TRIGGER", schema)

    def test_create_tables_are_ordered_before_foreign_key_dependents(self) -> None:
        statements = [
            "CREATE TABLE IF NOT EXISTS child (id INTEGER, parent_id INTEGER REFERENCES parent(id))",
            "CREATE INDEX IF NOT EXISTS idx_child_parent ON child(parent_id)",
            "CREATE TABLE IF NOT EXISTS parent (id INTEGER PRIMARY KEY AUTOINCREMENT)",
        ]
        tables, other = _order_create_table_statements(statements)
        self.assertIn("CREATE TABLE IF NOT EXISTS parent", tables[0])
        self.assertIn("CREATE TABLE IF NOT EXISTS child", tables[1])
        self.assertEqual(other, [statements[1]])

    def test_rewrites_case_insensitive_queries_and_sqlite_dates(self) -> None:
        query = _rewrite_sql(
            """
            SELECT * FROM users
            WHERE email = ? COLLATE NOCASE
              AND created_at >= datetime('now', '-7 days')
              AND name LIKE ? COLLATE NOCASE
            """
        )
        self.assertIn("LOWER(email) = LOWER(?)", query)
        self.assertIn("created_at::timestamptz >= NOW() - INTERVAL '7 days'", query)
        self.assertIn("name ILIKE ?", query)

    def test_translates_sqlite_insert_ignore_and_placeholders(self) -> None:
        query = _rewrite_sql("INSERT OR IGNORE INTO users (email) VALUES (?)")
        self.assertEqual(
            _replace_qmark_placeholders(query),
            "INSERT INTO users (email) VALUES (%s) ON CONFLICT DO NOTHING",
        )

    def test_qmark_placeholder_conversion_preserves_quoted_questions(self) -> None:
        query = _replace_qmark_placeholders(
            "SELECT '?' AS literal, value FROM settings WHERE name = ? AND note = '%done%'"
        )
        self.assertEqual(
            query,
            "SELECT '?' AS literal, value FROM settings WHERE name = %s AND note = '%%done%%'",
        )

    def test_named_placeholders_are_converted_for_postgres(self) -> None:
        connection = PostgresConnection.__new__(PostgresConnection)
        query, parameters = connection._prepare_query(
            "UPDATE products SET name = :name WHERE id = :product_id",
            {"name": "New product", "product_id": "p-1"},
        )
        self.assertEqual(
            query,
            "UPDATE products SET name = %(name)s WHERE id = %(product_id)s",
        )
        self.assertEqual(parameters, {"name": "New product", "product_id": "p-1"})

    def test_sensitive_values_are_encrypted_and_decrypted(self) -> None:
        key = "zB5k-3YxYqBUh5Vwx6rmmttjZeox8K0h36YG49hhMtQ="
        _fernet_for_key.cache_clear()
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": key}):
            encrypted = encrypt_value("+254700000000")
            self.assertTrue(encrypted.startswith(ENCRYPTED_PREFIX))
            self.assertNotIn("+254700000000", encrypted)
            self.assertEqual(decrypt_value(encrypted), "+254700000000")
            self.assertEqual(decrypt_result_value("customer_phone", encrypted), "+254700000000")
            self.assertEqual(encrypt_value(encrypted), encrypted)
            self.assertEqual(encrypt_value(""), "")
        _fernet_for_key.cache_clear()

    def test_sensitive_insert_parameters_are_encrypted_by_column(self) -> None:
        key = "zB5k-3YxYqBUh5Vwx6rmmttjZeox8K0h36YG49hhMtQ="
        _fernet_for_key.cache_clear()
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": key}):
            values = encrypt_write_parameters(
                "INSERT INTO orders (order_number, customer_phone, delivery_address) "
                "VALUES (%s, %s, %s)",
                ("MM-1", "+254700000000", "Nairobi"),
            )
            self.assertEqual(values[0], "MM-1")
            self.assertEqual(decrypt_value(values[1]), "+254700000000")
            self.assertEqual(decrypt_value(values[2]), "Nairobi")
        _fernet_for_key.cache_clear()

    def test_sensitive_named_insert_parameters_are_encrypted(self) -> None:
        key = "zB5k-3YxYqBUh5Vwx6rmmttjZeox8K0h36YG49hhMtQ="
        _fernet_for_key.cache_clear()
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": key}):
            values = encrypt_write_parameters(
                "INSERT INTO sellers (store_name, payout_account) "
                "VALUES (%(store_name)s, %(payout_account)s)",
                {"store_name": "Boutique", "payout_account": "123456789"},
            )
            self.assertEqual(values["store_name"], "Boutique")
            self.assertEqual(decrypt_value(values["payout_account"]), "123456789")
        _fernet_for_key.cache_clear()

    def test_sensitive_update_parameter_is_encrypted(self) -> None:
        key = "zB5k-3YxYqBUh5Vwx6rmmttjZeox8K0h36YG49hhMtQ="
        _fernet_for_key.cache_clear()
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": key}):
            values = encrypt_write_parameters(
                "UPDATE users SET full_name = %s, phone = %s WHERE id = %s",
                ("Jamie Rivers", "+254700000000", 4),
            )
            self.assertEqual(values[0], "Jamie Rivers")
            self.assertEqual(decrypt_value(values[1]), "+254700000000")
            self.assertEqual(values[2], 4)
        _fernet_for_key.cache_clear()

    def test_phone_lookup_hash_is_keyed_and_repeatable(self) -> None:
        key = "zB5k-3YxYqBUh5Vwx6rmmttjZeox8K0h36YG49hhMtQ="
        _fernet_for_key.cache_clear()
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": key}):
            first = phone_lookup_hash("+254700000000")
            self.assertEqual(first, phone_lookup_hash("+254700000000"))
            self.assertNotEqual(first, phone_lookup_hash("+254700000001"))
            self.assertNotIn("+254700000000", first)
        _fernet_for_key.cache_clear()

    def test_sqlite_master_lookups_keep_hard_coded_table_name(self) -> None:
        connection = PostgresConnection.__new__(PostgresConnection)
        query, parameters = connection._prepare_query(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'",
            (),
        )
        self.assertIn("pg_constraint", query)
        self.assertEqual(parameters, ("users",))

    def test_executemany_does_not_add_returning_clause(self) -> None:
        connection = PostgresConnection.__new__(PostgresConnection)
        query, _ = connection._prepare_query(
            "INSERT INTO users (email) VALUES (?)", (), auto_returning=False
        )
        self.assertEqual(query, "INSERT INTO users (email) VALUES (%s)")

    def test_executemany_converts_named_parameters(self) -> None:
        class FakeCursor:
            rowcount = 2

            def executemany(self, query, parameters):
                self.query = query
                self.parameters = parameters

        class FakeConnection:
            def __init__(self):
                self.cursor_instance = FakeCursor()

            def cursor(self):
                return self.cursor_instance

        connection = PostgresConnection.__new__(PostgresConnection)
        connection._connection = FakeConnection()
        rows = [{"id": "p-1"}, {"id": "p-2"}]

        connection.executemany(
            "INSERT INTO products (id) VALUES (:id)", rows
        )

        self.assertEqual(
            connection._connection.cursor_instance.query,
            "INSERT INTO products (id) VALUES (%(id)s)",
        )
        self.assertEqual(
            connection._connection.cursor_instance.parameters,
            rows,
        )

    def test_row_supports_sqlite_name_index_and_mapping_access(self) -> None:
        row = PostgresRow({"id": 7, "name": "Maison"})
        self.assertEqual(row["name"], "Maison")
        self.assertEqual(row[0], 7)
        self.assertEqual(dict(row), {"id": 7, "name": "Maison"})

    def test_row_does_not_expose_internal_phone_lookup_hash(self) -> None:
        row = PostgresRow(
            {"id": 7, "customer_phone_lookup_hash": "private-index", "status": "paid"}
        )
        self.assertNotIn("customer_phone_lookup_hash", row)
        self.assertEqual(dict(row), {"id": 7, "status": "paid"})

    def test_migration_schema_creation_does_not_seed_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "empty.sqlite3"
            with patch.dict(
                os.environ,
                {"DATABASE_URL": "", "DATABASE_PATH": str(database_path)},
            ):
                initialize_database(seed_initial_data=False)
            with closing(sqlite3.connect(database_path)) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM products").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM admin_role_permissions"
                    ).fetchone()[0],
                    0,
                )

    def test_migration_orders_foreign_keys_and_defers_self_references(self) -> None:
        source = sqlite3.connect(":memory:")
        source.row_factory = sqlite3.Row
        source.executescript(
            """
            CREATE TABLE parents (id INTEGER PRIMARY KEY);
            CREATE TABLE children (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER REFERENCES parents(id)
            );
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER REFERENCES categories(id)
            );
            """
        )
        try:
            tables = ["children", "categories", "parents"]
            ordered, self_references = _ordered_tables(source, tables)
            self.assertLess(ordered.index("parents"), ordered.index("children"))
            self.assertEqual(self_references["categories"], ["parent_id"])
        finally:
            source.close()

    def test_sequence_reset_checks_for_an_id_column_first(self) -> None:
        class FakeConnection:
            query = ""
            parameters = ()

            def execute(self, query, parameters):
                self.query = query
                self.parameters = parameters
                return type(
                    "Result",
                    (),
                    {"fetchone": lambda result: {"has_id": False}},
                )()

        connection = FakeConnection()
        self.assertFalse(_target_table_has_id(connection, "admin_role_permissions"))
        self.assertIn("information_schema.columns", connection.query)
        self.assertEqual(connection.parameters, ("admin_role_permissions",))


if __name__ == "__main__":
    unittest.main()
