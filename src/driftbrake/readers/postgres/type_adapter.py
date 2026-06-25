"""
Adapter de tipos Postgres -> canônico neutro.

Migra a `_PG_ALIASES` da v0.1.1 para um mapa de base tipada. Preenche
`bits + signed` ao mapear bases inteiras (necessário para a matriz por range).
Tipos não reconhecidos (PostGIS, enums) viram OPAQUE preservando o nome.
"""

from __future__ import annotations

import re

from driftbrake.core.type_system import CanonicalBase, CanonicalType


class PostgresTypeAdapter:
    _ALIAS_TO_BASE = {
        "int8": CanonicalBase.BIGINT,
        "int4": CanonicalBase.INTEGER,
        "int2": CanonicalBase.SMALLINT,
        "bigint": CanonicalBase.BIGINT,
        "integer": CanonicalBase.INTEGER,
        "smallint": CanonicalBase.SMALLINT,
        "int": CanonicalBase.INTEGER,  # alias SQL-padrão de int4
        "serial4": CanonicalBase.INTEGER,
        "serial8": CanonicalBase.BIGINT,  # tipo subjacente
        "serial": CanonicalBase.INTEGER,
        "bigserial": CanonicalBase.BIGINT,
        "serial2": CanonicalBase.SMALLINT,
        "smallserial": CanonicalBase.SMALLINT,
        "float8": CanonicalBase.DOUBLE,
        "float4": CanonicalBase.REAL,
        "double precision": CanonicalBase.DOUBLE,
        "real": CanonicalBase.REAL,
        "bool": CanonicalBase.BOOLEAN,
        "boolean": CanonicalBase.BOOLEAN,
        "decimal": CanonicalBase.NUMERIC,
        "numeric": CanonicalBase.NUMERIC,  # fix da v0.1.1
        "character varying": CanonicalBase.VARCHAR,
        "varchar": CanonicalBase.VARCHAR,
        "character": CanonicalBase.CHAR,
        "char": CanonicalBase.CHAR,
        "bpchar": CanonicalBase.CHAR,  # nome interno de char(n) no pg_catalog
        "text": CanonicalBase.TEXT,
        "timestamp without time zone": CanonicalBase.TIMESTAMP,
        "timestamp with time zone": CanonicalBase.TIMESTAMP,
        "timestamp": CanonicalBase.TIMESTAMP,
        "timestamptz": CanonicalBase.TIMESTAMP,
        "time without time zone": CanonicalBase.TIME,
        "time with time zone": CanonicalBase.TIME,
        "time": CanonicalBase.TIME,
        "timetz": CanonicalBase.TIME,
        "date": CanonicalBase.DATE,
        "json": CanonicalBase.JSON,
        "jsonb": CanonicalBase.JSON,
    }
    _BITS = {
        CanonicalBase.SMALLINT: 16,
        CanonicalBase.INTEGER: 32,
        CanonicalBase.BIGINT: 64,
    }

    def to_canonical(self, native_type: str) -> CanonicalType:
        s = native_type.strip().lower()
        params: tuple[int, ...] = ()
        m = re.match(r"^([a-z ]+?)\s*\(([\d,\s]+)\)$", s)
        if m:
            name = m.group(1).strip()
            params = tuple(int(x) for x in m.group(2).split(","))
        else:
            name = s
        tz = "with time zone" in name or name == "timestamptz" or name == "timetz"
        base = self._ALIAS_TO_BASE.get(name, CanonicalBase.OPAQUE)
        if base is CanonicalBase.OPAQUE:
            return CanonicalType(base="opaque", unit=name)
        binary_json = name == "jsonb"
        bits = self._BITS.get(base)
        return CanonicalType(
            base=base.value,
            params=params,
            tz=tz,
            bits=bits,
            signed=True,
            binary_json=binary_json,
        )
