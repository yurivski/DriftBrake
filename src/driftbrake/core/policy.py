# Policy: overrides de severidade e listas de ignore por projeto.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from driftbrake.exceptions import PolicyError

# Override keys específicas do Parquet que apelidam change_types canônicos do
# comparador. "required" no Parquet == NOT NULL; "optional" == nullable.
_OVERRIDE_ALIASES: dict[str, str] = {
    "nullable_to_required": "not_null_constraint_added",
    "required_to_nullable": "not_null_constraint_removed",
}


@dataclass
class ParquetDatasetPolicy:
    """Configuração de consolidação de dataset Parquet (seção parquet.dataset)."""

    dominant_schema_strategy: str = "most_common"  # most_common | first_file | latest_mtime
    max_divergent_files: int = 0  # 0 = zero tolerância
    ignore_partition_columns: bool = True  # colunas de partição vêm do path


@dataclass
class PostgresPolicy:
    """Seção específica de Postgres. Sobrescreve/adiciona à base agnóstica.

    O Postgres não tem vocabulário de tipo físico nem divergência inter-arquivo,
    então a seção carrega só `overrides` — o suficiente para um usuário afinar a
    severidade de um change_type só no caminho Postgres, sem tocar no Parquet."""

    overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class ParquetPolicy:
    """Seção específica de Parquet. Sobrescreve/adiciona à base agnóstica."""

    dataset: ParquetDatasetPolicy = field(default_factory=ParquetDatasetPolicy)
    overrides: dict[str, str] = field(default_factory=dict)
    """Overrides específicos de Parquet (timestamp_unit_changed, nullable_to_required, ...)."""


@dataclass
class Policy:
    overrides: dict[str, str] = field(default_factory=dict)
    """Base agnóstica: aplica a TODOS os engines. Mapeia change_type -> severidade."""

    ignore_tables: list[str] = field(default_factory=list)
    """Tabelas a ignorar totalmente no scan."""

    ignore_columns: list[str] = field(default_factory=list)
    """Colunas a ignorar. Formato: 'tabela.coluna'."""

    postgres: PostgresPolicy | None = None
    """Seção específica de Postgres. None = só a base (comportamento atual)."""

    parquet: ParquetPolicy | None = None
    """Seção específica de Parquet. None = só a base (comportamento atual)."""

    def effective_overrides(self, engine: str | None = None) -> dict[str, str]:
        """Overrides efetivos para um engine.

        Precedência: a base aplica a todos; a seção do engine sobrescreve/adiciona
        por cima. Sem `engine` (ou engine sem seção), devolve só a base — o que
        mantém o comportamento de quem não usa seções por engine.
        """
        merged = dict(self.overrides)
        if engine == "postgres" and self.postgres is not None:
            merged.update(self.postgres.overrides)
        elif engine == "parquet" and self.parquet is not None:
            merged.update(self.parquet.overrides)
        return merged


def load_policy(path: str | None) -> Policy:
    """Carrega YAML. Se path=None, retorna Policy() vazia."""
    if path is None:
        return Policy()

    try:
        import yaml
    except ImportError as exc:
        raise PolicyError("pyyaml is required to load policy files.") from exc

    policy_path = Path(path)
    if not policy_path.exists():
        raise PolicyError(f"Policy file not found: {path}")

    try:
        with policy_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        raise PolicyError(f"Failed to parse policy file '{path}': {exc}") from exc

    if data is None:
        return Policy()

    if not isinstance(data, dict):
        raise PolicyError(f"Policy file '{path}' must be a YAML mapping.")

    valid_severities = {"BREAKING", "WARNING", "SAFE"}

    overrides: dict[str, str] = {}
    raw_overrides = data.get("overrides") or {}
    if not isinstance(raw_overrides, dict):
        raise PolicyError(f"'overrides' in '{path}' must be a mapping.")
    for key, val in raw_overrides.items():
        val_upper = str(val).upper()
        if val_upper not in valid_severities:
            raise PolicyError(
                f"Invalid severity '{val}' for override '{key}' in '{path}'. "
                f"Must be one of {valid_severities}."
            )
        overrides[str(key)] = val_upper

    ignore_tables: list[str] = []
    raw_tables = data.get("ignore_tables") or []
    if not isinstance(raw_tables, list):
        raise PolicyError(f"'ignore_tables' in '{path}' must be a list.")
    ignore_tables = [str(t) for t in raw_tables]

    ignore_columns: list[str] = []
    raw_columns = data.get("ignore_columns") or []
    if not isinstance(raw_columns, list):
        raise PolicyError(f"'ignore_columns' in '{path}' must be a list.")
    ignore_columns = [str(c) for c in raw_columns]

    postgres_policy = _parse_postgres_section(data.get("postgres"), path, valid_severities)
    parquet_policy = _parse_parquet_section(data.get("parquet"), path, valid_severities)

    return Policy(
        overrides=overrides,
        ignore_tables=ignore_tables,
        ignore_columns=ignore_columns,
        postgres=postgres_policy,
        parquet=parquet_policy,
    )


def _parse_engine_overrides(
    raw_overrides: object, section: str, path: str, valid_severities: set[str]
) -> dict[str, str]:
    """Valida e normaliza o mapa de overrides de uma seção de engine."""
    if not isinstance(raw_overrides, dict):
        raise PolicyError(f"'{section}.overrides' in '{path}' must be a mapping.")
    out: dict[str, str] = {}
    for key, val in raw_overrides.items():
        val_upper = str(val).upper()
        if val_upper not in valid_severities:
            raise PolicyError(
                f"Invalid severity '{val}' for {section} override '{key}' in '{path}'. "
                f"Must be one of {valid_severities}."
            )
        out[str(key)] = val_upper
    return out


def _parse_postgres_section(
    raw: object, path: str, valid_severities: set[str]
) -> PostgresPolicy | None:
    """Parseia a seção `postgres:`. Ausente = None (só a base, comportamento atual)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PolicyError(f"'postgres' in '{path}' must be a mapping.")
    overrides = _parse_engine_overrides(
        raw.get("overrides") or {}, "postgres", path, valid_severities
    )
    return PostgresPolicy(overrides=overrides)


def _parse_parquet_section(
    raw: object, path: str, valid_severities: set[str]
) -> ParquetPolicy | None:
    """Parseia a seção `parquet:`. Ausente = None (comportamento atual preservado)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PolicyError(f"'parquet' in '{path}' must be a mapping.")

    dataset = ParquetDatasetPolicy()
    raw_dataset = raw.get("dataset") or {}
    if not isinstance(raw_dataset, dict):
        raise PolicyError(f"'parquet.dataset' in '{path}' must be a mapping.")
    if "dominant_schema_strategy" in raw_dataset:
        strategy = str(raw_dataset["dominant_schema_strategy"])
        valid_strategies = {"most_common", "first_file", "latest_mtime"}
        if strategy not in valid_strategies:
            raise PolicyError(
                f"Invalid dominant_schema_strategy '{strategy}' in '{path}'. "
                f"Must be one of {valid_strategies}."
            )
        dataset.dominant_schema_strategy = strategy
    if "max_divergent_files" in raw_dataset:
        dataset.max_divergent_files = int(raw_dataset["max_divergent_files"])
    if "ignore_partition_columns" in raw_dataset:
        dataset.ignore_partition_columns = bool(raw_dataset["ignore_partition_columns"])

    overrides = _parse_engine_overrides(
        raw.get("overrides") or {}, "parquet", path, valid_severities
    )
    return ParquetPolicy(dataset=dataset, overrides=overrides)


def apply_policy(result, policy: Policy, engine: str | None = None):
    """
    Aplica overrides de política ao DiffResult como pós-processamento.
    Retorna um novo DiffResult com severidades e mudanças ajustadas.

    `engine` seleciona a seção específica: os overrides efetivos são a base
    agnóstica mesclada com a seção do engine ("postgres" / "parquet"). Sem
    `engine`, só a base — preservando o comportamento de quem não usa seções.
    """
    from driftbrake.core.models import DiffResult, Severity

    # Overrides efetivos = base + seção do engine. Aliases de engine -> change_type
    # canônico (a policy Parquet fala "required/optional"; o comparador emite NOT NULL).
    overrides = dict(policy.effective_overrides(engine))
    for alias, target in _OVERRIDE_ALIASES.items():
        if alias in overrides and target not in overrides:
            overrides[target] = overrides[alias]

    if not overrides and not policy.ignore_tables and not policy.ignore_columns:
        return result

    filtered = []
    for change in result.changes:
        # Ignorar tabelas
        if change.table_name in policy.ignore_tables:
            continue

        # Ignorar colunas (formato: "tabela.coluna")
        col_key = f"{change.table_name}.{change.column_name}" if change.column_name else None
        if col_key and col_key in policy.ignore_columns:
            continue

        # Aplicar override de severidade
        change_type_name = (
            change.change_type.value
            if hasattr(change.change_type, "value")
            else str(change.change_type)
        )
        if change_type_name in overrides:
            from dataclasses import replace

            new_severity = Severity(overrides[change_type_name])
            change = replace(
                change,
                severity=new_severity,
                description=f"{change.description} [overridden by policy: {new_severity.value}]",
            )

        filtered.append(change)

    return DiffResult(
        changes=filtered,
        compared_at=result.compared_at,
        expected_source=result.expected_source,
        current_source=result.current_source,
    )
