"""CLI `diff`: resolução de --new-db consistente com os demais comandos.

Regressão da pegadinha: `diff --new-db "$DATABASE_URL"` com a variável vazia no
shell virava `--new-db ""`, que era tratado como "não informado" e dizia
"Provide --new or --new-db" — enquanto `init`/`check` carregavam o .env e
conectavam. Agora o `diff` resolve --new-db pelo mesmo caminho (valor explícito,
senão .env / DATABASE_URL), com mensagem específica de banco.
"""

import importlib
import json
from datetime import datetime

from typer.testing import CliRunner

from driftbrake.core.models import ColumnSchema, DatabaseSchema, TableSchema

# `driftbrake.cli.__init__` reexporta `app`, sombreando o nome do submódulo;
# pega o módulo real via importlib para conseguir monkeypatchar seus globais.
app_mod = importlib.import_module("driftbrake.cli.app")

runner = CliRunner()


def _snapshot(path):
    data = {
        "database_type": "postgresql",
        "generated_at": "2026-01-01T00:00:00",
        "schemas": {"public": {"tables": {"t": {"columns": {"id": {"type": "integer"}}}}}},
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _fake_db():
    col = ColumnSchema("id", "integer", True, None, False, False, [], 1)
    table = TableSchema(name="t", schema="public", columns={"id": col})
    return DatabaseSchema("postgresql", datetime(2026, 1, 1), {"public": {"t": table}})


class _FakeReader:
    """Captura a URL recebida sem abrir conexão real."""

    last_url = None

    def __init__(self, database_url=None, **kwargs):
        _FakeReader.last_url = database_url

    def read(self):
        return _fake_db()


def _isolate_env(monkeypatch):
    monkeypatch.setattr(app_mod, "load_dotenv", lambda *a, **k: None)
    for var in ("DATABASE_URL", "DB_NAME", "DB_USER", "DB_HOST", "DB_PORT", "DB_PASSWORD"):
        monkeypatch.delenv(var, raising=False)


def test_diff_new_db_empty_no_env_gives_db_specific_error(tmp_path, monkeypatch):
    _isolate_env(monkeypatch)
    old = _snapshot(tmp_path / "before.json")

    result = runner.invoke(app_mod.app, ["diff", "--old", old, "--new-db", ""])
    assert result.exit_code == 3
    # mensagem de banco, nomeando --new-db e DATABASE_URL — não a antiga genérica
    assert "DATABASE_URL" in result.output
    assert "--new-db" in result.output
    assert "Provide --new or --new-db" not in result.output


def test_diff_new_db_empty_falls_back_to_env(tmp_path, monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@localhost:5432/dbfromenv")
    monkeypatch.setattr(app_mod, "PostgresSchemaReader", _FakeReader)
    old = _snapshot(tmp_path / "before.json")

    result = runner.invoke(app_mod.app, ["diff", "--old", old, "--new-db", ""])
    # --new-db "" resolveu para a URL do ambiente (igual init/check)
    assert _FakeReader.last_url == "postgresql://user:pw@localhost:5432/dbfromenv"
    assert result.exit_code == 0


def test_diff_new_db_explicit_value_is_used(tmp_path, monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setattr(app_mod, "PostgresSchemaReader", _FakeReader)
    old = _snapshot(tmp_path / "before.json")

    url = "postgresql://user:pw@localhost:5432/explicit"
    result = runner.invoke(app_mod.app, ["diff", "--old", old, "--new-db", url])
    assert _FakeReader.last_url == url
    assert result.exit_code == 0


def test_diff_neither_source_still_asks_for_one(tmp_path, monkeypatch):
    _isolate_env(monkeypatch)
    old = _snapshot(tmp_path / "before.json")

    result = runner.invoke(app_mod.app, ["diff", "--old", old])
    assert result.exit_code == 6
    assert "Provide --new or --new-db" in result.output


def test_diff_file_to_file_still_works(tmp_path, monkeypatch):
    _isolate_env(monkeypatch)
    old = _snapshot(tmp_path / "before.json")
    new = _snapshot(tmp_path / "after.json")

    result = runner.invoke(app_mod.app, ["diff", "--old", old, "--new", new])
    assert result.exit_code == 0
