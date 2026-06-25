"""Trava arquitetural executável: a travessia do comparador para o CanonicalType
é singular.

O docstring de `_classify_type_change` declara a regra em prosa; prosa apodrece
porque nada a força a continuar verdadeira. Este teste a torna executável: se
alguém adicionar um segundo ponto que faz parse da serialização canônica dentro
do comparador, ele quebra de propósito, o sinal de concluir a migração para o
CanonicalType, não de acumular um terceiro caso especial.

Mesma filosofia do `test_matrix_parity.py`: travar a decisão num teste em vez de
confiar que ela sobreviva num comentário.
"""

import ast
import inspect

from driftbrake.core import comparator

_SANCTIONED_SEAM = "_classify_type_change"


def _crossing_functions_and_calls() -> tuple[list[str], int]:
    """Funções do módulo comparador que cruzam para o CanonicalType (chamam
    `from_string`), e a contagem bruta de chamadas a `from_string`."""
    tree = ast.parse(inspect.getsource(comparator))

    def is_from_string(call: ast.Call) -> bool:
        return isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "from_string"

    raw_calls = sum(1 for node in ast.walk(tree) if is_from_string(node))

    crossing_fns: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if any(is_from_string(inner) for inner in ast.walk(node)):
                crossing_fns.append(node.name)
    return crossing_fns, raw_calls


def test_canonical_seam_is_singular():
    crossing_fns, raw_calls = _crossing_functions_and_calls()

    # Invariante primário: só UMA função pode cruzar para o CanonicalType.
    assert crossing_fns == [_SANCTIONED_SEAM], (
        f"Travessias para o CanonicalType no comparador: {crossing_fns}. "
        "Limite arquitetural: só _classify_type_change pode cruzar. Um segundo "
        "refinamento que a matriz de strings não expresse é o sinal de CONCLUIR "
        "a migração ao CanonicalType, não de adicionar outro caso especial. "
        "Ver o docstring de _classify_type_change."
    )

    # Tripwire secundário: a travessia sancionada parseia exatamente os dois
    # operandos (old, new). Um terceiro parse = um refinamento novo entrando
    # pela porta dos fundos. Quebre conscientemente, não por acidente.
    assert raw_calls <= 2, (
        f"{raw_calls} chamadas a from_string no comparador (esperado <= 2: old e new). "
        "Um terceiro parse indica um segundo refinamento — conclua a migração."
    )
