"""
ParquetSchemaReader — fronteira de entrada do engine Parquet.

Orquestra: descobre arquivos, delega ao `dataset.py`, devolve `DatabaseSchema`
(modelo neutro). Import lazy do PyArrow; se ausente, erro claro apontando
`driftbrake[parquet]` (mesmo padrão do psycopg2).

Um diretório é lido como UMA OU MAIS tabelas: arquivos com colunas afins são a
mesma tabela (um dataset, com divergência inter-arquivo); conjuntos disjuntos
são tabelas distintas. Os datasets por tabela ficam em `self.table_datasets`
após `read()`; `self.dataset_schema` é atalho para o único, quando há só um.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from driftbrake.core.models import ColumnSchema, DatabaseSchema, TableSchema
from driftbrake.exceptions import MissingDependencyError, ParquetReadError
from driftbrake.readers.base import SchemaReader


class ParquetSchemaReader(SchemaReader):
    """Lê um arquivo ou diretório Parquet e devolve `DatabaseSchema`.

    Diretório vira uma ou mais tabelas (por afinidade de colunas); cada tabela é
    um dataset com seu próprio relatório de divergência inter-arquivo.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        schema_name: str = "parquet",
        table_name: str | None = None,
        dominant_schema_strategy: str = "most_common",
        ignore_partition_columns: bool = True,
    ) -> None:
        self.path = Path(path)
        self.schema_name = schema_name
        self._table_name_override = table_name
        self.dominant_schema_strategy = dominant_schema_strategy
        self.ignore_partition_columns = ignore_partition_columns
        # preenchidos por read():
        self.table_datasets: dict = {}  # {nome_tabela: DatasetSchema}
        self.dataset_schema = None  # atalho: o único dataset, se houver só um

    def _require_pyarrow(self) -> None:
        try:
            import pyarrow.parquet  # noqa: F401
        except ImportError as exc:
            raise MissingDependencyError(
                "PyArrow é necessário para ler Parquet. Instale driftbrake[parquet]."
            ) from exc

    def _build_table(self, name: str, dataset) -> TableSchema:
        columns: dict[str, ColumnSchema] = {}
        for position, (col_name, canonical) in enumerate(dataset.columns.items(), start=1):
            columns[col_name] = ColumnSchema(
                name=col_name,
                type=str(canonical),
                # required/optional físico do Parquet: lido do footer (drift de nulabilidade)
                nullable=dataset.nullability.get(col_name, True),
                default=None,
                primary_key=False,
                unique=False,
                foreign_key=[],
                ordinal_position=position,
            )
        return TableSchema(name=name, schema=self.schema_name, columns=columns)

    def read(self) -> DatabaseSchema:
        self._require_pyarrow()

        from driftbrake.readers.parquet.dataset import (
            ArrowTypeAdapter,
            DatasetSchema,
            _read_file,
            discover_tables,
        )

        if not self.path.exists():
            raise ParquetReadError(f"Caminho Parquet não encontrado: {self.path}")

        if self.path.is_file():
            types, nullables = _read_file(self.path, ArrowTypeAdapter())
            name = self._table_name_override or self.path.stem or self.path.name
            self.table_datasets = {
                name: DatasetSchema(columns=types, file_count=1, nullability=nullables)
            }
        else:
            tables = discover_tables(
                self.path,
                dominant_schema_strategy=self.dominant_schema_strategy,
                ignore_partition_columns=self.ignore_partition_columns,
            )
            # --table só renomeia quando o diretório resolve para UMA tabela;
            # com várias, os nomes vêm da estrutura (não há um nome único a dar).
            if self._table_name_override and len(tables) == 1:
                ((_, only),) = tables.items()
                tables = {self._table_name_override: only}
            self.table_datasets = tables

        self.dataset_schema = (
            next(iter(self.table_datasets.values())) if len(self.table_datasets) == 1 else None
        )

        schema_tables = {
            name: self._build_table(name, ds) for name, ds in self.table_datasets.items()
        }
        return DatabaseSchema(
            database_type="parquet",
            generated_at=datetime.now(),
            schemas={self.schema_name: schema_tables},
        )
