# Leitor de schema JSON: lê o schema.lock.json e converte para DatabaseSchema.

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from driftbrake.core.models import ColumnSchema, DatabaseSchema, TableSchema, _parse_indexes
from driftbrake.exceptions import SchemaContractNotFoundError
from driftbrake.readers.base import SchemaReader


class JsonSchemaReader(SchemaReader):
    """
    Lê metadados de schema de um arquivo schema.lock.json.
    Converte o formato do lock file para um objeto DatabaseSchema para comparação.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> DatabaseSchema:
        """
        Lê o arquivo de lock de schema e retorna um DatabaseSchema.

        DatabaseSchema: O schema representado no lock file.
        SchemaContractNotFoundError: Se o arquivo não existir ou for inválido.
        """
        if not self.path.exists():
            raise SchemaContractNotFoundError(f"Schema contract file not found: {self.path}")

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except json.JSONDecodeError as exc:
            raise SchemaContractNotFoundError(
                f"Schema contract file is not valid JSON: {self.path}\n{exc}"
            ) from exc

        return self._parse(data)

    def _parse(self, data: dict[str, Any]) -> DatabaseSchema:
        database_type = data.get("database_type", "postgresql")
        generated_at_raw = data.get("generated_at", "")
        try:
            generated_at = datetime.fromisoformat(generated_at_raw)
        except (ValueError, TypeError):
            generated_at = datetime.now()

        raw_schemas = data.get("schemas", {})
        db_schemas: dict[str, dict[str, TableSchema]] = {}

        for schema_name, schema_data in raw_schemas.items():
            db_schemas[schema_name] = {}
            raw_tables = schema_data.get("tables", {})
            for table_name, table_data in raw_tables.items():
                table_schema = self._parse_table(schema_name, table_name, table_data)
                db_schemas[schema_name][table_name] = table_schema

        return DatabaseSchema(
            database_type=database_type,
            generated_at=generated_at,
            schemas=db_schemas,
        )

    def _parse_table(
        self, schema_name: str, table_name: str, table_data: dict[str, Any]
    ) -> TableSchema:
        raw_columns = table_data.get("columns", {})
        columns: dict[str, ColumnSchema] = {}
        for col_name, col_data in raw_columns.items():
            columns[col_name] = ColumnSchema.from_dict(col_name, col_data)

        indexes = _parse_indexes(table_data.get("indexes", []))
        return TableSchema(
            name=table_name,
            schema=schema_name,
            columns=columns,
            indexes=indexes,
            check_constraints=table_data.get("check_constraints", []),
        )
