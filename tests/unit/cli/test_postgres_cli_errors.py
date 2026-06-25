"""CLI: erros conhecidos da leitura Postgres saem limpos, não como traceback.

Regressão: `init --schemas public,sales` contra um banco sem o schema `sales`
levantava SchemaNotFoundError, que NÃO era capturado (só SchemaConnectionError
era) — o usuário via um traceback inteiro em vez de uma mensagem e exit code.
SchemaNotFoundError tem exit_code=5; agora init/check/snapshot/update-contract
capturam qualquer DriftBrakeError e saem com o código certo.
"""

import importlib

from typer.testing import CliRunner

from driftbrake.exceptions import SchemaNotFoundError

app_mod = importlib.import_module("driftbrake.cli.app")
runner = CliRunner()

_MSG = "Schema(s) not found in database: ['sales']. Existing schemas: ['public']"


class _RaisingReader:
    def __init__(self, **kwargs):
        pass

    def read(self):
        raise SchemaNotFoundError(_MSG)


class _RaisingGuard:
    def __init__(self, **kwargs):
        pass

    def check(self):
        raise SchemaNotFoundError(_MSG)


def _assert_clean_schema_error(result):
    assert result.exit_code == 5  # exit_code de SchemaNotFoundError, não 1 (traceback)
    assert "[ERROR]" in result.output
    assert "not found in database" in result.output
    # o erro de biblioteca não vazou como exceção não-tratada
    assert not isinstance(result.exception, SchemaNotFoundError)


def test_init_schema_not_found_is_clean(monkeypatch):
    monkeypatch.setattr(app_mod, "PostgresSchemaReader", _RaisingReader)
    result = runner.invoke(
        app_mod.app,
        ["init", "--db-url", "postgresql://x", "--schemas", "public,sales"],
    )
    _assert_clean_schema_error(result)


def test_snapshot_schema_not_found_is_clean(monkeypatch):
    monkeypatch.setattr(app_mod, "PostgresSchemaReader", _RaisingReader)
    result = runner.invoke(
        app_mod.app,
        ["snapshot", "--db-url", "postgresql://x", "--schemas", "public,sales"],
    )
    _assert_clean_schema_error(result)


def test_update_contract_schema_not_found_is_clean(monkeypatch):
    monkeypatch.setattr(app_mod, "PostgresSchemaReader", _RaisingReader)
    result = runner.invoke(
        app_mod.app,
        ["update-contract", "--yes", "--db-url", "postgresql://x", "--schemas", "public,sales"],
    )
    _assert_clean_schema_error(result)


def test_check_schema_not_found_is_clean(monkeypatch):
    # check passa pelo SchemaGuard; antes caía no `except Exception` -> exit 6.
    monkeypatch.setattr(app_mod, "SchemaGuard", _RaisingGuard)
    result = runner.invoke(app_mod.app, ["check", "--db-url", "postgresql://x"])
    _assert_clean_schema_error(result)
