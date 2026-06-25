"""
Sistema de tipos canônico do DriftBrake (fundação multi-engine).

O canônico vira objeto estruturado (`CanonicalType`), não string. A string passa
a ser só a representação serializada para o contrato JSON. Os campos de range
(`bits`, `signed`) e o `binary_json` são internos à comparação — `__str__` os
ignora para preservar os contratos `schema.lock.json` existentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CanonicalBase(str, Enum):
    """Vocabulário neutro de bases. Cada agrupamento corresponde a uma distinção
    que a matriz precisa fazer (inteiros separados por range; char/varchar/text
    separados; real/double separados)."""

    # inteiros
    SMALLINT = "smallint"
    INTEGER = "integer"
    BIGINT = "bigint"
    # decimais / ponto flutuante
    NUMERIC = "numeric"
    REAL = "real"
    DOUBLE = "double precision"
    # texto
    CHAR = "char"
    VARCHAR = "varchar"
    TEXT = "text"
    # temporais
    DATE = "date"
    TIME = "time"
    TIMESTAMP = "timestamp"
    # booleano / binário / estruturado
    BOOLEAN = "boolean"
    BINARY = "binary"
    JSON = "json"
    # escape hatch — destino conservador para tipos não reconhecidos
    OPAQUE = "opaque"


# Bits efetivos por base inteira. None para não-inteiros.
_BASE_BITS: dict[str, int] = {
    CanonicalBase.SMALLINT.value: 16,
    CanonicalBase.INTEGER.value: 32,
    CanonicalBase.BIGINT.value: 64,
}


@dataclass(frozen=True)
class CanonicalType:
    base: str
    params: tuple[int, ...] = ()
    tz: bool = False
    unit: str | None = None
    bits: int | None = None  # largura efetiva p/ inteiros: 16/32/64
    signed: bool = True  # False só p/ unsigned do Arrow
    binary_json: bool = False  # distingue jsonb (True) de json (False)

    def positive_max_bits(self) -> int | None:
        """Bits disponíveis para valores positivos.
        signed int32 -> 31 bits positivos; unsigned int32 -> 32 bits positivos."""
        if self.bits is None:
            return None
        return self.bits if not self.signed else self.bits - 1

    def __str__(self) -> str:
        """Serialização determinística para o contrato.

        IGNORA `bits`/`signed`/`binary_json`, o JSON do contrato continua
        "integer", "numeric(10,2)". Para temporais, a `unit` (quando presente,
        só o Arrow a define) é preservada: "timestamp(us)" / "timestamp(us) with
        time zone". O Postgres não define `unit`, então seus contratos continuam
        "timestamp" / "timestamp with time zone".
        """
        base = self.base
        if base == CanonicalBase.TIMESTAMP.value or base == CanonicalBase.TIME.value:
            s = base
            if self.unit:
                s += f"({self.unit})"
            if self.tz:
                s += " with time zone"
            return s
        if self.params:
            inner = ",".join(str(p) for p in self.params)
            return f"{base}({inner})"
        return base

    @classmethod
    def from_string(cls, type_str: str) -> CanonicalType:
        """Reconstrói um CanonicalType a partir da serialização neutra.

        Inverso de `__str__` para a representação canônica. Reconstrói `bits`
        para bases inteiras e a `unit` para temporais (a serialização as carrega
        explicitamente). Não conhece aliases de engine, isso é trabalho do
        `TypeAdapter`. Tipos não reconhecidos viram OPAQUE preservando o nome.
        """
        s = type_str.strip()
        low = s.lower()

        tz = "with time zone" in low
        # isola o núcleo "base(conteúdo)" removendo o sufixo de timezone
        core = low.replace(" with time zone", "").replace(" without time zone", "").strip()
        params: tuple[int, ...] = ()
        unit: str | None = None

        inner = None
        if core.endswith(")") and "(" in core:
            head, _, tail = core.partition("(")
            core = head.strip()
            inner = tail[:-1].strip()

        # normaliza temporais
        if core.startswith("timestamp") or core in ("timestamptz",):
            name = CanonicalBase.TIMESTAMP.value
        elif (core.startswith("time") or core == "timetz") and "timestamp" not in core:
            name = CanonicalBase.TIME.value
        else:
            name = core

        if core in ("timestamptz", "timetz"):
            tz = True

        # interpreta o conteúdo entre parênteses
        if inner:
            if name in (CanonicalBase.TIMESTAMP.value, CanonicalBase.TIME.value) and inner in (
                "s",
                "ms",
                "us",
                "ns",
            ):
                unit = inner
            else:
                try:
                    params = tuple(int(x) for x in inner.split(",") if x.strip())
                except ValueError:
                    params = ()

        valid = {b.value for b in CanonicalBase}
        if name not in valid or name == CanonicalBase.OPAQUE.value:
            return cls(base=CanonicalBase.OPAQUE.value, unit=s)

        bits = _BASE_BITS.get(name)
        return cls(base=name, params=params, tz=tz, unit=unit, bits=bits, signed=True)
