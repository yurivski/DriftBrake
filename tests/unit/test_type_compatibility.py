"""
Testes unitários para a matriz de compatibilidade de tipos.
Pra evitar que o arquivo fique muito grande, apenas as chamadas com argumentos
acima de 100 caracteres terão quebras de linhas.
"""

import pytest

from driftbrake.core.type_compatibility import _canonicalize_type, classify_type_change
from driftbrake.models import Severity


class TestVarcharChanges:
    def test_varchar_widening_is_safe(self):
        assert classify_type_change("VARCHAR(50)", "VARCHAR(100)") == Severity.SAFE

    def test_varchar_narrowing_is_breaking(self):
        assert classify_type_change("VARCHAR(100)", "VARCHAR(50)") == Severity.BREAKING

    def test_varchar_same_length_is_safe(self):
        assert classify_type_change("VARCHAR(100)", "VARCHAR(100)") == Severity.SAFE

    def test_varchar_to_text_is_safe(self):
        assert classify_type_change("VARCHAR(100)", "TEXT") == Severity.SAFE

    def test_text_to_varchar_is_breaking(self):
        assert classify_type_change("TEXT", "VARCHAR(100)") == Severity.BREAKING


class TestIntegerChanges:
    def test_integer_to_bigint_is_warning(self):
        assert classify_type_change("integer", "bigint") == Severity.WARNING

    def test_bigint_to_integer_is_breaking(self):
        assert classify_type_change("bigint", "integer") == Severity.BREAKING

    def test_smallint_to_integer_is_safe(self):
        assert classify_type_change("smallint", "integer") == Severity.SAFE

    def test_smallint_to_bigint_is_safe(self):
        assert classify_type_change("smallint", "bigint") == Severity.SAFE

    def test_integer_to_smallint_is_breaking(self):
        assert classify_type_change("integer", "smallint") == Severity.BREAKING


class TestNumericChanges:
    def test_numeric_precision_widening_is_safe(self):
        assert classify_type_change("NUMERIC(10,2)", "NUMERIC(12,2)") == Severity.SAFE

    def test_numeric_precision_narrowing_is_breaking(self):
        assert classify_type_change("NUMERIC(12,2)", "NUMERIC(10,2)") == Severity.BREAKING

    def test_numeric_same_is_safe(self):
        assert classify_type_change("NUMERIC(10,2)", "NUMERIC(10,2)") == Severity.SAFE

    def test_numeric_to_text_is_breaking(self):
        assert classify_type_change("numeric", "text") == Severity.BREAKING

    def test_text_to_numeric_is_breaking(self):
        assert classify_type_change("text", "numeric") == Severity.BREAKING


class TestDateTimeChanges:
    def test_date_to_timestamp_is_warning(self):
        assert classify_type_change("date", "timestamp") == Severity.WARNING

    def test_timestamp_to_date_is_breaking(self):
        assert classify_type_change("timestamp", "date") == Severity.BREAKING

    def test_timestamp_to_timestamptz_is_warning(self):
        assert classify_type_change("timestamp", "timestamptz") == Severity.WARNING


class TestIdenticalTypes:
    def test_same_type_is_safe(self):
        assert classify_type_change("INTEGER", "INTEGER") == Severity.SAFE
        assert classify_type_change("TEXT", "TEXT") == Severity.SAFE
        assert classify_type_change("BOOLEAN", "BOOLEAN") == Severity.SAFE

    def test_same_type_case_insensitive(self):
        assert classify_type_change("integer", "INTEGER") == Severity.SAFE
        assert classify_type_change("Varchar(50)", "VARCHAR(50)") == Severity.SAFE


class TestBooleanChanges:
    def test_boolean_to_integer_is_breaking(self):
        assert classify_type_change("boolean", "integer") == Severity.BREAKING

    def test_integer_to_boolean_is_breaking(self):
        assert classify_type_change("integer", "boolean") == Severity.BREAKING


class TestUnknownTypeFallback:
    def test_completely_different_types_are_breaking(self):
        assert classify_type_change("uuid", "bytea") == Severity.BREAKING
        assert classify_type_change("jsonb", "text") == Severity.BREAKING


class TestTypeCanonicalizer:
    """Garante que aliases do catálogo do PostgreSQL sejam normalizados para o nome canônico.

    Se o SQLAlchemy emitir um alias em vez do nome padrão entre uma leitura e outra,
    o comparador NÃO deve gerar um type_changed fantasma.
    """

    @pytest.mark.parametrize(
        "alias, canonical",
        [
            ("character varying", "varchar"),
            ("character varying(100)", "varchar(100)"),
            ("character varying(255)", "varchar(255)"),
            ("decimal", "numeric"),
            ("decimal(10,2)", "numeric(10,2)"),
            ("decimal(18,4)", "numeric(18,4)"),
            ("int8", "bigint"),
            ("int4", "integer"),
            ("int2", "smallint"),
            ("float8", "double precision"),
            ("float4", "real"),
            ("bool", "boolean"),
            ("timestamp without time zone", "timestamp"),
            ("timestamp with time zone", "timestamptz"),
            ("time without time zone", "time"),
            ("time with time zone", "timetz"),
            ("character", "char"),
            ("character(10)", "char(10)"),
            ("bpchar", "char"),  # nome interno de char(n) via pg_catalog
            ("bpchar(10)", "char(10)"),
        ],
    )
    def test_alias_maps_to_canonical(self, alias: str, canonical: str):
        assert _canonicalize_type(alias) == canonical

    def test_bpchar_does_not_produce_phantom_type_changed(self):
        # char(10) relido como bpchar(10) via pg_catalog não deve gerar type_changed
        assert classify_type_change("char(10)", "bpchar(10)") == Severity.SAFE
        assert classify_type_change("bpchar(10)", "char(10)") == Severity.SAFE

    @pytest.mark.parametrize(
        "alias_a, alias_b",
        [
            # Par de aliases que representam o MESMO tipo — diff deve ser SAFE
            ("character varying(100)", "VARCHAR(100)"),
            # decimal é alias exato de numeric no catálogo do PostgreSQL
            ("decimal", "numeric"),
            ("decimal(10,2)", "NUMERIC(10,2)"),
            ("decimal(10,2)", "numeric(10,2)"),
            ("int4", "INTEGER"),
            ("int8", "BIGINT"),
            ("bool", "BOOLEAN"),
            ("timestamp without time zone", "TIMESTAMP"),
            ("timestamp with time zone", "TIMESTAMPTZ"),
            ("float8", "double precision"),
            ("float4", "REAL"),
        ],
    )
    def test_equivalent_aliases_produce_no_diff(self, alias_a: str, alias_b: str):
        """Ler o mesmo banco duas vezes com representações distintas não gera type_changed."""
        assert classify_type_change(alias_a, alias_b) == Severity.SAFE
        assert classify_type_change(alias_b, alias_a) == Severity.SAFE
