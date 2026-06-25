"""DriftBrake — fachada de alto nível sobre o SchemaGuard."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from driftbrake.core.decision import decide
from driftbrake.core.policy import Policy, apply_policy, load_policy
from driftbrake.exceptions import (
    BreakingChangesDetected,
    ContractMissingError,
    ContractWriteError,
    DriftBrakeError,
    MissingDatabaseURL,
    UserAborted,
)
from driftbrake.guard import SchemaGuard
from driftbrake.prompters import NonInteractivePrompter, StdinPrompter
from driftbrake.protocols import Prompter, Reporter
from driftbrake.reporters.facade_terminal import FacadeTerminalReporter as TerminalReporter


class DriftBrake:
    def __init__(
        self,
        database_url: str,
        contract_path: str = "schema.lock.json",
        config_path: str | None = None,
        policy_path: str | None = None,
        auto_init: bool = True,
        interactive: bool | Literal["auto"] = "auto",
        ask_on: list[str] | None = None,
        fail_on: list[str] | None = None,
        output_json: str | None = None,
        output_html: str | None = None,
        output_markdown: str | None = None,
        schemas: list[str] | None = None,
        verbose: bool = False,
        reporter: Reporter | None = None,
        prompter: Prompter | None = None,
    ) -> None:
        self.database_url = database_url
        self.contract_path = contract_path
        self.config_path = config_path
        self.auto_init = auto_init
        self._interactive_raw = interactive
        self.ask_on = [s.upper() for s in (ask_on or ["WARNING"])]
        self.fail_on = [s.upper() for s in (fail_on or ["BREAKING"])]
        self.output_json = output_json
        self.output_html = output_html
        self.output_markdown = output_markdown
        self.schemas = schemas or ["public"]
        self.verbose = verbose

        # Arquivo de política único: se nenhum caminho for dado, usa "policy.yml"
        # quando presente — a mesma convenção da CLI. Ausente = sem política.
        if policy_path is None and Path("policy.yml").exists():
            policy_path = "policy.yml"
        self.policy: Policy = load_policy(policy_path)
        self.guard = SchemaGuard(
            database_url=database_url,
            contract_path=contract_path,
            config_path=config_path,
            output_json=output_json,
            output_html=output_html,
            output_markdown=output_markdown,
            fail_on=fail_on,
            schemas=self.schemas,
        )

        self._interactive = self._resolve_interactive()
        self.reporter: Reporter = reporter or TerminalReporter(verbose=verbose)
        self.prompter: Prompter = prompter or (
            StdinPrompter() if self._interactive else NonInteractivePrompter()
        )

    # Construtores
    @classmethod
    def from_env(cls, **kwargs) -> DriftBrake:
        """
        Resolve configuração a partir de variáveis de ambiente.
        kwargs sobrescrevem valores do ambiente.
        Levanta MissingDatabaseURL se DATABASE_URL não estiver disponível.
        """
        database_url = kwargs.pop("database_url", None) or os.getenv("DATABASE_URL")
        if not database_url:
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "5432")
            name = os.getenv("DB_NAME", "")
            user = os.getenv("DB_USER", "")
            password = os.getenv("DB_PASSWORD", "")
            if name and user:
                database_url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
            else:
                raise MissingDatabaseURL(
                    "DATABASE_URL not set. Pass database_url=... or export DATABASE_URL."
                )
        return cls(database_url=database_url, **kwargs)

    # Internos
    def _resolve_interactive(self) -> bool:
        if self._interactive_raw == "auto":
            return sys.stdin.isatty() and sys.stdout.isatty()
        return bool(self._interactive_raw)

    def _contract_exists(self) -> bool:
        return Path(self.contract_path).exists()

    def _create_contract(self) -> None:
        from driftbrake.contracts.writer import ContractWriter
        from driftbrake.readers.postgres import PostgresSchemaReader

        reader = PostgresSchemaReader(
            database_url=self.database_url,
            schemas=self.schemas,
        )
        schema = reader.read()
        try:
            ContractWriter(self.contract_path).write(schema)
        except (PermissionError, OSError) as exc:
            raise ContractWriteError(
                f"Cannot write contract to {self.contract_path}: {exc}"
            ) from exc

    # API pública
    def evaluate(self):
        """
        Roda o scan e retorna (Decision, CheckResult).
        Não imprime, não pergunta, não levanta exceção (exceto erros de conexão).
        """
        result = self.guard.check()
        if self.policy is not None:
            # Facade lê de um banco Postgres: aplica a base + a seção postgres.
            result = apply_policy(result, self.policy, engine="postgres")
        decision = decide(
            result=result,
            fail_on=self.fail_on,
            ask_on=self.ask_on,
            interactive_effective=self._interactive,
        )
        return decision, result

    def protect(self):
        """
        Executa o ciclo completo de proteção.
        Retorna CheckResult em caso de sucesso.
        Levanta DriftBrakeError em caso de bloqueio ou aborto.
        """
        # contrato
        if not self._contract_exists():
            self.reporter.on_contract_missing(self.contract_path)
            if not self.auto_init:
                raise ContractMissingError(
                    f"Contract not found: {self.contract_path}. "
                    f"Run `driftbrake init` or set auto_init=True."
                )
            if self._interactive:
                if not self.prompter.confirm_create_contract(self.contract_path):
                    raise UserAborted("Contract creation declined.")
            self._create_contract()
            self.reporter.on_contract_created(self.contract_path)
            return None  # primeira execução, nada a comparar

        # scan + decisão pura
        decision, result = self.evaluate()

        # reporter: invoca um bloco por severidade presente, não apenas a pior
        if not result.changes:
            self.reporter.on_no_drift(result)
        else:
            if result.has_safe:
                self.reporter.on_safe(result)
            if result.has_warnings:
                self.reporter.on_warning(result)
            if result.has_breaking:
                self.reporter.on_breaking(result)
                self.guard.save_reports(result)

        # agir conforme decisão
        if decision.action == "block":
            self.reporter.on_blocked(decision.reason)
            raise BreakingChangesDetected(result, message=decision.reason)

        if decision.action == "ask":
            if decision.severity == "warning":
                confirmed = self.prompter.confirm_continue_with_warnings(result)
            else:
                confirmed = self.prompter.confirm_continue_with_safe(result)
            if not confirmed:
                raise UserAborted("Aborted by user after change confirmation.")

        self.reporter.on_released()
        return result

    def protect_or_exit(self):
        """
        Atalho: chama protect() e traduz exceções em sys.exit().
        Uso recomendado em scripts simples / entrypoints de pipeline.
        """
        try:
            return self.protect()
        except DriftBrakeError as e:
            sys.exit(e.exit_code)

    @classmethod
    def run_from_env(cls, **kwargs):
        """
        Constrói a partir das variáveis de ambiente e executa o ciclo de proteção com
        tradução completa dos códigos de saída.

        Equivalente a:
            try:
                cls.from_env(**kwargs).protect()
            except DriftBrakeError as e:
                sys.exit(e.exit_code)

        Use esta função quando quiser um ponto de entrada (entrypoint) em uma única linha
        que traduza todas as exceções DriftBrakeError, incluindo aquelas levantadas durante
        a construção (ex.: MissingDatabaseURL), para o código de saída apropriado.
        """
        try:
            return cls.from_env(**kwargs).protect()
        except DriftBrakeError as e:
            sys.exit(e.exit_code)

    # Async
    async def aprotect(self):
        """Versão async de protect(). Usa asyncio.to_thread internamente."""
        import asyncio

        return await asyncio.to_thread(self.protect)

    async def aprotect_or_exit(self):
        try:
            return await self.aprotect()
        except DriftBrakeError as e:
            sys.exit(e.exit_code)

    # Context manager

    def guard_block(self) -> _GuardContext:
        """Context manager. Uso: `with DriftBrake.from_env().guard_block(): ...`"""
        return _GuardContext(self)


class _GuardContext:
    def __init__(self, db: DriftBrake) -> None:
        self.db = db
        self.result = None

    def __enter__(self):
        self.result = self.db.protect()
        return self.result

    def __exit__(self, exc_type, exc, tb):
        return False  # nunca suprime exceções do bloco
