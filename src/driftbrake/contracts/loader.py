# Carrega contrato de schema - carrega e valida o schema.lock.json.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from driftbrake.core.models import DatabaseSchema
from driftbrake.exceptions import SchemaContractNotFoundError
from driftbrake.readers.json.reader import JsonSchemaReader

# Campos sempre obrigatórios (presentes em ambos os formatos)
REQUIRED_FIELDS = {"database_type", "generated_at", "schemas"}


class ContractLoader:
    # Carrega e valida um arquivo de contrato schema.lock.json.

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> DatabaseSchema:
        """
        DatabaseSchema: O schema interpretado.
        SchemaContractNotFoundError: Se o arquivo estiver ausente ou inválido.
        """
        if not self.path.exists():
            raise SchemaContractNotFoundError(
                f"Schema contract not found: {self.path}\n"
                "Run 'driftbrake init' to create a new contract."
            )

        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw: dict[str, Any] = json.load(f)
        except json.JSONDecodeError as exc:
            raise SchemaContractNotFoundError(
                f"Schema contract is not valid JSON: {self.path}\n{exc}"
            ) from exc

        self._validate(raw)

        reader = JsonSchemaReader(self.path)
        return reader.read()

    def _validate(self, data: dict[str, Any]) -> None:
        missing = REQUIRED_FIELDS - set(data.keys())
        if missing:
            raise SchemaContractNotFoundError(
                f"Schema contract is missing required fields: {missing}. File: {self.path}"
            )

        # Aceita formato legado (schema_detector_version) e novo (driftbrake_version)
        has_version = "driftbrake_version" in data or "schema_detector_version" in data
        if not has_version:
            raise SchemaContractNotFoundError(
                f"Schema contract is missing version field ('driftbrake_version'). "
                f"File: {self.path}"
            )

        if not isinstance(data.get("schemas"), dict):
            raise SchemaContractNotFoundError(
                f"Schema contract 'schemas' field must be a dict. File: {self.path}"
            )
