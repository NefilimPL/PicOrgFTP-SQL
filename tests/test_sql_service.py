"""Unit tests for SQL metadata helpers."""

from __future__ import annotations

import unittest

from picorgftp_sql.services.sql_service import (
    build_column_detection_query,
    extract_presence_context,
)


class SqlServiceTests(unittest.TestCase):
    def test_build_column_detection_query_for_mysql_without_schema(self) -> None:
        query_info = build_column_detection_query(
            "UPDATE object_query_1 SET img = 'x' WHERE EAN = '{ean}'",
            "mysql",
        )

        self.assertIsNotNone(query_info)
        assert query_info is not None
        self.assertEqual(query_info.table_ref, "object_query_1")
        self.assertEqual(
            query_info.query,
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION",
        )
        self.assertEqual(query_info.params, ("object_query_1",))
        self.assertEqual(
            query_info.preview,
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'object_query_1' "
            "ORDER BY ORDINAL_POSITION",
        )

    def test_build_column_detection_query_for_mssql_with_schema(self) -> None:
        query_info = build_column_detection_query(
            "UPDATE [dbo].[object_query_1] SET img = 'x' WHERE EAN = '{ean}'",
            "mssql",
        )

        self.assertIsNotNone(query_info)
        assert query_info is not None
        self.assertEqual(query_info.table_ref, "dbo.object_query_1")
        self.assertEqual(query_info.schema, "dbo")
        self.assertEqual(query_info.table_name, "object_query_1")
        self.assertEqual(
            query_info.query,
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
            "ORDER BY ORDINAL_POSITION",
        )
        self.assertEqual(query_info.params, ("dbo", "object_query_1"))
        self.assertEqual(
            query_info.preview,
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'object_query_1' "
            "ORDER BY ORDINAL_POSITION",
        )

    def test_extract_presence_context_normalizes_quoted_table_reference(self) -> None:
        context = extract_presence_context(
            {
                "sql_query": (
                    "UPDATE [catalog].[dbo].[object_query_1] "
                    "SET img = 'x' WHERE EAN = '{ean}'"
                )
            },
            "5901234567890",
        )

        self.assertEqual(
            context,
            (
                "catalog.dbo.object_query_1",
                " WHERE EAN = '5901234567890'",
            ),
        )


if __name__ == "__main__":
    unittest.main()
