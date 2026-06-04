"""
Carrega configurações para driftbrake.yml.

Suporta todas as opções de controle de comportamento de comparação, filtragem
e limiares de falha.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from driftbrake.exceptions import ConfigurationError
from driftbrake.models import Severity

DEFAULT_FAIL_ON = [Severity.BREAKING]
DEFAULT_WARN_ON = [Severity.WARNING]


class Settings:
    """
    Configurações carregadas do driftbrake.yml.

    fail_on: Lista de níveis de severidade que devem causar saída não-zero.
    warn_on: Lista de níveis de severidade que devem exibir avisos.
    schemas_include: Lista de schemas a incluir (vazio = todos).
    schemas_exclude: Lista de schemas a excluir.
    tables_ignore: Lista de nomes de tabelas a ignorar.
    columns_ignore: Dicionário mapeando padrões de tabela para listas de colunas ignoradas.
    rules: Sobrescritas de regras personalizadas.
    """

    def __init__(
        self,
        fail_on: list[Severity] | None = None,
        warn_on: list[Severity] | None = None,
        schemas_include: list[str] | None = None,
        schemas_exclude: list[str] | None = None,
        tables_ignore: list[str] | None = None,
        columns_ignore: dict[str, list[str]] | None = None,
        rules: dict[str, Any] | None = None,
    ) -> None:
        self.fail_on = fail_on if fail_on is not None else DEFAULT_FAIL_ON
        self.warn_on = warn_on if warn_on is not None else DEFAULT_WARN_ON
        self.schemas_include = schemas_include or []
        self.schemas_exclude = schemas_exclude or []
        self.tables_ignore = tables_ignore or []
        self.columns_ignore = columns_ignore or {}
        self.rules = rules or {}

    @classmethod
    def defaults(cls) -> Settings:
        # Retorna um objeto Settings com todos os valores padrão.
        return cls()

    @classmethod
    def from_file(cls, path: str | Path) -> Settings:
        """
        Carrega as configurações de um arquivo YAML.

        ConfigurationError: Se o arquivo for inválido ou estiver faltando valores obrigatórios.
        """
        path = Path(path)
        if not path.exists():
            raise ConfigurationError(
                f"Configuration file not found: {path}\n"
                "Create a driftbrake.yml file or use driftbrake.example.yml as a template."
            )

        try:
            import yaml  # type: ignore[import]
        except ImportError as exc:
            raise ConfigurationError(
                "PyYAML is required to load configuration files. "
                "Install it with: pip install pyyaml"
            ) from exc

        try:
            with path.open("r", encoding="utf-8") as f:
                raw: dict[str, Any] = yaml.safe_load(f) or {}
        except Exception as exc:
            raise ConfigurationError(f"Failed to parse YAML config: {path}\n{exc}") from exc

        return cls._parse(raw, path)

    @classmethod
    def _parse(cls, raw: dict[str, Any], path: Path) -> Settings:
        def parse_severities(values: list[str] | None) -> list[Severity]:
            if not values:
                return []
            result = []
            for v in values:
                try:
                    result.append(Severity(v.upper()))
                except ValueError:
                    raise ConfigurationError(
                        f"Invalid severity value '{v}' in {path}. "
                        f"Valid values: {[s.value for s in Severity]}"
                    )
            return result

        fail_on_raw = raw.get("fail_on", ["BREAKING"])
        warn_on_raw = raw.get("warn_on", ["WARNING"])
        fail_on = parse_severities(fail_on_raw) if fail_on_raw else DEFAULT_FAIL_ON
        warn_on = parse_severities(warn_on_raw) if warn_on_raw else DEFAULT_WARN_ON

        schema_cfg = raw.get("schemas", {})
        schemas_include = schema_cfg.get("include", []) if isinstance(schema_cfg, dict) else []
        schemas_exclude = schema_cfg.get("exclude", []) if isinstance(schema_cfg, dict) else []

        table_cfg = raw.get("tables", {})
        tables_ignore = table_cfg.get("ignore", []) if isinstance(table_cfg, dict) else []

        column_cfg = raw.get("columns", {})
        columns_ignore = column_cfg.get("ignore", {}) if isinstance(column_cfg, dict) else {}

        # Detecta formato v0.0.2 (tables.ignore / columns.ignore aninhados).
        # O formato v0.1.0 usa driftbrake.policy.yml com ignore_tables / ignore_columns planos.
        if isinstance(table_cfg, dict) and "ignore" in table_cfg:
            warnings.warn(
                f"'{path}' uses the v0.0.2 config format (tables.ignore / columns.ignore). "
                "This format is deprecated and will be removed in v0.2.0. "
                "Migrate to driftbrake.policy.yml with ignore_tables / ignore_columns. "
                "See DOCUMENTATION.md § 'Policy files' for details.",
                DeprecationWarning,
                stacklevel=4,
            )
        elif isinstance(column_cfg, dict) and "ignore" in column_cfg:
            warnings.warn(
                f"'{path}' uses the v0.0.2 config format (tables.ignore / columns.ignore). "
                "This format is deprecated and will be removed in v0.2.0. "
                "Migrate to driftbrake.policy.yml with ignore_tables / ignore_columns. "
                "See DOCUMENTATION.md § 'Policy files' for details.",
                DeprecationWarning,
                stacklevel=4,
            )

        rules = raw.get("rules", {})

        return cls(
            fail_on=fail_on,
            warn_on=warn_on,
            schemas_include=schemas_include,
            schemas_exclude=schemas_exclude,
            tables_ignore=tables_ignore,
            columns_ignore=columns_ignore,
            rules=rules,
        )

    def should_fail(self, severity: Severity) -> bool:
        return severity in self.fail_on

    def should_warn(self, severity: Severity) -> bool:
        return severity in self.warn_on
