"""discover_tables: uma pasta vira UMA OU MAIS tabelas, por afinidade de colunas.

Cobre o caso que o teste do Argus expôs: uma pasta de tabelas heterogêneas não
pode virar um dataset único com o resto descartado. Aqui ela vira N tabelas, e
um dataset particionado de verdade continua sendo uma só.
"""

import pyarrow as pa
import pyarrow.parquet as pq

from driftbrake.readers.parquet.dataset import discover_tables


def _w(path, table):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def _events(id_type=pa.int64()):
    return pa.table(
        {
            "id": pa.array([1, 2], type=id_type),
            "amount": pa.array([1.0, 2.0]),
            "created_at": pa.array([0, 1], type=pa.timestamp("us")),
        }
    )


def test_homogeneous_dir_is_one_table(tmp_path):
    for i in range(3):
        _w(tmp_path / f"part-{i:05d}.parquet", _events())
    tables = discover_tables(tmp_path)
    assert len(tables) == 1
    name, ds = next(iter(tables.items()))
    assert name == tmp_path.name  # nome da pasta para um dataset solto
    assert ds.is_consistent
    assert set(ds.columns) == {"id", "amount", "created_at"}


def test_heterogeneous_dir_becomes_multiple_tables(tmp_path):
    _w(tmp_path / "events.parquet", _events())
    _w(tmp_path / "users.parquet", pa.table({"user_id": pa.array([1]), "email": pa.array(["a"])}))
    _w(tmp_path / "products.parquet", pa.table({"sku": pa.array(["x"]), "price": pa.array([1.0])}))

    tables = discover_tables(tmp_path)
    assert set(tables) == {"events", "users", "products"}  # nomeadas pelo stem
    # cada uma é consistente: nada de divergência fantasma found None entre tabelas
    assert all(ds.is_consistent for ds in tables.values())


def test_divergent_type_stays_one_table_with_drift(tmp_path):
    # 2 arquivos int64, 1 int32 na mesma coluna: MESMA tabela, com drift (não split)
    _w(tmp_path / "part-00000.parquet", _events(pa.int64()))
    _w(tmp_path / "part-00001.parquet", _events(pa.int64()))
    _w(tmp_path / "part-00002.parquet", _events(pa.int32()))
    tables = discover_tables(tmp_path)
    assert len(tables) == 1
    ds = next(iter(tables.values()))
    assert not ds.is_consistent
    assert len(ds.divergences) == 1
    d = ds.divergences[0]
    assert d.column == "id" and d.expected == "bigint" and d.found == "integer"


def test_added_column_keeps_one_table(tmp_path):
    # afinidade alta (2 de 3 colunas em comum); uma coluna a mais é drift, não tabela nova
    _w(tmp_path / "part-00000.parquet", pa.table({"id": pa.array([1]), "amount": pa.array([1.0])}))
    _w(tmp_path / "part-00001.parquet", pa.table({"id": pa.array([1]), "amount": pa.array([1.0])}))
    _w(
        tmp_path / "part-00002.parquet",
        pa.table({"id": pa.array([1]), "amount": pa.array([1.0]), "extra": pa.array(["x"])}),
    )
    tables = discover_tables(tmp_path)
    assert len(tables) == 1


def test_partitioned_dir_is_one_table(tmp_path):
    _w(tmp_path / "year=2026" / "month=06" / "part-0.parquet", _events())
    _w(tmp_path / "year=2026" / "month=07" / "part-0.parquet", _events())
    tables = discover_tables(tmp_path)
    assert len(tables) == 1
    ds = next(iter(tables.values()))
    assert ds.is_consistent
    assert "year" not in ds.columns and "month" not in ds.columns


def test_subdirectories_are_separate_tables(tmp_path):
    _w(tmp_path / "events" / "part-00000.parquet", _events())
    _w(tmp_path / "events" / "part-00001.parquet", _events())
    _w(tmp_path / "users" / "part-00000.parquet", pa.table({"user_id": pa.array([1])}))
    tables = discover_tables(tmp_path)
    assert set(tables) == {"events", "users"}  # nomeadas pelo subdiretório
    assert tables["events"].file_count == 2
