"""
CLI do DriftBrake usando Typer.

Comandos:
    init            - Inicializa um novo contrato de schema a partir de um banco de dados ativo.
    check           - Compara o banco de dados ativo contra um contrato.
    diff            - Compara dois arquivos de schema ou um arquivo contra um banco de dados.
    snapshot        - Captura o schema atual sem realizar comparação.
    update-contract - Atualiza o contrato para refletir o estado atual do banco de dados.

Códigos de saída:
    0 - Schema compatível / sucesso.
    1 - Aviso em modo estrito.
    2 - Alteração crítica detectada.
    3 - Erro de conexão com o banco de dados.
    4 - Contrato ausente ou inválido.
    5 - Erro de configuração.
    6 - Erro interno.
"""

from __future__ import annotations

import os
import platform
import sys
from importlib.metadata import version as get_version
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from driftbrake.contracts.writer import ContractWriter
from driftbrake.core.comparator import SchemaComparator
from driftbrake.core.models import Severity
from driftbrake.core.policy import apply_policy, load_policy
from driftbrake.exceptions import (
    DriftBrakeError,
    MissingDependencyError,
    ParquetReadError,
    SchemaConnectionError,
    SchemaContractNotFoundError,
)
from driftbrake.guard import SchemaGuard
from driftbrake.readers.json.reader import JsonSchemaReader
from driftbrake.readers.parquet.reader import ParquetSchemaReader
from driftbrake.readers.postgres import PostgresSchemaReader
from driftbrake.reporters.html_report import HtmlReporter
from driftbrake.reporters.json_report import JsonReporter
from driftbrake.reporters.terminal import TerminalReporter

# Arquivo de política único, lido pela CLI e pela biblioteca.
DEFAULT_POLICY_FILE = "policy.yml"

app = typer.Typer(
    name="driftbrake",
    help="DriftBrake — Validate schema contracts before running data pipelines.",
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    # Exibe a versão e encerra o processo.
    if value:
        v = get_version("driftbrake")
        typer.echo(f"DriftBrake {v}")
        raise typer.Exit()


def _info_callback(value: bool) -> None:
    # Exibe informações detalhadas sobre o ambiente e encerra o processo.
    if value:
        import sqlalchemy

        v = get_version("driftbrake")
        typer.echo(f"DriftBrake {v}")
        typer.echo(f"Python {sys.version.split()[0]}")
        typer.echo(f"Platform {platform.platform()}")
        typer.echo(f"SQLAlchemy {sqlalchemy.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    info: bool = typer.Option(
        False,
        "--info",
        callback=_info_callback,
        is_eager=True,
        help="Show environment info (version, Python, platform, SQLAlchemy) and exit.",
    ),
) -> None:
    pass


def _build_db_url(db_url: str | None, flag: str = "--db-url") -> str:
    # Resolve a URL do banco de dados a partir do argumento ou variáveis de ambiente.
    # `flag` nomeia a opção da CLI na mensagem de erro (--db-url no init/check,
    # --new-db no diff), para o erro casar com o que o usuário digitou.
    load_dotenv()

    if db_url:
        return db_url
    if database_url := os.getenv("DATABASE_URL"):
        return database_url
    if not os.getenv("DB_NAME") or not os.getenv("DB_USER"):
        typer.echo(
            f"[ERROR] No database URL resolved. Pass {flag} with a value, or set "
            "DATABASE_URL (a .env file is loaded automatically).",
            err=True,
        )
        raise typer.Exit(3)
    return (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD', '')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
        f"/{os.getenv('DB_NAME')}"
    )


def _load_policy_if_present(policy_path: str | None):
    """Carrega o `policy.yml` se existir; ausente = sem política (None).

    Um arquivo de política único serve a CLI e a biblioteca. Não existir é o caso
    normal de quem não usa políticas — não é erro. Um arquivo presente porém
    malformado aborta com a mensagem e o exit code da exceção.
    """
    if not policy_path or not Path(policy_path).exists():
        return None
    try:
        return load_policy(policy_path)
    except DriftBrakeError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(exc.exit_code)


def _apply_policy_file(result, policy_path: str | None, engine: str):
    """Aplica o `policy.yml` (base + seção do engine) ao resultado, se presente."""
    policy = _load_policy_if_present(policy_path)
    if policy is None:
        return result
    return apply_policy(result, policy, engine=engine)


def _iter_divergences(reader):
    """Itera (nome_tabela, FieldDivergence) sobre todas as tabelas do reader."""
    for table_name, ds in reader.table_datasets.items():
        for d in ds.divergences:
            yield table_name, d


def _parquet_reader(source: str, policy_path: str | None, table_name: str | None = None):
    """Constrói um ParquetSchemaReader herdando a seção `parquet.dataset` do policy.yml.

    `table_name` só renomeia quando o source resolve para uma única tabela.
    Retorna (reader, max_divergent_files, policy).
    """
    policy = _load_policy_if_present(policy_path)
    strategy = "most_common"
    ignore_partition = True
    max_divergent = 0
    if policy is not None and policy.parquet is not None:
        ds = policy.parquet.dataset
        strategy = ds.dominant_schema_strategy
        ignore_partition = ds.ignore_partition_columns
        max_divergent = ds.max_divergent_files
    reader = ParquetSchemaReader(
        source,
        table_name=table_name,
        dominant_schema_strategy=strategy,
        ignore_partition_columns=ignore_partition,
    )
    return reader, max_divergent, policy


def _check_parquet_source(
    *,
    source: str,
    contract: str,
    fail_on_list: list[str],
    json_output: str | None,
    html_output: str | None,
    markdown_output: str | None,
    policy_path: str | None,
    table_name: str | None = None,
) -> None:
    """Caminho Parquet do `check`: drift contra o contrato (#2) + divergência inter-arquivo (#1)."""
    try:
        expected = JsonSchemaReader(contract).read()
    except SchemaContractNotFoundError as exc:
        typer.echo(f"[ERROR] Contract error: {exc}", err=True)
        raise typer.Exit(4)

    try:
        reader, max_divergent, policy = _parquet_reader(source, policy_path, table_name=table_name)
        current = reader.read()
    except MissingDependencyError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(5)
    except ParquetReadError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(3)

    result = SchemaComparator().compare(
        expected=expected,
        current=current,
        expected_source=contract,
        current_source=source,
    )

    # Aplica o policy.yml (base + seção parquet) ao resultado.
    if policy is not None:
        result = apply_policy(result, policy, engine="parquet")

    TerminalReporter(mode="check").print(result)
    if json_output:
        JsonReporter(json_output).write(result)
        typer.echo(f"JSON report: {json_output}")
    if html_output:
        try:
            HtmlReporter(html_output).write(result)
            typer.echo(f"HTML report: {html_output}")
        except FileNotFoundError as exc:
            typer.echo(f"[WARNING] HTML report skipped: {exc}", err=True)
    if markdown_output:
        from driftbrake.reporters.markdown_report import MarkdownReporter

        MarkdownReporter(markdown_output).write(result)
        typer.echo(f"Markdown report: {markdown_output}")

    # Drift #1 — consistência interna de cada tabela (divergência inter-arquivo)
    divs = list(_iter_divergences(reader))
    divergent = len(divs)
    if divergent:
        typer.echo(
            f"\n[DRIFT] {divergent} inter-file divergence(s) from the dominant schema:", err=True
        )
        for table_name, d in divs:
            typer.echo(
                f"  - [{table_name}] {d.file} :: column '{d.column}': "
                f"expected {d.expected}, found {d.found}",
                err=True,
            )

    fail_severities = [Severity(s.upper()) for s in fail_on_list]
    failing = [c for c in result.changes if c.severity in fail_severities]
    divergence_over = divergent > max_divergent

    if failing or divergence_over:
        reasons = []
        if failing:
            reasons.append(f"{len(failing)} change(s) above threshold ({','.join(fail_on_list)})")
        if divergence_over:
            reasons.append(f"{divergent} divergent file(s) over tolerance ({max_divergent})")
        typer.echo(f"\n[FAILED] {'; '.join(reasons)}. Exiting with code 2.", err=True)
        raise typer.Exit(2)

    typer.echo("\n[OK] Schema is compatible.")


@app.command("init", help="Initialize a schema contract from a database or a Parquet source.")
def init(
    db_url: Annotated[
        str | None,
        typer.Option("--db-url", help="Database connection URL."),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", help="Parquet file or directory to read instead of a database."),
    ] = None,
    table: Annotated[
        str | None,
        typer.Option("--table", help="Name for the table when the Parquet source is a single one."),
    ] = None,
    schemas: Annotated[
        str,
        typer.Option("--schemas", help="Comma-separated list of schemas to capture."),
    ] = "public",
    output: Annotated[
        str,
        typer.Option("--output", help="Output path for the schema contract file."),
    ] = "schema.lock.json",
) -> None:
    # Inicializa um contrato de schema a partir de um banco vivo ou de um dataset Parquet.

    if source:
        typer.echo(f"Reading Parquet schema from {source} ...")
        try:
            reader, _, _ = _parquet_reader(source, None, table_name=table)
            db_schema = reader.read()
        except MissingDependencyError as exc:
            typer.echo(f"[ERROR] {exc}", err=True)
            raise typer.Exit(5)
        except ParquetReadError as exc:
            typer.echo(f"[ERROR] {exc}", err=True)
            raise typer.Exit(3)
    else:
        url = _build_db_url(db_url)
        schema_list = [s.strip() for s in schemas.split(",") if s.strip()]
        typer.echo(f"Connecting to database and reading schema ({', '.join(schema_list)})...")
        try:
            reader = PostgresSchemaReader(database_url=url, schemas=schema_list)
            db_schema = reader.read()
        except SchemaConnectionError as exc:
            typer.echo(f"[ERROR] Connection failed: {exc}", err=True)
            raise typer.Exit(3)
        except DriftBrakeError as exc:
            # ex.: schema inexistente (SchemaNotFoundError, exit 5). Erro de
            # usuário deve sair limpo, com o código certo — nunca traceback.
            typer.echo(f"[ERROR] {exc}", err=True)
            raise typer.Exit(exc.exit_code)

    writer = ContractWriter(output)
    writer.write(db_schema)
    typer.echo(f"[OK] Schema contract saved to: {output}")

    # Lista as tabelas capturadas, nunca some com elas em silêncio.
    table_names = [t for tables in db_schema.schemas.values() for t in tables]
    typer.echo(
        f"     {len(table_names)} table(s) captured across {len(db_schema.schemas)} schema(s): "
        f"{', '.join(sorted(table_names))}"
    )


@app.command(
    "check",
    help="Check for divergences between the live database and the schema contract.",
)
def check(
    db_url: Annotated[
        str | None,
        typer.Option("--db-url", help="Database connection URL."),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", help="Parquet file or directory to check instead of a database."),
    ] = None,
    table: Annotated[
        str | None,
        typer.Option("--table", help="Name for the table when the Parquet source is a single one."),
    ] = None,
    contract: Annotated[
        str,
        typer.Option("--contract", help="Path to the schema.lock.json contract file."),
    ] = "schema.lock.json",
    fail_on: Annotated[
        str,
        typer.Option("--fail-on", help="Severity levels (comma-sep.) that cause a non-zero exit."),
    ] = "BREAKING",
    json_output: Annotated[
        str | None,
        typer.Option("--json", help="Write the diff report as JSON to this path."),
    ] = None,
    html_output: Annotated[
        str | None,
        typer.Option("--html", help="Write the diff report as HTML to this path."),
    ] = None,
    markdown_output: Annotated[
        str | None,
        typer.Option("--markdown", help="Write the diff report as Markdown to this path."),
    ] = None,
    policy: Annotated[
        str,
        typer.Option(
            "--policy",
            "--config",
            help="Path to the policy.yml file (overrides, ignores, postgres/parquet sections).",
        ),
    ] = DEFAULT_POLICY_FILE,
) -> None:
    # Compara o schema do banco de dados ativo (ou um dataset Parquet) contra um contrato.
    fail_on_list = [s.strip() for s in fail_on.split(",") if s.strip()]

    if source:
        _check_parquet_source(
            source=source,
            contract=contract,
            fail_on_list=fail_on_list,
            json_output=json_output,
            html_output=html_output,
            markdown_output=markdown_output,
            policy_path=policy,
            table_name=table,
        )
        return

    url = _build_db_url(db_url)

    try:
        guard = SchemaGuard(
            database_url=url,
            contract_path=contract,
            output_json=json_output,
            output_html=html_output,
            output_markdown=markdown_output,
            fail_on=fail_on_list,
        )
        result = guard.check()
    except SchemaConnectionError as exc:
        typer.echo(f"[ERROR] Connection failed: {exc}", err=True)
        raise typer.Exit(3)
    except SchemaContractNotFoundError as exc:
        typer.echo(f"[ERROR] Contract error: {exc}", err=True)
        raise typer.Exit(4)
    except DriftBrakeError as exc:
        # ex.: schema inexistente -> exit 5, mensagem limpa (não "Unexpected error").
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(exc.exit_code)
    except Exception as exc:
        typer.echo(f"[ERROR] Unexpected error: {exc}", err=True)
        raise typer.Exit(6)

    # policy.yml (base + seção postgres) aplicado ao resultado, como na biblioteca.
    result = _apply_policy_file(result, policy, engine="postgres")

    guard.save_reports(result)
    guard.print_report(result)

    fail_severities = [Severity(s.upper()) for s in fail_on_list]
    failing = [c for c in result.changes if c.severity in fail_severities]
    if failing:
        typer.echo(
            f"\n[FAILED] {len(failing)} change(s) above threshold ({fail_on}). "
            "Exiting with code 2.",
            err=True,
        )
        raise typer.Exit(2)

    typer.echo("\n[OK] Schema is compatible.")


@app.command("diff", help="Compare two schemas (JSON files or database) and show differences.")
def diff(
    old: Annotated[
        str | None,
        typer.Option("--old", help="Path to the JSON file representing the expected (old) schema."),
    ] = None,
    new: Annotated[
        str | None,
        typer.Option("--new", help="Path to the JSON file representing the current (new) schema."),
    ] = None,
    new_db: Annotated[
        str | None,
        typer.Option("--new-db", help="Database URL to use as the current (new) schema."),
    ] = None,
    json_output: Annotated[
        str | None,
        typer.Option("--json", help="Write the diff report as JSON to this path."),
    ] = None,
    html_output: Annotated[
        str | None,
        typer.Option("--html", help="Write the diff report as HTML to this path."),
    ] = None,
) -> None:
    # Compara duas fontes de schema (arquivos ou um arquivo contra um banco de dados ativo).

    if not old:
        typer.echo("[ERROR] --old is required.", err=True)
        raise typer.Exit(6)

    try:
        expected = JsonSchemaReader(old).read()
    except SchemaContractNotFoundError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(4)

    current_source = ""
    try:
        if new_db is not None:
            # --new-db foi passado (mesmo vazio, ex.: "$DATABASE_URL" não exportada):
            # resolve como os outros comandos — valor explícito, senão .env/DATABASE_URL.
            url = _build_db_url(new_db, flag="--new-db")
            current = PostgresSchemaReader(database_url=url).read()
            current_source = url
        elif new:
            current = JsonSchemaReader(new).read()
            current_source = new
        else:
            typer.echo("[ERROR] Provide --new or --new-db.", err=True)
            raise typer.Exit(6)
    except SchemaConnectionError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(3)
    except SchemaContractNotFoundError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(4)

    comparator = SchemaComparator()
    result = comparator.compare(
        expected=expected,
        current=current,
        expected_source=old,
        current_source=current_source,
    )

    TerminalReporter(mode="diff").print(result)

    if json_output:
        JsonReporter(json_output).write(result)
        typer.echo(f"JSON report: {json_output}")
    if html_output:
        try:
            HtmlReporter(html_output).write(result)
            typer.echo(f"HTML report: {html_output}")
        except FileNotFoundError as exc:
            typer.echo(f"[WARNING] HTML report skipped: {exc}", err=True)


@app.command("snapshot", help="Capture the current database schema without comparing.")
def snapshot(
    db_url: Annotated[
        str | None,
        typer.Option("--db-url", help="Database connection URL."),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", help="Output path for the snapshot JSON file."),
    ] = "schema.snapshot.json",
    schemas: Annotated[
        str,
        typer.Option("--schemas", help="Comma-separated list of schemas to capture."),
    ] = "public",
) -> None:
    """Captures a snapshot of the current database schema without comparing."""
    url = _build_db_url(db_url)
    schema_list = [s.strip() for s in schemas.split(",") if s.strip()]

    typer.echo(f"Capturing schema snapshot from {url.split('@')[-1]}...")
    try:
        reader = PostgresSchemaReader(database_url=url, schemas=schema_list)
        db_schema = reader.read()
    except SchemaConnectionError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(3)
    except DriftBrakeError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(exc.exit_code)

    ContractWriter(output).write(db_schema)
    total_tables = sum(len(t) for t in db_schema.schemas.values())
    typer.echo(f"[OK] Snapshot saved to {output} ({total_tables} tables).")


@app.command("update-contract", help="Update the schema contract to match the current database.")
def update_contract(
    db_url: Annotated[
        str | None,
        typer.Option("--db-url", help="Database connection URL."),
    ] = None,
    contract: Annotated[
        str,
        typer.Option("--contract", help="Path to the schema.lock.json to be updated."),
    ] = "schema.lock.json",
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip the interactive confirmation prompt."),
    ] = False,
    schemas: Annotated[
        str,
        typer.Option("--schemas", help="Comma-separated list of schemas to capture."),
    ] = "public",
) -> None:
    """Updates the schema contract to reflect the current state of the database."""
    url = _build_db_url(db_url)
    schema_list = [s.strip() for s in schemas.split(",") if s.strip()]

    if not yes:
        confirmed = typer.confirm(
            f"This will overwrite '{contract}' with the current database schema. Continue?"
        )
        if not confirmed:
            typer.echo("Operation cancelled.")
            raise typer.Exit(0)

    typer.echo("Reading current database schema...")
    try:
        reader = PostgresSchemaReader(database_url=url, schemas=schema_list)
        db_schema = reader.read()
    except SchemaConnectionError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(3)
    except DriftBrakeError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(exc.exit_code)

    ContractWriter(contract).write(db_schema)
    total_tables = sum(len(t) for t in db_schema.schemas.values())
    typer.echo(f"[OK] Contract updated: {contract} ({total_tables} tables).")


@app.command(
    "parquet-check",
    help="Validate schema consistency within a partitioned Parquet dataset (drift #1).",
)
def parquet_check(
    path: Annotated[
        str,
        typer.Option("--path", help="Directory of the partitioned Parquet dataset (or a file)."),
    ],
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            help="Dominant schema strategy: most_common | first_file | latest_mtime.",
        ),
    ] = "most_common",
    max_divergent: Annotated[
        int,
        typer.Option("--max-divergent", help="Max divergent files tolerated (0 = zero tolerance)."),
    ] = 0,
    json_output: Annotated[
        str | None,
        typer.Option("--json", help="Write the divergence report as JSON to this path."),
    ] = None,
    policy_path: Annotated[
        str,
        typer.Option(
            "--policy",
            "--config",
            help="policy.yml; its parquet.dataset section sets the defaults below.",
        ),
    ] = DEFAULT_POLICY_FILE,
) -> None:
    # Consolida o dataset, imprime o schema dominante e as divergências inter-arquivo.
    ignore_partition_columns = True
    policy = _load_policy_if_present(policy_path)
    if policy is not None and policy.parquet is not None:
        ds_cfg = policy.parquet.dataset
        # opções explícitas da CLI ganham; senão, herdam do policy.yml
        if strategy == "most_common":
            strategy = ds_cfg.dominant_schema_strategy
        if max_divergent == 0:
            max_divergent = ds_cfg.max_divergent_files
        ignore_partition_columns = ds_cfg.ignore_partition_columns

    try:
        reader = ParquetSchemaReader(
            path,
            dominant_schema_strategy=strategy,
            ignore_partition_columns=ignore_partition_columns,
        )
        reader.read()
    except MissingDependencyError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(5)
    except ParquetReadError as exc:
        typer.echo(f"[ERROR] {exc}", err=True)
        raise typer.Exit(3)

    tables = reader.table_datasets
    if len(tables) > 1:
        typer.echo(
            f"{len(tables)} tables discovered in {path} (grouped by column affinity). "
            "Inter-file divergence is checked within each."
        )
    n = 0
    for tname, ds in tables.items():
        typer.echo(
            f"\nTable '{tname}': {ds.file_count} file(s), {len(ds.columns)} column(s), "
            f"strategy={ds.dominant_strategy}"
        )
        for col, canonical in ds.columns.items():
            typer.echo(f"  - {col}: {canonical}")
        if ds.divergences:
            n += len(ds.divergences)
            typer.echo(
                f"  [DRIFT] {len(ds.divergences)} divergence(s) from the dominant schema:",
                err=True,
            )
            for d in ds.divergences:
                typer.echo(
                    f"    - {d.file} :: column '{d.column}': "
                    f"expected {d.expected}, found {d.found}",
                    err=True,
                )

    if json_output:
        import json as _json

        report = {t: ds.to_dict() for t, ds in tables.items()}
        with open(json_output, "w", encoding="utf-8") as f:
            _json.dump(report, f, indent=2, ensure_ascii=False)
        typer.echo(f"JSON report: {json_output}")

    if n == 0:
        typer.echo("\n[OK] Dataset is schema-consistent (no inter-file drift).")
        return

    if n > max_divergent:
        typer.echo(
            f"\n[FAILED] {n} divergent change(s) above threshold ({max_divergent}). "
            "Exiting with code 2.",
            err=True,
        )
        raise typer.Exit(2)
    typer.echo("\n[OK] Divergences within tolerance.")


if __name__ == "__main__":
    app()
