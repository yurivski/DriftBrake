"""O coração da feature: consolidação e detecção de divergência inter-arquivo."""

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from driftbrake.exceptions import ParquetReadError
from driftbrake.readers.parquet.dataset import read_dataset


def _write(path, table):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def _file(n_id_type, amount_type=pa.int64()):
    return pa.table(
        {
            "id": pa.array([1, 2], type=n_id_type),
            "amount": pa.array([10, 20], type=amount_type),
        }
    )


def test_consistent_dataset_consolidates_to_single_schema(tmp_path):
    for i in range(3):
        _write(tmp_path / f"part-{i:05d}.parquet", _file(pa.int64()))

    ds = read_dataset(tmp_path)
    assert ds.file_count == 3
    assert ds.is_consistent
    assert ds.divergences == []
    assert ds.columns["id"].base == "bigint"
    assert ds.columns["amount"].base == "bigint"


def test_divergent_file_is_detected(tmp_path):
    # 2 arquivos com int64, 1 com int32 na coluna amount
    _write(tmp_path / "part-00001.parquet", _file(pa.int64(), amount_type=pa.int64()))
    _write(tmp_path / "part-00002.parquet", _file(pa.int64(), amount_type=pa.int64()))
    _write(tmp_path / "part-00003.parquet", _file(pa.int64(), amount_type=pa.int32()))

    ds = read_dataset(tmp_path)
    assert not ds.is_consistent
    assert len(ds.divergences) == 1
    d = ds.divergences[0]
    assert "part-00003" in d.file
    assert d.column == "amount"
    assert d.expected == "bigint"
    assert d.found == "integer"
    # forma da saída exigida pela v0.3.0
    out = ds.to_dict()
    assert out["schema_dominante"]["amount"] == "bigint"
    assert out["divergencias"][0]["arquivo"] == d.file


def test_partitioned_dataset_ignores_partition_columns(tmp_path):
    # 'year' aparece no footer com tipos diferentes; é coluna de partição (vem do path)
    _write(
        tmp_path / "year=2026" / "month=06" / "a.parquet",
        pa.table({"id": pa.array([1], type=pa.int64()), "year": pa.array([2026], type=pa.int32())}),
    )
    _write(
        tmp_path / "year=2025" / "month=06" / "b.parquet",
        pa.table({"id": pa.array([2], type=pa.int64()), "year": pa.array([2025], type=pa.int64())}),
    )

    ds = read_dataset(tmp_path, ignore_partition_columns=True)
    assert "year" not in ds.columns  # coluna de partição não vira schema
    assert ds.divergences == []  # nem drift fantasma
    assert "year" in ds.partition_columns


def test_timestamp_unit_divergence_is_visible(tmp_path):
    # mesma base física, unidades diferentes — antes ambos renderizavam "timestamp"
    _write(
        tmp_path / "a.parquet",
        pa.table({"ts": pa.array([0, 1], type=pa.timestamp("us"))}),
    )
    _write(
        tmp_path / "b.parquet",
        pa.table({"ts": pa.array([0, 1], type=pa.timestamp("ms"))}),
    )
    ds = read_dataset(tmp_path, dominant_schema_strategy="first_file")
    assert not ds.is_consistent
    d = ds.divergences[0]
    assert d.expected == "timestamp(us)"
    assert d.found == "timestamp(ms)"


def test_dataset_carries_dominant_nullability(tmp_path):
    schema = pa.schema(
        [pa.field("id", pa.int64(), nullable=False), pa.field("v", pa.string(), nullable=True)]
    )
    table = pa.table({"id": pa.array([1]), "v": pa.array(["x"])}, schema=schema)
    _write(tmp_path / "a.parquet", table)
    ds = read_dataset(tmp_path)
    assert ds.nullability == {"id": False, "v": True}


def test_empty_directory_raises(tmp_path):
    with pytest.raises(ParquetReadError):
        read_dataset(tmp_path)
