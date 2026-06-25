"""Matriz de compatibilidade sobre CanonicalType: roda PRIMEIRO."""

import pytest

from driftbrake.core.type_matrix import classify_type_change
from driftbrake.core.type_system import CanonicalType
from driftbrake.models import Severity


def I(base, **kw):  # noqa: E743, N802 — helper conciso do plano v0.3.0
    bits = {"smallint": 16, "integer": 32, "bigint": 64}.get(base)
    return CanonicalType(base=base, bits=bits, signed=kw.get("signed", True))


def num(p=None, s=None):
    return CanonicalType(base="numeric", params=(p, s) if p is not None else ())


def vc(n=None):
    return CanonicalType(base="varchar", params=(n,) if n is not None else ())


def ts(tz=False, unit="us"):
    return CanonicalType(base="timestamp", tz=tz, unit=unit)


def js(binary):
    return CanonicalType(base="json", binary_json=binary)


S, W, B = Severity.SAFE, Severity.WARNING, Severity.BREAKING

PARITY_V011 = [
    (vc(50), vc(100), S),
    (vc(100), vc(50), B),
    (vc(100), CanonicalType(base="text"), S),
    (CanonicalType(base="text"), vc(100), B),
    (I("smallint"), I("integer"), S),
    (I("integer"), I("bigint"), W),
    (I("bigint"), I("integer"), B),
    (I("integer"), I("smallint"), B),
    (I("integer"), CanonicalType(base="text"), W),
    (I("bigint"), CanonicalType(base="text"), W),
    (num(10, 2), num(12, 2), S),
    (num(12, 2), num(10, 2), B),
    (num(10, 4), num(10, 2), B),
    (num(10, 2), CanonicalType(base="text"), B),
    (CanonicalType(base="date"), ts(), W),
    (ts(), CanonicalType(base="date"), B),
    (ts(tz=False), ts(tz=True), W),
    (ts(tz=True), ts(tz=False), W),
    (js(False), js(True), S),
    (js(True), js(False), W),
]


@pytest.mark.parametrize("old, new, expected", PARITY_V011)
def test_parity_with_v011(old, new, expected):
    assert classify_type_change(old, new) == expected


NEW_RULES = [
    (I("smallint"), I("bigint"), W),  # [DIFERENCIAL]
    (ts(unit="us"), ts(unit="ms"), B),
    (ts(unit="ms"), ts(unit="us"), W),
    (ts(unit="us"), ts(unit="us"), S),
    (CanonicalType(base="integer", bits=32, signed=False), I("bigint"), S),  # uint32 -> bigint
    (CanonicalType(base="integer", bits=32, signed=False), I("integer"), B),  # uint32 -> integer
    (CanonicalType(base="bigint", bits=64, signed=False), I("bigint"), B),  # uint64 -> bigint
    (
        CanonicalType(base="integer", bits=32, signed=False),
        CanonicalType(base="integer", bits=32, signed=False),
        S,
    ),
]


@pytest.mark.parametrize("old, new, expected", NEW_RULES)
def test_new_parquet_and_range_rules(old, new, expected):
    assert classify_type_change(old, new) == expected


def test_identical_types_are_safe():
    t = num(10, 2)
    assert classify_type_change(t, t) == Severity.SAFE


def test_opaque_either_side_is_breaking():
    opq = CanonicalType(base="opaque", unit="geometry")
    assert classify_type_change(opq, I("integer")) == Severity.BREAKING
    assert classify_type_change(I("integer"), opq) == Severity.BREAKING


def test_unknown_cross_base_is_breaking():
    assert classify_type_change(CanonicalType(base="boolean"), I("integer")) == Severity.BREAKING
