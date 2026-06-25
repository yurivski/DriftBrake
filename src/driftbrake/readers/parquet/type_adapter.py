"""
Adapter de tipos Arrow -> canônico neutro.

O adapter é burro de propósito: preserva `bits + signed` e deixa a matriz
calcular capacidade. `unit` do timestamp é o que captura o drift #3 (físico vs
lógico). Compostos (list/struct/map) e desconhecidos viram OPAQUE, preservando
o nome.
"""

from __future__ import annotations

import pyarrow as pa  # import lazy: só carrega quando este módulo é usado

from driftbrake.core.type_system import CanonicalBase, CanonicalType

_SI = CanonicalBase.SMALLINT.value
_IN = CanonicalBase.INTEGER.value
_BI = CanonicalBase.BIGINT.value


class ArrowTypeAdapter:
    def to_canonical(self, t: pa.DataType) -> CanonicalType:
        # inteiros — preserva largura e sinal; a matriz decide o range
        if pa.types.is_int8(t):
            return CanonicalType(base=_SI, bits=8, signed=True)
        if pa.types.is_int16(t):
            return CanonicalType(base=_SI, bits=16, signed=True)
        if pa.types.is_int32(t):
            return CanonicalType(base=_IN, bits=32, signed=True)
        if pa.types.is_int64(t):
            return CanonicalType(base=_BI, bits=64, signed=True)
        if pa.types.is_uint8(t):
            return CanonicalType(base=_SI, bits=8, signed=False)
        if pa.types.is_uint16(t):
            return CanonicalType(base=_SI, bits=16, signed=False)
        if pa.types.is_uint32(t):
            return CanonicalType(base=_IN, bits=32, signed=False)
        if pa.types.is_uint64(t):
            return CanonicalType(base=_BI, bits=64, signed=False)
        # ponto flutuante
        if pa.types.is_float32(t):
            return CanonicalType(base=CanonicalBase.REAL.value)
        if pa.types.is_float64(t):
            return CanonicalType(base=CanonicalBase.DOUBLE.value)
        # decimal — precisão e escala vêm como atributos do tipo
        if pa.types.is_decimal(t):
            return CanonicalType(base=CanonicalBase.NUMERIC.value, params=(t.precision, t.scale))
        # texto — string e large_string colapsam em texto sem limite
        if pa.types.is_string(t) or pa.types.is_large_string(t):
            return CanonicalType(base=CanonicalBase.TEXT.value)
        # temporais — AQUI mora o diferencial: a unidade
        if pa.types.is_timestamp(t):
            return CanonicalType(
                base=CanonicalBase.TIMESTAMP.value, tz=(t.tz is not None), unit=t.unit
            )
        if pa.types.is_date(t):
            return CanonicalType(base=CanonicalBase.DATE.value)
        if pa.types.is_time(t):
            return CanonicalType(base=CanonicalBase.TIME.value, unit=t.unit)
        if pa.types.is_boolean(t):
            return CanonicalType(base=CanonicalBase.BOOLEAN.value)
        if pa.types.is_binary(t) or pa.types.is_large_binary(t):
            return CanonicalType(base=CanonicalBase.BINARY.value)
        # compostos e desconhecidos -> OPAQUE, preservando o nome
        return CanonicalType(base="opaque", unit=str(t))
