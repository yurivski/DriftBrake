"""Serialização canônica: __str__ / from_string, com foco na unidade temporal."""

import pytest

from driftbrake.core.type_system import CanonicalType


@pytest.mark.parametrize(
    "ct, expected",
    [
        (CanonicalType(base="integer", bits=32), "integer"),
        (CanonicalType(base="numeric", params=(10, 2)), "numeric(10,2)"),
        (CanonicalType(base="varchar", params=(100,)), "varchar(100)"),
        (CanonicalType(base="timestamp"), "timestamp"),
        (CanonicalType(base="timestamp", tz=True), "timestamp with time zone"),
        (CanonicalType(base="timestamp", unit="us"), "timestamp(us)"),
        (CanonicalType(base="timestamp", unit="ms", tz=True), "timestamp(ms) with time zone"),
        (CanonicalType(base="time", unit="ns"), "time(ns)"),
    ],
)
def test_str_serialization(ct, expected):
    assert str(ct) == expected


def test_postgres_timestamp_contract_unchanged():
    # Postgres não define unit, então o contrato continua "timestamp [with time zone]"
    assert str(CanonicalType(base="timestamp")) == "timestamp"
    assert str(CanonicalType(base="timestamp", tz=True)) == "timestamp with time zone"


@pytest.mark.parametrize(
    "text, base, unit, tz",
    [
        ("timestamp", "timestamp", None, False),
        ("timestamp with time zone", "timestamp", None, True),
        ("timestamp(us)", "timestamp", "us", False),
        ("timestamp(ms) with time zone", "timestamp", "ms", True),
        ("time(ns)", "time", "ns", False),
        ("timestamptz", "timestamp", None, True),
    ],
)
def test_from_string_temporal(text, base, unit, tz):
    ct = CanonicalType.from_string(text)
    assert ct.base == base
    assert ct.unit == unit
    assert ct.tz == tz


def test_timestamp_unit_round_trips():
    for unit in ("s", "ms", "us", "ns"):
        ct = CanonicalType(base="timestamp", unit=unit)
        assert CanonicalType.from_string(str(ct)).unit == unit


def test_from_string_reconstructs_int_bits_and_numeric_params():
    assert CanonicalType.from_string("integer").bits == 32
    assert CanonicalType.from_string("numeric(10,2)").params == (10, 2)
    assert CanonicalType.from_string("geometry").base == "opaque"
