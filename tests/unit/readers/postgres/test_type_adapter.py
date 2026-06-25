"""PostgresTypeAdapter: aliases -> base canônica tipada (migra a _PG_ALIASES)."""

import pytest

from driftbrake.readers.postgres.type_adapter import PostgresTypeAdapter

A = PostgresTypeAdapter()


@pytest.mark.parametrize(
    "alias, base",
    [
        ("character varying", "varchar"),
        ("character", "char"),
        ("decimal", "numeric"),
        ("int8", "bigint"),
        ("int4", "integer"),
        ("int2", "smallint"),
        ("float8", "double precision"),
        ("float4", "real"),
        ("bool", "boolean"),
        ("timestamp without time zone", "timestamp"),
        ("timestamp with time zone", "timestamp"),
        ("time without time zone", "time"),
        ("time with time zone", "time"),
    ],
)
def test_alias_maps_to_canonical(alias, base):
    # v0.1.1 testava _canonicalize_type(...) == str; agora é base tipada
    assert A.to_canonical(alias).base == base


@pytest.mark.parametrize(
    "alias, base",
    [
        ("int", "integer"),
        ("serial4", "integer"),
        ("serial8", "bigint"),
        ("bigserial", "bigint"),
        ("serial2", "smallint"),
        ("smallserial", "smallint"),
        ("bpchar", "char"),  # nome interno via pg_catalog, sem ele, char(10) vira drift fantasma
    ],
)
def test_missing_aliases_added(alias, base):
    assert A.to_canonical(alias).base == base


def test_int_bases_get_bits_for_range_matrix():
    assert A.to_canonical("smallint").bits == 16
    assert A.to_canonical("integer").bits == 32
    assert A.to_canonical("bigint").bits == 64
    assert A.to_canonical("integer").signed is True


def test_params_and_tz_preserved():
    vc = A.to_canonical("character varying(100)")
    assert vc.base == "varchar"
    assert vc.params == (100,)
    num = A.to_canonical("decimal(10,2)")
    assert num.base == "numeric"
    assert num.params == (10, 2)
    assert A.to_canonical("timestamp with time zone").tz is True
    assert A.to_canonical("timestamptz").tz is True


def test_jsonb_distinguished_from_json():
    assert A.to_canonical("jsonb").binary_json is True
    assert A.to_canonical("json").binary_json is False


def test_unknown_type_is_opaque_preserving_name():
    ct = A.to_canonical("geometry")
    assert ct.base == "opaque"
    assert ct.unit == "geometry"
