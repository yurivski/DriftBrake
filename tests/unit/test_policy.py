"""
Testes de carregamento e aplicação de política.
Pra evitar que o arquivo fique muito grande, apenas as chamadas com argumentos
acima de 100 caracteres terão quebras de linhas.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from driftbrake.exceptions import PolicyError
from driftbrake.models import ChangeType, DiffResult, SchemaChange, Severity
from driftbrake.policy import ParquetPolicy, Policy, PostgresPolicy, apply_policy, load_policy

# helpers


def _change(
    severity: Severity,
    table: str = "users",
    column: str = "email",
    change_type: ChangeType = ChangeType.COLUMN_REMOVED,
) -> SchemaChange:
    return SchemaChange(
        change_type=change_type,
        severity=severity,
        schema_name="public",
        table_name=table,
        column_name=column,
        field_name=None,
        old_value="text",
        new_value=None,
        description="test change",
    )


def _write_yaml(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


# load_policy


def test_load_policy_none_returns_empty():
    policy = load_policy(None)
    assert isinstance(policy, Policy)
    assert policy.overrides == {}
    assert policy.ignore_tables == []
    assert policy.ignore_columns == []


def test_load_policy_valid_yaml():
    path = _write_yaml("""
overrides:
  column_removed: WARNING
  table_added: SAFE

ignore_tables:
  - audit_log
  - tmp_staging

ignore_columns:
  - users.updated_at
""")
    try:
        policy = load_policy(path)
        assert policy.overrides["column_removed"] == "WARNING"
        assert policy.overrides["table_added"] == "SAFE"
        assert "audit_log" in policy.ignore_tables
        assert "tmp_staging" in policy.ignore_tables
        assert "users.updated_at" in policy.ignore_columns
    finally:
        os.unlink(path)


def test_load_policy_empty_yaml_returns_empty():
    path = _write_yaml("")
    try:
        policy = load_policy(path)
        assert policy.overrides == {}
    finally:
        os.unlink(path)


def test_load_policy_missing_file_raises():
    with pytest.raises(PolicyError, match="not found"):
        load_policy("/tmp/this_file_does_not_exist_driftbrake.yml")


def test_load_policy_malformed_yaml_raises():
    path = _write_yaml("overrides: [invalid: yaml: structure")
    try:
        with pytest.raises(PolicyError):
            load_policy(path)
    finally:
        os.unlink(path)


def test_load_policy_invalid_severity_raises():
    path = _write_yaml("overrides:\n  column_removed: TYPO\n")
    try:
        with pytest.raises(PolicyError, match="Invalid severity"):
            load_policy(path)
    finally:
        os.unlink(path)


def test_load_policy_severity_case_insensitive():
    path = _write_yaml("overrides:\n  column_removed: breaking\n")
    try:
        policy = load_policy(path)
        assert policy.overrides["column_removed"] == "BREAKING"
    finally:
        os.unlink(path)


# apply_policy


def test_apply_policy_no_overrides_returns_unchanged():
    result = DiffResult(changes=[_change(Severity.BREAKING)])
    policy = Policy()
    out = apply_policy(result, policy)
    assert out is result  # sem modificações, retorna o mesmo objeto


def test_apply_policy_ignores_table():
    result = DiffResult(
        changes=[
            _change(Severity.BREAKING, table="audit_log"),
            _change(Severity.SAFE, table="users"),
        ]
    )
    policy = Policy(ignore_tables=["audit_log"])
    out = apply_policy(result, policy)
    assert len(out.changes) == 1
    assert out.changes[0].table_name == "users"


def test_apply_policy_ignores_column():
    result = DiffResult(
        changes=[
            _change(Severity.BREAKING, table="users", column="updated_at"),
            _change(Severity.SAFE, table="users", column="email"),
        ]
    )
    policy = Policy(ignore_columns=["users.updated_at"])
    out = apply_policy(result, policy)
    assert len(out.changes) == 1
    assert out.changes[0].column_name == "email"


def test_apply_policy_parquet_override_aliases():
    # nullable_to_required / required_to_nullable apelidam os change_types NOT NULL
    result = DiffResult(
        changes=[
            _change(Severity.BREAKING, change_type=ChangeType.NOT_NULL_CONSTRAINT_ADDED),
            _change(Severity.WARNING, change_type=ChangeType.NOT_NULL_CONSTRAINT_REMOVED),
        ]
    )
    policy = Policy(overrides={"nullable_to_required": "WARNING", "required_to_nullable": "SAFE"})
    out = apply_policy(result, policy)
    by_type = {c.change_type: c.severity for c in out.changes}
    assert by_type[ChangeType.NOT_NULL_CONSTRAINT_ADDED] == Severity.WARNING
    assert by_type[ChangeType.NOT_NULL_CONSTRAINT_REMOVED] == Severity.SAFE


def test_apply_policy_timestamp_unit_override():
    result = DiffResult(
        changes=[_change(Severity.WARNING, change_type=ChangeType.TIMESTAMP_UNIT_CHANGED)]
    )
    policy = Policy(overrides={"timestamp_unit_changed": "BREAKING"})
    out = apply_policy(result, policy)
    assert out.changes[0].severity == Severity.BREAKING


def test_apply_policy_overrides_severity():
    result = DiffResult(changes=[_change(Severity.BREAKING, change_type=ChangeType.COLUMN_REMOVED)])
    policy = Policy(overrides={"column_removed": "WARNING"})
    out = apply_policy(result, policy)
    assert out.changes[0].severity == Severity.WARNING


def test_apply_policy_preserves_metadata():
    from datetime import datetime

    ts = datetime(2026, 1, 1)
    result = DiffResult(
        changes=[_change(Severity.SAFE)],
        compared_at=ts,
        expected_source="a",
        current_source="b",
    )
    policy = Policy(ignore_tables=["non_existent"])
    out = apply_policy(result, policy)
    assert out.compared_at == ts
    assert out.expected_source == "a"
    assert out.current_source == "b"


# ---------------------------------------------------------------------------
# Política por engine: base agnóstica + seções postgres/parquet
# ---------------------------------------------------------------------------


def test_load_policy_parses_both_engine_sections():
    policy = load_policy(
        _write_yaml(
            """
overrides:
  column_removed: BREAKING
ignore_tables:
  - audit_log
postgres:
  overrides:
    index_removed: BREAKING
parquet:
  dataset:
    dominant_schema_strategy: latest_mtime
    max_divergent_files: 2
  overrides:
    timestamp_unit_changed: BREAKING
"""
        )
    )
    assert policy.overrides == {"column_removed": "BREAKING"}
    assert policy.ignore_tables == ["audit_log"]
    assert policy.postgres is not None
    assert policy.postgres.overrides == {"index_removed": "BREAKING"}
    assert policy.parquet is not None
    assert policy.parquet.dataset.dominant_schema_strategy == "latest_mtime"
    assert policy.parquet.dataset.max_divergent_files == 2
    assert policy.parquet.overrides == {"timestamp_unit_changed": "BREAKING"}


def test_missing_engine_sections_default_to_none():
    policy = load_policy(_write_yaml("overrides:\n  column_removed: BREAKING\n"))
    assert policy.postgres is None
    assert policy.parquet is None


def test_invalid_severity_in_postgres_section_raises():
    with pytest.raises(PolicyError):
        load_policy(_write_yaml("postgres:\n  overrides:\n    index_removed: NONSENSE\n"))


def test_effective_overrides_merges_base_with_engine():
    policy = Policy(
        overrides={"column_removed": "BREAKING", "default_changed": "WARNING"},
        postgres=PostgresPolicy(overrides={"index_removed": "BREAKING"}),
        parquet=ParquetPolicy(overrides={"timestamp_unit_changed": "BREAKING"}),
    )
    # base sozinha
    assert policy.effective_overrides() == {
        "column_removed": "BREAKING",
        "default_changed": "WARNING",
    }
    # base + postgres
    assert policy.effective_overrides("postgres") == {
        "column_removed": "BREAKING",
        "default_changed": "WARNING",
        "index_removed": "BREAKING",
    }
    # base + parquet
    assert policy.effective_overrides("parquet") == {
        "column_removed": "BREAKING",
        "default_changed": "WARNING",
        "timestamp_unit_changed": "BREAKING",
    }


def test_engine_section_overrides_base_key():
    # mesma key na base e na seção do engine: a seção vence, e só para aquele engine
    policy = Policy(
        overrides={"column_removed": "BREAKING"},
        parquet=ParquetPolicy(overrides={"column_removed": "WARNING"}),
    )
    assert policy.effective_overrides()["column_removed"] == "BREAKING"
    assert policy.effective_overrides("postgres")["column_removed"] == "BREAKING"
    assert policy.effective_overrides("parquet")["column_removed"] == "WARNING"


def test_engines_are_isolated_in_apply_policy():
    # Um column_removed é classificado diferente por engine, sem duplicar a base.
    policy = Policy(
        overrides={"column_removed": "BREAKING"},
        parquet=ParquetPolicy(overrides={"column_removed": "SAFE"}),
    )
    res = DiffResult(changes=[_change(Severity.BREAKING, change_type=ChangeType.COLUMN_REMOVED)])

    pg = apply_policy(res, policy, engine="postgres")
    pq = apply_policy(res, policy, engine="parquet")
    assert pg.changes[0].severity == Severity.BREAKING  # herda a base
    assert pq.changes[0].severity == Severity.SAFE  # seção parquet sobrescreve


def test_apply_policy_without_engine_uses_base_only():
    # backward-compat: sem engine, seções são ignoradas (comportamento pré-v0.3.0).
    policy = Policy(
        overrides={"column_removed": "BREAKING"},
        parquet=ParquetPolicy(overrides={"column_removed": "SAFE"}),
    )
    res = DiffResult(changes=[_change(Severity.WARNING, change_type=ChangeType.COLUMN_REMOVED)])
    out = apply_policy(res, policy)
    assert out.changes[0].severity == Severity.BREAKING
