"""Paridade exaustiva entre as duas matrizes de tipo.

bpchar - uma lista curada de pares não pega tudo: o par que
diverge pode estar fora da lista. Este teste varre o produto cartesiano de
todos os aliases do PostgresTypeAdapter e afirma que o caminho legado
(string + _PG_ALIASES) e o caminho novo (adapter -> CanonicalType -> type_matrix)
dão a mesma severidade para cada par, exceto um conjunto explícito de
divergências intencionais.

Se um par novo divergir, é o próximo bpchar: um bug pego antes do usuário.
Se uma divergência intencional sumir, alguém mexeu na fundação sem querer.
"""

from itertools import product

import pytest

from driftbrake.core.models import Severity
from driftbrake.core.type_compatibility import classify_type_change as legacy_classify
from driftbrake.core.type_matrix import classify_type_change as canonical_classify
from driftbrake.readers.postgres.type_adapter import PostgresTypeAdapter

_ADAPTER = PostgresTypeAdapter()
_ALIASES = sorted(_ADAPTER._ALIAS_TO_BASE.keys())

# Divergências intencionais, por par de bases canônicas (old_base, new_base).
# Cada uma é um refinamento consciente da v0.3.0 sobre a v0.1.1, não um bug.
#
# smallint -> bigint: a v0.1.1 classificava como SAFE (alargamento nominal); a
# matriz canônica por range diz WARNING (cruza o limiar de 32 bits do cliente).
# O caminho Postgres preserva o SAFE da v0.1.1; o canônico/Parquet usa WARNING.
_INTENDED: dict[tuple[str, str], tuple[Severity, Severity]] = {
    ("smallint", "bigint"): (Severity.SAFE, Severity.WARNING),
}


def _pairs():
    return list(product(_ALIASES, repeat=2))


@pytest.mark.parametrize("a, b", _pairs())
def test_legacy_and_canonical_agree(a: str, b: str):
    legacy = legacy_classify(a, b)
    canonical = canonical_classify(_ADAPTER.to_canonical(a), _ADAPTER.to_canonical(b))
    bases = (_ADAPTER.to_canonical(a).base, _ADAPTER.to_canonical(b).base)

    if bases in _INTENDED:
        expected_legacy, expected_canonical = _INTENDED[bases]
        assert (legacy, canonical) == (expected_legacy, expected_canonical), (
            f"divergência intencional mudou para {a}->{b}: "
            f"legacy={legacy.value} canonical={canonical.value}"
        )
    else:
        assert legacy == canonical, (
            f"NOVO bpchar: {a}->{b} diverge — legacy={legacy.value} canonical={canonical.value}"
        )


def test_intended_divergence_actually_occurs():
    """
    Garante que a única divergência documentada de fato aparece no produto
    cartesiano, senão o guard acima passaria vazio se os aliases sumissem.
    """
    found = False
    for a, b in _pairs():
        bases = (_ADAPTER.to_canonical(a).base, _ADAPTER.to_canonical(b).base)
        if bases == ("smallint", "bigint"):
            assert legacy_classify(a, b) == Severity.SAFE
            assert canonical_classify(_ADAPTER.to_canonical(a), _ADAPTER.to_canonical(b)) == (
                Severity.WARNING
            )
            found = True
    assert found, "smallint->bigint deveria aparecer no produto cartesiano de aliases"


def test_serial_aliases_canonicalize_in_both_paths():
    """
    O par que o bpchar previu: serial/int relidos pelo caminho legado não podem
    mais gerar type_changed fantasma contra o que o adapter grava.
    """
    for serial, base_int in [
        ("serial4", "int4"),
        ("bigserial", "int8"),
        ("smallserial", "int2"),
        ("int", "integer"),
    ]:
        assert legacy_classify(serial, base_int) == Severity.SAFE
        assert legacy_classify(base_int, serial) == Severity.SAFE
