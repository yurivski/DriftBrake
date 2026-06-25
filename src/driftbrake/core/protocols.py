"""
Protocolos de fronteira do core agnóstico.

`Reporter`/`Prompter` (saída e decisões interativas) + os protocolos estruturais
do core: `SchemaReader` e `TypeAdapter`. O `TypeAdapter` é a peça que cada engine
implementa para traduzir seu tipo nativo para o canônico neutro.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from driftbrake.core.type_system import CanonicalType


@runtime_checkable
class Reporter(Protocol):
    """Saída visual / observabilidade. Sem retorno — apenas efeito colateral."""

    def on_no_drift(self, result) -> None: ...
    def on_safe(self, result) -> None: ...
    def on_warning(self, result) -> None: ...
    def on_breaking(self, result) -> None: ...
    def on_contract_missing(self, contract_path: str) -> None: ...
    def on_contract_created(self, contract_path: str) -> None: ...
    def on_released(self) -> None: ...
    def on_blocked(self, reason: str) -> None: ...


@runtime_checkable
class Prompter(Protocol):
    """Decisões interativas. Retorna bool (True = prosseguir)."""

    def confirm_create_contract(self, contract_path: str) -> bool: ...
    def confirm_continue_with_warnings(self, result) -> bool: ...
    def confirm_continue_with_safe(self, result) -> bool: ...


@runtime_checkable
class SchemaReader(Protocol):
    """Lê uma fonte e devolve sempre um `DatabaseSchema` (modelo neutro)."""

    def read(self): ...


@runtime_checkable
class TypeAdapter(Protocol):
    def to_canonical(self, native_type: object) -> CanonicalType:
        """Traduz o tipo nativo do engine para o canônico neutro.

        `native_type` é `object` de propósito: string no Postgres ("int4"),
        `pa.DataType` no Arrow. Cada adapter sabe o tipo concreto que recebe.

        Regra: o `core/comparator` nunca chama adapter. Os adapters rodam no
        reader, na fronteira de entrada; a partir dali tudo é canônico.
        """
        ...


__all__ = ["Reporter", "Prompter", "SchemaReader", "TypeAdapter"]
