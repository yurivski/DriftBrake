"""
Núcleo agnóstico do DriftBrake.

Regra: nada em `core/` importa de `readers/`. A dependência vai
num sentido só: readers conhecem o core, o core nunca conhece um engine.

Aqui vivem as peças neutras: o sistema de tipos canônico (`type_system`), a
matriz de compatibilidade por capacidade de range (`type_matrix`) e os
protocolos de fronteira (`protocols`).
"""

from driftbrake.core.type_matrix import classify_type_change
from driftbrake.core.type_system import CanonicalBase, CanonicalType

__all__ = ["CanonicalType", "CanonicalBase", "classify_type_change"]
