"""CLI: um único policy.yml controla tanto Postgres quanto Parquet.

Antes a CLI tinha dois arquivos: driftbrake.yml (só fail_on, via SchemaGuard) e
driftbrake.policy.yml (só a biblioteca aplicava os overrides). Agora o `check`
aplica o policy.yml (base + seção do engine) nos dois caminhos, igual à lib.
"""

import importlib
from datetime import datetime

from typer.testing import CliRunner

from driftbrake.core.models import ChangeType, DiffResult, SchemaChange, Severity

app_mod = importlib.import_module("driftbrake.cli.app")
runner = CliRunner()


def _change(severity, change_type=ChangeType.COLUMN_REMOVED):
    return SchemaChange(
        change_type=change_type,
        severity=severity,
        schema_name="public",
        table_name="customers",
        column_name="email",
        field_name=None,
        old_value="text",
        new_value=None,
        description="coluna removida",
    )


class _FakeGuard:
    """SchemaGuard de mentira: check() devolve um BREAKING fixo; reports são no-op."""

    result = None

    def __init__(self, **kwargs):
        pass

    def check(self):
        return DiffResult(changes=[_change(Severity.BREAKING)], compared_at=datetime(2026, 1, 1))

    def save_reports(self, result):
        _FakeGuard.result = result

    def print_report(self, result):
        pass


def _write_policy(path, body):
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_check_postgres_applies_policy_override(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "SchemaGuard", _FakeGuard)
    policy = _write_policy(
        tmp_path / "policy.yml",
        "postgres:\n  overrides:\n    column_removed: WARNING\n",
    )
    # column_removed é BREAKING por padrão; a seção postgres rebaixa para WARNING,
    # então com --fail-on BREAKING o check passa (exit 0).
    result = runner.invoke(app_mod.app, ["check", "--db-url", "postgresql://x", "--policy", policy])
    assert result.exit_code == 0
    assert "compatible" in result.output


def test_check_postgres_without_policy_still_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "SchemaGuard", _FakeGuard)
    # policy.yml inexistente -> sem override -> BREAKING continua bloqueando (exit 2).
    result = runner.invoke(
        app_mod.app,
        ["check", "--db-url", "postgresql://x", "--policy", str(tmp_path / "absent.yml")],
    )
    assert result.exit_code == 2


def test_check_postgres_parquet_section_does_not_leak(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "SchemaGuard", _FakeGuard)
    # Override só na seção parquet NÃO afeta o caminho postgres -> ainda BREAKING.
    policy = _write_policy(
        tmp_path / "policy.yml",
        "parquet:\n  overrides:\n    column_removed: SAFE\n",
    )
    result = runner.invoke(app_mod.app, ["check", "--db-url", "postgresql://x", "--policy", policy])
    assert result.exit_code == 2


def test_single_policy_file_drives_both_engines(tmp_path, monkeypatch):
    # O mesmo policy.yml: base aplica aos dois; cada seção afina o seu engine.
    from driftbrake.core.policy import load_policy

    policy = load_policy(
        _write_policy(
            tmp_path / "policy.yml",
            "overrides:\n  column_removed: WARNING\n"
            "postgres:\n  overrides:\n    index_removed: BREAKING\n"
            "parquet:\n  overrides:\n    timestamp_unit_changed: BREAKING\n",
        )
    )
    res = DiffResult(changes=[_change(Severity.BREAKING)])
    pg = app_mod.apply_policy(res, policy, engine="postgres")
    pq = app_mod.apply_policy(res, policy, engine="parquet")
    # base (column_removed: WARNING) vale para os dois
    assert pg.changes[0].severity == Severity.WARNING
    assert pq.changes[0].severity == Severity.WARNING
    # e cada engine tem o seu vocabulário próprio na mesma fonte
    assert policy.effective_overrides("postgres")["index_removed"] == "BREAKING"
    assert policy.effective_overrides("parquet")["timestamp_unit_changed"] == "BREAKING"
