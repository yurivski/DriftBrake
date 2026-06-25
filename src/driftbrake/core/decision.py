from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Action = Literal["release", "ask", "block"]
Severity = Literal["none", "safe", "warning", "breaking"]


@dataclass(frozen=True)
class Decision:
    action: Action
    severity: Severity
    reason: str
    exit_code: int | None = None  # preenchido apenas se action == "block"


def decide(
    result,
    fail_on: list[str],
    ask_on: list[str],
    interactive_effective: bool,
) -> Decision:
    """
    Recebe resultado + config. Retorna Decision.
    Não imprime, não pergunta, não levanta exceção.

    Avalia a severidade mais alta presente e aplica as regras na ordem:
      0. Nenhuma mudança -> release (severity=none)
      1. severity ∈ fail_on -> block
      2. severity ∈ ask_on + interactive -> ask
      3. caso contrário -> release
    """
    # Determina a severidade mais alta
    if result.has_breaking:
        severity: Severity = "breaking"
    elif result.has_warnings:
        severity = "warning"
    elif result.has_safe:
        severity = "safe"
    else:
        severity = "none"

    if severity == "none":
        return Decision(
            action="release",
            severity="none",
            reason="No schema drift detected.",
        )

    sev_upper = severity.upper()

    if sev_upper in fail_on:
        return Decision(
            action="block",
            severity=severity,
            reason=f"{sev_upper} in fail_on.",
            exit_code=2,
        )

    if sev_upper in ask_on and interactive_effective:
        return Decision(
            action="ask",
            severity=severity,
            reason=f"{sev_upper} changes detected.",
        )

    return Decision(
        action="release",
        severity=severity,
        reason=f"{sev_upper} changes detected but not in fail_on or ask_on.",
    )
