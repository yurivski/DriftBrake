"""ParquetSchemaReader sobre arquivo único."""

import sys
import time

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from driftbrake.exceptions import MissingDependencyError
from driftbrake.readers.parquet.reader import ParquetSchemaReader


def _write(path, table):
    pq.write_table(table, path)


def test_reads_single_file_schema(tmp_path):
    f = tmp_path / "part-00000.parquet"
    table = pa.table(
        {
            "id": pa.array([1, 2, 3], type=pa.int64()),
            "name": pa.array(["a", "b", "c"], type=pa.string()),
            "price": pa.array([1.5, 2.5, 3.5], type=pa.float64()),
        }
    )
    _write(f, table)

    schema = ParquetSchemaReader(f).read()
    table_schema = schema.get_table("parquet", "part-00000")
    assert table_schema is not None
    cols = table_schema.columns
    assert cols["id"].type == "bigint"
    assert cols["name"].type == "text"
    assert cols["price"].type == "double precision"


def test_reader_preserves_arrow_field_nullability(tmp_path):
    # required/optional físico do Parquet vira nullable no SchemaModel
    f = tmp_path / "part.parquet"
    schema = pa.schema(
        [pa.field("id", pa.int64(), nullable=False), pa.field("name", pa.string(), nullable=True)]
    )
    _write(f, pa.table({"id": pa.array([1]), "name": pa.array(["a"])}, schema=schema))

    cols = ParquetSchemaReader(f).read().get_table("parquet", "part").columns
    assert cols["id"].nullable is False
    assert cols["name"].nullable is True


def test_reader_uses_footer_not_data(tmp_path):
    small = tmp_path / "small.parquet"
    big = tmp_path / "big.parquet"
    schema = pa.schema([("id", pa.int64()), ("v", pa.string())])
    _write(small, pa.table({"id": pa.array([1] * 10), "v": pa.array(["x"] * 10)}, schema=schema))
    big_table = pa.table(
        {"id": pa.array([1] * 1_000_000), "v": pa.array(["x"] * 1_000_000)}, schema=schema
    )
    _write(big, big_table)

    small_schema = ParquetSchemaReader(small).read().get_table("parquet", "small")
    t0 = time.perf_counter()
    big_schema = ParquetSchemaReader(big).read().get_table("parquet", "big")
    elapsed = time.perf_counter() - t0

    # mesmo schema independente do volume; ler só o footer é barato mesmo com 1M linhas
    assert {c: v.type for c, v in big_schema.columns.items()} == {
        c: v.type for c, v in small_schema.columns.items()
    }
    assert elapsed < 1.0


def test_missing_pyarrow_raises_clear_error(tmp_path, monkeypatch):
    f = tmp_path / "x.parquet"
    _write(f, pa.table({"id": pa.array([1], type=pa.int64())}))

    # simula PyArrow ausente: import pyarrow.parquet passa a falhar
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)

    with pytest.raises(MissingDependencyError) as exc:
        ParquetSchemaReader(f).read()
    assert "driftbrake[parquet]" in str(exc.value)
