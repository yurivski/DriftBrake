"""
Matriz de compatibilidade sobre `CanonicalType`.

A matriz deixa de comparar strings e passa a raciocinar sobre **capacidade de
range**. Duas camadas: mesma base (refino por params/tz/unit) e cross-base.
Decisões marcadas com [DIFERENCIAL] são onde a precisão venceu o conservadorismo.
"""

from __future__ import annotations

from driftbrake.core.models import Severity
from driftbrake.core.type_system import CanonicalBase, CanonicalType

_SI = CanonicalBase.SMALLINT.value
_IN = CanonicalBase.INTEGER.value
_BI = CanonicalBase.BIGINT.value
_REAL = CanonicalBase.REAL.value
_DBL = CanonicalBase.DOUBLE.value
_NUM = CanonicalBase.NUMERIC.value
_CHAR = CanonicalBase.CHAR.value
_VARCHAR = CanonicalBase.VARCHAR.value
_TEXT = CanonicalBase.TEXT.value
_DATE = CanonicalBase.DATE.value
_TIME = CanonicalBase.TIME.value
_TS = CanonicalBase.TIMESTAMP.value
_BOOL = CanonicalBase.BOOLEAN.value
_JSON = CanonicalBase.JSON.value
_OPAQUE = CanonicalBase.OPAQUE.value

_INT_BASES = (_SI, _IN, _BI)
_FLOAT_WIDTH = {_REAL: 1, _DBL: 2}
_TIME_UNIT = {"s": 1, "ms": 2, "us": 3, "ns": 4}

# Limiar do cliente de largura fixa. [DECISÃO] manter 31: aviso mais útil, mais
# barato de relaxar via policy depois. Acima dele, ampliar inteiro vira WARNING.
SAFE_CLIENT_BITS = 31

_CROSS_BASE_FIXED: dict[tuple[str, str], Severity] = {
    (_VARCHAR, _TEXT): Severity.SAFE,
    (_CHAR, _TEXT): Severity.SAFE,
    (_TEXT, _VARCHAR): Severity.BREAKING,
    (_TEXT, _CHAR): Severity.BREAKING,
    (_DATE, _TS): Severity.WARNING,
    (_TS, _DATE): Severity.BREAKING,
    (_NUM, _TEXT): Severity.BREAKING,
    (_TEXT, _NUM): Severity.BREAKING,
    (_IN, _TEXT): Severity.WARNING,
    (_BI, _TEXT): Severity.WARNING,
}


def classify_type_change(old: CanonicalType, new: CanonicalType) -> Severity:
    if old == new:
        return Severity.SAFE
    if old.base == _OPAQUE or new.base == _OPAQUE:
        return Severity.BREAKING
    if old.base == new.base:
        return _same_base_severity(old, new)
    return _cross_base_severity(old, new)


# Camada 1: mesma base (refino por params/tz/unit)


def _same_base_severity(old: CanonicalType, new: CanonicalType) -> Severity:
    base = old.base
    if base in _INT_BASES:
        return _int_range_severity(old, new)
    if base == _NUM:
        return _numeric_severity(old, new)
    if base in (_VARCHAR, _CHAR):
        return _string_length_severity(old, new)
    if base in (_TS, _TIME):
        return _temporal_severity(old, new)
    if base == _JSON:
        return _json_severity(old, new)
    return Severity.BREAKING


def _numeric_severity(old: CanonicalType, new: CanonicalType) -> Severity:
    """numeric(precision, scale). v0.1.1: redução de precisão OU qualquer
    mudança de escala = BREAKING; ampliação de precisão com escala intacta = SAFE."""
    if not old.params and new.params:
        return Severity.BREAKING  # numeric livre -> numeric(10,2): passa a estourar
    if old.params and not new.params:
        return Severity.SAFE  # numeric(10,2) -> numeric livre: amplia
    old_prec, old_scale = (old.params + (0, 0))[:2]
    new_prec, new_scale = (new.params + (0, 0))[:2]
    if new_prec < old_prec or new_scale != old_scale:
        return Severity.BREAKING
    return Severity.SAFE


def _string_length_severity(old: CanonicalType, new: CanonicalType) -> Severity:
    """varchar(n)/char(n). Ampliar = SAFE, reduzir = BREAKING."""
    old_len = old.params[0] if old.params else None
    new_len = new.params[0] if new.params else None
    if old_len is None or new_len is None:
        if old_len is None and new_len is not None:
            return Severity.BREAKING  # ilimitado -> varchar(n): restringe
        return Severity.SAFE
    return Severity.BREAKING if new_len < old_len else Severity.SAFE


def _temporal_severity(old: CanonicalType, new: CanonicalType) -> Severity:
    """timestamp/time. tz muda = WARNING. unidade: ampliar precisão = WARNING,
    reduzir = BREAKING. (Regra nova do Parquet/Arrow.)"""
    if old.tz != new.tz:
        return Severity.WARNING
    old_u = _TIME_UNIT.get(old.unit or "us", 3)
    new_u = _TIME_UNIT.get(new.unit or "us", 3)
    if new_u < old_u:
        return Severity.BREAKING  # us -> ms: trunca precisão
    if new_u > old_u:
        return Severity.WARNING  # ms -> us: amplia
    return Severity.SAFE


def _json_severity(old: CanonicalType, new: CanonicalType) -> Severity:
    """json (binary_json=False) <-> jsonb (binary_json=True). v0.1.1:
    json -> jsonb = SAFE; jsonb -> json = WARNING (perde indexabilidade)."""
    if old.binary_json and not new.binary_json:
        return Severity.WARNING  # jsonb -> json
    return Severity.SAFE


# Camada 2: cross-base


def _cross_base_severity(old: CanonicalType, new: CanonicalType) -> Severity:
    o, n = old.base, new.base
    if o in _INT_BASES and n in _INT_BASES:  # [DIFERENCIAL] range, não par nominal
        return _int_range_severity(old, new)
    if o in _FLOAT_WIDTH and n in _FLOAT_WIDTH:
        return Severity.SAFE if _FLOAT_WIDTH[n] > _FLOAT_WIDTH[o] else Severity.BREAKING
    if (o, n) in _CROSS_BASE_FIXED:
        return _CROSS_BASE_FIXED[(o, n)]
    return Severity.BREAKING  # par desconhecido: falha barulhenta


def _int_range_severity(old: CanonicalType, new: CanonicalType) -> Severity:
    """[DIFERENCIAL] Classifica transição inteira pela CAPACIDADE DE RANGE positivo.

    smallint -> integer : amplia -> SAFE
    integer  -> bigint  : amplia, cliente de 32 bits pode estourar -> WARNING
    smallint -> bigint  : cruza limiar de 32 bits -> WARNING
    bigint   -> integer : reduz -> BREAKING
    uint32   -> bigint  : 32 bits positivos cabem em 63 -> SAFE
    uint32   -> integer : 32 bits positivos NÃO cabem em 31 -> BREAKING
    uint64   -> bigint  : 64 bits positivos NÃO cabem em 63 -> BREAKING
    """
    old_cap = old.positive_max_bits()
    new_cap = new.positive_max_bits()
    if old_cap is None or new_cap is None:
        return Severity.BREAKING
    if new_cap < old_cap:
        return Severity.BREAKING  # redução de capacidade
    if new_cap <= SAFE_CLIENT_BITS:
        return Severity.SAFE
    if old_cap <= SAFE_CLIENT_BITS < new_cap:
        return Severity.WARNING  # cruzou o limiar de 32 bits do cliente
    return Severity.SAFE  # ambos > 31 bits, ampliando dentro de 64
