"""Integração end-to-end: escreve dataset, gera contrato, relê, diff vazio.

Sem testcontainers (arquivo local), mais barato que o equivalente Postgres.
"""

import pyarrow as pa
import pyarrow.parquet as pq

from driftbrake.contracts.writer import ContractWriter
from driftbrake.core.comparator import SchemaComparator
from driftbrake.readers.json.reader import JsonSchemaReader
from driftbrake.readers.parquet.reader import ParquetSchemaReader


def _write(path, table):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def test_write_read_contract_reread_is_empty(tmp_path):
    data_dir = tmp_path / "events"
    table = pa.table(
        {
            "id": pa.array([1, 2, 3], type=pa.int64()),
            "name": pa.array(["a", "b", "c"], type=pa.string()),
            "amount": pa.array([1.0, 2.0, 3.0], type=pa.float64()),
            "ts": pa.array([0, 1, 2], type=pa.timestamp("us")),
        }
    )
    for i in range(3):
        _write(data_dir / f"part-{i:05d}.parquet", table)

    current = ParquetSchemaReader(data_dir).read()

    contract_path = tmp_path / "schema.lock.json"
    ContractWriter(contract_path).write(current)
    expected = JsonSchemaReader(contract_path).read()

    diff = SchemaComparator().compare(expected, current)
    assert diff.is_compatible
    assert len(diff.changes) == 0


def test_legacy_contract_without_timestamp_unit_reread_is_empty(tmp_path):
    """Migração de contrato: um contrato gravado pela v0.3.0-leva-1 (quando a
    unidade era perdida na serialização) tem `ts` como "timestamp" sem unidade.
    Relido pela versão atual contra um dataset `timestamp(us)`, o primeiro check
    NÃO pode emitir um timestamp_unit_changed fantasma."""
    import json

    data_dir = tmp_path / "events"
    table = pa.table(
        {"id": pa.array([1], type=pa.int64()), "ts": pa.array([0], type=pa.timestamp("us"))}
    )
    _write(data_dir / "part-00000.parquet", table)

    # contrato "antigo": ts gravado como "timestamp" (sem unidade), como a leva-1 fazia
    legacy_contract = {
        "database_type": "parquet",
        "generated_at": "2026-01-01T00:00:00",
        "schemas": {
            "parquet": {
                "tables": {
                    "events": {
                        "columns": {
                            "id": {"type": "bigint", "nullable": True},
                            "ts": {"type": "timestamp", "nullable": True},
                        }
                    }
                }
            }
        },
    }
    contract_path = tmp_path / "schema.lock.json"
    contract_path.write_text(json.dumps(legacy_contract), encoding="utf-8")

    expected = JsonSchemaReader(contract_path).read()
    current = ParquetSchemaReader(data_dir, table_name="events").read()

    diff = SchemaComparator().compare(expected, current)
    assert diff.is_compatible
    assert len(diff.changes) == 0
