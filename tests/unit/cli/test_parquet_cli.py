"""CLI parquet-check: liga o relatório de divergência inter-arquivo ao terminal."""

import pyarrow as pa
import pyarrow.parquet as pq
from typer.testing import CliRunner

from driftbrake.cli.app import app

runner = CliRunner()


def _write(path, amount_type):
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "id": pa.array([1, 2], type=pa.int64()),
            "amount": pa.array([10, 20], type=amount_type),
        }
    )
    pq.write_table(table, path)


def test_consistent_dataset_exits_zero(tmp_path):
    _write(tmp_path / "a.parquet", pa.int64())
    _write(tmp_path / "b.parquet", pa.int64())

    result = runner.invoke(app, ["parquet-check", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "schema-consistent" in result.output


def test_divergent_dataset_exits_two_and_names_file(tmp_path):
    _write(tmp_path / "part-00001.parquet", pa.int64())
    _write(tmp_path / "part-00002.parquet", pa.int64())
    _write(tmp_path / "part-00003.parquet", pa.int32())

    result = runner.invoke(app, ["parquet-check", "--path", str(tmp_path)])
    assert result.exit_code == 2
    assert "part-00003.parquet" in result.output
    assert "amount" in result.output


def test_within_tolerance_exits_zero(tmp_path):
    _write(tmp_path / "part-00001.parquet", pa.int64())
    _write(tmp_path / "part-00002.parquet", pa.int64())
    _write(tmp_path / "part-00003.parquet", pa.int32())

    result = runner.invoke(app, ["parquet-check", "--path", str(tmp_path), "--max-divergent", "1"])
    assert result.exit_code == 0
    assert "within tolerance" in result.output


def test_empty_directory_exits_three(tmp_path):
    result = runner.invoke(app, ["parquet-check", "--path", str(tmp_path)])
    assert result.exit_code == 3


def test_init_source_builds_contract_and_check_is_clean(tmp_path):
    _write(tmp_path / "part-00000.parquet", pa.int64())
    _write(tmp_path / "part-00001.parquet", pa.int64())
    contract = tmp_path / "schema.lock.json"

    init_res = runner.invoke(app, ["init", "--source", str(tmp_path), "--output", str(contract)])
    assert init_res.exit_code == 0
    assert contract.exists()

    check_res = runner.invoke(
        app, ["check", "--source", str(tmp_path), "--contract", str(contract)]
    )
    assert check_res.exit_code == 0
    assert "compatible" in check_res.output


def test_check_source_fails_on_inter_file_divergence(tmp_path):
    _write(tmp_path / "part-00000.parquet", pa.int64())
    _write(tmp_path / "part-00001.parquet", pa.int64())
    contract = tmp_path / "schema.lock.json"
    runner.invoke(app, ["init", "--source", str(tmp_path), "--output", str(contract)])

    _write(tmp_path / "part-00002.parquet", pa.int32())
    res = runner.invoke(app, ["check", "--source", str(tmp_path), "--contract", str(contract)])
    assert res.exit_code == 2
    assert "part-00002.parquet" in res.output


def test_check_source_missing_contract_exits_four(tmp_path):
    _write(tmp_path / "part-00000.parquet", pa.int64())
    res = runner.invoke(
        app, ["check", "--source", str(tmp_path), "--contract", str(tmp_path / "nope.json")]
    )
    assert res.exit_code == 4


# --- pasta heterogênea: uma ou mais tabelas, sem perda silenciosa ---------------


def _write_table(path, table):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def _heterogeneous(tmp_path):
    _write_table(
        tmp_path / "events.parquet",
        pa.table({"id": pa.array([1]), "amt": pa.array([1.0])}),
    )
    _write_table(
        tmp_path / "users.parquet",
        pa.table({"user_id": pa.array([1]), "email": pa.array(["a"])}),
    )
    _write_table(
        tmp_path / "products.parquet",
        pa.table({"sku": pa.array(["x"]), "price": pa.array([1.0])}),
    )


def test_init_heterogeneous_captures_all_tables_no_silent_drop(tmp_path):
    # Regressão do bug do Argus: init não pode gravar uma tabela e descartar o resto.
    import json

    _heterogeneous(tmp_path)
    contract = tmp_path / "schema.lock.json"
    res = runner.invoke(app, ["init", "--source", str(tmp_path), "--output", str(contract)])
    assert res.exit_code == 0
    tables = set(json.loads(contract.read_text())["schemas"]["parquet"]["tables"])
    assert tables == {"events", "users", "products"}  # as três, não só a dominante
    # e o output lista o que foi capturado, em vez de só dizer "1 table"
    for name in ("events", "users", "products"):
        assert name in res.output


def test_parquet_check_heterogeneous_has_no_phantom_divergence(tmp_path):
    # Antes: dezenas de "divergências" found None entre tabelas diferentes.
    # Agora: três tabelas, cada uma consistente.
    _heterogeneous(tmp_path)
    res = runner.invoke(app, ["parquet-check", "--path", str(tmp_path)])
    assert res.exit_code == 0
    assert "3 tables discovered" in res.output
    assert "found None" not in res.output


def test_init_table_override_names_single_table(tmp_path):
    import json

    _write(tmp_path / "part-00000.parquet", pa.int64())
    _write(tmp_path / "part-00001.parquet", pa.int64())
    contract = tmp_path / "c.json"
    res = runner.invoke(
        app, ["init", "--source", str(tmp_path), "--table", "eventos", "--output", str(contract)]
    )
    assert res.exit_code == 0
    assert list(json.loads(contract.read_text())["schemas"]["parquet"]["tables"]) == ["eventos"]
