"""
SchemaGuard - API de alto nível para validação de contratos de schema.

Fornece uma interface simples para executar verificações de schema em pipelines,
sistemas de CI e fluxos de dados.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from driftbrake.config.settings import Settings
from driftbrake.contracts.loader import ContractLoader
from driftbrake.core.classifier import ImpactClassifier
from driftbrake.core.comparator import SchemaComparator
from driftbrake.core.models import DiffResult, Severity
from driftbrake.exceptions import SchemaConnectionError
from driftbrake.readers.postgres import PostgresSchemaReader
from driftbrake.reporters.html_report import HtmlReporter
from driftbrake.reporters.json_report import JsonReporter
from driftbrake.reporters.markdown_report import MarkdownReporter
from driftbrake.reporters.terminal import TerminalReporter


class SchemaGuard:
    """
    Guard de contrato de schema de alto nível.

    Conecta ao banco de dados, carrega o contrato, compara os schemas
    e aplica as regras de compatibilidade.

    Uso:
        guard = SchemaGuard.from_env(contract_path="schema.lock.json")
        guard.assert_compatible()
    """

    def __init__(
        self,
        database_url: str,
        contract_path: str | Path,
        config_path: str | Path | None = None,
        output_json: str | Path | None = None,
        output_html: str | Path | None = None,
        output_markdown: str | Path | None = None,
        fail_on: list[str] | None = None,
        schemas: list[str] | None = None,
        include_tables: list[str] | None = None,
        exclude_tables: list[str] | None = None,
    ) -> None:
        self.database_url = database_url
        self.contract_path = Path(contract_path)
        self.config_path = Path(config_path) if config_path else None
        self.output_json = Path(output_json) if output_json else None
        self.output_html = Path(output_html) if output_html else None
        self.output_markdown = Path(output_markdown) if output_markdown else None
        self.schemas = schemas or ["public"]
        self.include_tables = include_tables
        self.exclude_tables = exclude_tables or []

        # Carrega as configurações
        if self.config_path and self.config_path.exists():
            self.settings = Settings.from_file(self.config_path)
        else:
            self.settings = Settings.defaults()

        # Sobrescreve fail_on se fornecido explicitamente
        if fail_on is not None:
            self.settings.fail_on = [Severity(s.upper()) for s in fail_on]

    @classmethod
    def from_env(
        cls,
        contract_path: str | Path,
        **kwargs: Any,
    ) -> SchemaGuard:
        """
        Cria um SchemaGuard usando DATABASE_URL do ambiente.

        Usa variáveis DB_* individuais para construir a URL caso DATABASE_URL
        não esteja definida.

        contract_path: Caminho para o arquivo schema.lock.json.
        **kwargs: Argumentos adicionais repassados para SchemaGuard.__init__.
        """
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "5432")
            name = os.getenv("DB_NAME", "")
            user = os.getenv("DB_USER", "")
            password = os.getenv("DB_PASSWORD", "")
            if not name or not user:
                raise SchemaConnectionError(
                    "Database connection not configured. Set DATABASE_URL or "
                    "DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD in the environment."
                )
            database_url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
        return cls(database_url=database_url, contract_path=contract_path, **kwargs)

    def check(self) -> DiffResult:
        """
        Executa a comparação de schema.

        Lê o schema atual do banco de dados e o schema esperado do arquivo de
        contrato, então os compara.

        DiffResult: Todas as alterações detectadas com classificações de severidade.
        """
        reader = PostgresSchemaReader(
            database_url=self.database_url,
            schemas=self.schemas,
            include_tables=self.include_tables,
            exclude_tables=self.exclude_tables,
        )
        current_schema = reader.read()

        loader = ContractLoader(self.contract_path)
        expected_schema = loader.load()

        classifier = ImpactClassifier()
        comparator = SchemaComparator(classifier=classifier)

        result = comparator.compare(
            expected=expected_schema,
            current=current_schema,
            expected_source=str(self.contract_path),
            current_source=(
                self.database_url.split("@")[-1] if "@" in self.database_url else self.database_url
            ),
        )
        return result

    def assert_compatible(self) -> None:
        """
        Executa a verificação de schema e encerra com código não-zero se incompatível.

        Códigos de saída:
            0 - Schema compatível.
            2 - Alterações críticas detectadas.
            3 - Erro de conexão com o banco de dados.
            4 - Arquivo de contrato ausente ou inválido.
        """
        try:
            result = self.check()
        except SchemaConnectionError as exc:
            print(f"[ERROR] Database connection failed: {exc}", file=sys.stderr)
            sys.exit(3)
        except Exception as exc:
            from driftbrake.exceptions import SchemaContractNotFoundError

            if isinstance(exc, SchemaContractNotFoundError):
                print(f"[ERROR] Contract error: {exc}", file=sys.stderr)
                sys.exit(4)
            print(f"[ERROR] Unexpected error: {exc}", file=sys.stderr)
            sys.exit(6)

        self.save_reports(result)
        self.print_report(result)

        active_severities = {c.severity for c in result.changes}
        failing_severities = [s for s in self.settings.fail_on if s in active_severities]
        if failing_severities:
            labels = [s.value for s in failing_severities]
            print(
                f"\n[FAIL] Schema check failed due to: {', '.join(labels)} changes.",
                file=sys.stderr,
            )
            sys.exit(2)

    def save_reports(self, result: DiffResult) -> None:
        """Salva relatórios JSON, HTML e Markdown se os caminhos de saída estiverem configurados."""
        if self.output_json:
            reporter = JsonReporter(self.output_json)
            reporter.write(result)

        if self.output_html:
            try:
                reporter_html = HtmlReporter(self.output_html)
                reporter_html.write(result)
            except FileNotFoundError as exc:
                print(f"[WARN] Could not generate HTML report: {exc}", file=sys.stderr)

        if self.output_markdown:
            reporter_md = MarkdownReporter(self.output_markdown)
            reporter_md.write(result)

    def print_report(self, result: DiffResult) -> None:
        # Imprime o relatório de diff no terminal.
        terminal = TerminalReporter()
        terminal.print(result)
