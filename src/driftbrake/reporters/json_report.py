# Reporter JSON - gera um arquivo schema_diff.json estável.

from __future__ import annotations

import json
from pathlib import Path

from driftbrake.core.models import DiffResult


class JsonReporter:
    # Serializa um DiffResult para um arquivo JSON.

    def __init__(self, output_path: str | Path) -> None:
        self.output_path = Path(output_path)

    def write(self, result: DiffResult) -> None:
        """
        Grava o DiffResult em um arquivo JSON.
        result: O resultado de diff a ser serializado.
        """
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        data = result.to_dict()
        with self.output_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def to_string(self, result: DiffResult) -> str:
        # Retorna a representação JSON como string.
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
