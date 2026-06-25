# Grava contrato de schema - salva o schema.lock.json a partir de um DatabaseSchema.

from __future__ import annotations

import json
from importlib.metadata import version as _get_version
from pathlib import Path

from driftbrake.core.models import DatabaseSchema


class ContractWriter:
    # Grava um DatabaseSchema em um arquivo schema.lock.json.

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write(self, schema: DatabaseSchema) -> None:
        """
        Serializa o DatabaseSchema para JSON e grava no disco.
        schema: O DatabaseSchema a ser persistido.
        """
        data = self._serialize(schema)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _serialize(self, schema: DatabaseSchema) -> dict:
        serialized_schemas: dict = {}
        for schema_name, tables in schema.schemas.items():
            serialized_schemas[schema_name] = {
                "tables": {
                    table_name: self._serialize_table(table) for table_name, table in tables.items()
                }
            }

        return {
            "contract_version": "1.0",
            "generated_by": "driftbrake",
            "driftbrake_version": _get_version("driftbrake"),
            "database_type": schema.database_type,
            "generated_at": schema.generated_at.isoformat(),
            "schemas": serialized_schemas,
        }

    def _serialize_table(self, table) -> dict:
        # Delega ao serializador do próprio modelo (fonte única). Reimplementar
        # aqui foi o que deixou `indexes` como objetos IndexSchema crus — não
        # serializáveis — em vez de `[idx.to_dict() ...]`.
        return table.to_dict()
