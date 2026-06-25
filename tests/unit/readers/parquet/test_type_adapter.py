"""Arrow -> canônico, sem tocar arquivo."""

import pyarrow as pa

from driftbrake.readers.parquet.type_adapter import ArrowTypeAdapter

A = ArrowTypeAdapter()


def test_arrow_primitive_maps_to_canonical():
    assert A.to_canonical(pa.int32()).base == "integer"
    assert A.to_canonical(pa.int64()).base == "bigint"
    assert A.to_canonical(pa.string()).base == "text"
    assert A.to_canonical(pa.large_string()).base == "text"
    assert A.to_canonical(pa.float64()).base == "double precision"


def test_arrow_decimal_preserves_precision():
    ct = A.to_canonical(pa.decimal128(10, 2))
    assert ct.base == "numeric"
    assert ct.params == (10, 2)


def test_arrow_timestamp_unit_distinguished():
    ms = A.to_canonical(pa.timestamp("ms"))
    us = A.to_canonical(pa.timestamp("us"))
    assert ms.unit == "ms"
    assert us.unit == "us"
    assert ms.unit != us.unit


def test_arrow_unsigned_preserves_signed_flag():
    ct = A.to_canonical(pa.uint32())
    assert ct.signed is False
    assert ct.bits == 32


def test_arrow_date32_and_date64_collapse_to_date():
    # ambas as larguras físicas de date do Arrow colapsam no mesmo canônico
    assert A.to_canonical(pa.date32()).base == "date"
    assert A.to_canonical(pa.date64()).base == "date"


def test_unknown_arrow_type_is_conservative():
    assert A.to_canonical(pa.list_(pa.int32())).base == "opaque"
    assert A.to_canonical(pa.struct([("a", pa.int32())])).base == "opaque"
