"""
Matriz de compatibilidade de tipos PostgreSQL.

Classifica alterações de tipo como SAFE, WARNING ou BREAKING com base nas
regras de coerção e cast implícito do PostgreSQL.
"""

from __future__ import annotations

import re

from driftbrake.core.models import Severity

# Regras de compatibilidade explícitas como triplas (from_pattern, to_pattern, severity).
# Os padrões são comparados sem diferenciação de maiúsculas usando substring ou regex.
_COMPAT_RULES: list[tuple[str, str, Severity]] = [
    # Expansões de VARCHAR: seguro
    ("varchar", "text", Severity.SAFE),
    ("character varying", "text", Severity.SAFE),
    # Alargamento numérico: seguro (tipos menores promovidos)
    ("smallint", "integer", Severity.SAFE),
    ("smallint", "bigint", Severity.SAFE),
    ("real", "double precision", Severity.SAFE),
    # Estreitamento numérico: crítico
    ("bigint", "integer", Severity.BREAKING),
    ("bigint", "smallint", Severity.BREAKING),
    ("integer", "smallint", Severity.BREAKING),
    ("double precision", "real", Severity.BREAKING),
    # integer -> bigint: aviso (alargamento, mas pode afetar o comportamento da app / tipos ORM)
    ("integer", "bigint", Severity.WARNING),
    # Data/hora: date -> timestamp é aviso (sem perda de dados, mas semântica muda)
    ("date", "timestamp", Severity.WARNING),
    ("timestamp", "date", Severity.BREAKING),
    ("timestamp", "timestamptz", Severity.WARNING),
    ("timestamptz", "timestamp", Severity.WARNING),
    # Estreitamento de text/varchar: crítico
    ("text", "varchar", Severity.BREAKING),
    ("text", "character varying", Severity.BREAKING),
    ("text", "numeric", Severity.BREAKING),
    ("text", "integer", Severity.BREAKING),
    ("text", "bigint", Severity.BREAKING),
    # numeric para text: crítico
    ("numeric", "text", Severity.BREAKING),
    ("integer", "text", Severity.WARNING),
    ("bigint", "text", Severity.WARNING),
    # Alterações de boolean: crítico
    ("boolean", "integer", Severity.BREAKING),
    ("integer", "boolean", Severity.BREAKING),
]


# Aliases do catálogo do PostgreSQL -> nome canônico usado internamente.
# Garante que leituras via SQLAlchemy em versões diferentes (ou via pg_catalog)
# produzam o mesmo token e não gerem type_changed fantasma.
_PG_ALIASES: list[tuple[str, str]] = [
    ("character varying", "varchar"),
    ("character", "char"),
    ("bpchar", "char"),  # nome interno de char(n) no pg_catalog; evita type_changed fantasma
    ("decimal", "numeric"),  # alias exato no catálogo do PostgreSQL; deve vir antes de "numeric"
    ("int8", "bigint"),
    ("int4", "integer"),
    ("int2", "smallint"),
    ("int", "integer"),  # alias SQL-padrão de int4
    # serial: o catálogo devolve o inteiro subjacente. Canonicalizar aqui
    # mantém o caminho legado e o PostgresTypeAdapter falando a mesma língua.
    ("bigserial", "bigint"),
    ("smallserial", "smallint"),
    ("serial8", "bigint"),
    ("serial4", "integer"),
    ("serial2", "smallint"),
    ("serial", "integer"),
    ("float8", "double precision"),
    ("float4", "real"),
    ("bool", "boolean"),
    ("timestamp without time zone", "timestamp"),
    ("timestamp with time zone", "timestamptz"),
    ("time without time zone", "time"),
    ("time with time zone", "timetz"),
]


def _canonicalize_type(type_str: str) -> str:
    """Mapeia aliases do catálogo do PostgreSQL para o nome canônico.

    character varying(N) -> varchar(N); int4 -> integer; etc.
    Chamado antes de qualquer comparação para evitar falso-positivo de type_changed.
    """
    s = type_str.strip().lower()
    for alias, canonical in _PG_ALIASES:
        # Substitui o alias preservando parâmetros: "character varying(100)" -> "varchar(100)"
        if s == alias:
            return canonical
        if s.startswith(alias + "(") and s.endswith(")"):
            return canonical + s[len(alias) :]
    return s


def _normalize_type(type_str: str) -> str:
    # Canonicaliza aliases e normaliza para minúsculas sem espaços extras.
    return _canonicalize_type(type_str)


def _extract_varchar_length(type_str: str) -> int | None:
    # Extrai o comprimento de VARCHAR(n) ou CHARACTER VARYING(n).
    match = re.search(r"(?:varchar|character varying)\s*\((\d+)\)", type_str, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _extract_numeric_precision(type_str: str) -> tuple[int, int] | None:
    # Extrai (precisão, escala) de NUMERIC(p, s) ou DECIMAL(p, s).
    match = re.search(r"(?:numeric|decimal)\s*\((\d+)\s*,\s*(\d+)\)", type_str, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


# Pares exatos (sobre nomes já canonicalizados) que o casamento por substring de
# _COMPAT_RULES não expressa com segurança ("json" é substring de "jsonb",
# "time" de "timestamp"). Mantém o caminho legado de acordo com a matriz canônica
# e com a doc (json<->jsonb, char->text, time<->timetz).
_EXACT_PAIRS: dict[tuple[str, str], Severity] = {
    ("json", "jsonb"): Severity.SAFE,
    ("jsonb", "json"): Severity.WARNING,
    ("char", "text"): Severity.SAFE,
    ("time", "timetz"): Severity.WARNING,
    ("timetz", "time"): Severity.WARNING,
}


def classify_type_change(old_type: str, new_type: str) -> Severity:
    # Classifica uma alteração de tipo de coluna como SAFE, WARNING ou BREAKING.
    old_norm = _normalize_type(old_type)
    new_norm = _normalize_type(new_type)

    if old_norm == new_norm:
        return Severity.SAFE

    # Pares exatos têm prioridade sobre o casamento por substring (evita colisões).
    if (old_norm, new_norm) in _EXACT_PAIRS:
        return _EXACT_PAIRS[(old_norm, new_norm)]

    # Regras de VARCHAR(n) -> VARCHAR(m)
    old_len = _extract_varchar_length(old_norm)
    new_len = _extract_varchar_length(new_norm)
    if old_len is not None and new_len is not None:
        if new_len >= old_len:
            return Severity.SAFE
        return Severity.BREAKING

    # VARCHAR(n) -> TEXT: seguro
    if old_len is not None and "text" in new_norm:
        return Severity.SAFE

    # CHAR(n) -> TEXT: seguro (ampliação; espelha a matriz canônica CHAR->TEXT)
    if old_norm.startswith("char") and new_norm == "text":
        return Severity.SAFE

    # NUMERIC(p1,s) -> NUMERIC(p2,s): seguro se p2 >= p1
    old_num = _extract_numeric_precision(old_norm)
    new_num = _extract_numeric_precision(new_norm)
    if old_num is not None and new_num is not None:
        old_prec, old_scale = old_num
        new_prec, new_scale = new_num
        if new_scale == old_scale and new_prec >= old_prec:
            return Severity.SAFE
        if new_prec < old_prec or new_scale != old_scale:
            return Severity.BREAKING

    # Aplica regras explícitas (verifica se a substring está contida)
    for from_pat, to_pat, severity in _COMPAT_RULES:
        if from_pat in old_norm and to_pat in new_norm:
            return severity

    # Padrão: alteração de tipo desconhecida é BREAKING (conservador)
    return Severity.BREAKING
