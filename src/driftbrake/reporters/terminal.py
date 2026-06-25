# Reporter de terminal usando Rich pra saída colorida e estruturada.

from __future__ import annotations

from driftbrake.core.models import DiffResult, Severity


def _severity_style(severity: Severity) -> str:
    return {
        Severity.BREAKING: "bold red",
        Severity.WARNING: "bold yellow",
        Severity.SAFE: "bold green",
    }.get(severity, "white")


def _severity_label(severity: Severity) -> str:
    return {
        Severity.BREAKING: "[bold red]BREAKING[/bold red]",
        Severity.WARNING: "[bold yellow]WARNING[/bold yellow]",
        Severity.SAFE: "[bold green]SAFE[/bold green]",
    }.get(severity, severity.value)


class TerminalReporter:
    # Imprime um relatório de diff colorido e estruturado no terminal.

    def __init__(self, show_safe: bool = True, mode: str = "check") -> None:
        self.show_safe = show_safe
        # mode controla a mensagem final: "check" mostra DRIFTBRAKE CHECK FAILED/PASSED,
        # "diff" mostra DIFFERENCES DETECTED (exploratório, sem falha).
        self.mode = mode

    def print(self, result: DiffResult) -> None:
        # Imprime o DiffResult no terminal usando Rich.
        try:
            from rich import box
            from rich.console import Console
            from rich.panel import Panel
            from rich.table import Table
        except ImportError:
            self._print_plain(result)
            return

        console = Console()

        # Quando não há mudanças, colapsa para uma linha única sem painel completo.
        if not result.changes:
            console.print()
            console.print(
                Panel(
                    "[bold green]Schemas compatible[/bold green] — 0 changes detected.",
                    style="green",
                    expand=False,
                )
            )
            return

        date_str = result.compared_at.strftime("%Y-%m-%d %H:%M:%S")

        # Largura de referência calculada a partir do conteúdo do painel de cabeçalho.
        # +4 para bordas e padding do Panel. Mínimo de 100 para acomodar 6 colunas.
        ref_lines = [
            "DriftBrake — Comparison Report",
            f"Compared at: {date_str}",
            f"Expected: {result.expected_source}  Current: {result.current_source}",
        ]
        ref_width = max(max(len(line) for line in ref_lines) + 4, 120)
        # Adapta ao terminal se menor que a largura de referência.
        table_width = min(console.size.width, ref_width)

        console.print()
        console.print(
            Panel(
                f"[bold]DriftBrake[/bold] — Comparison Report\n"
                f"Compared at: [dim]{date_str}[/dim]\n"
                f"Expected: [cyan]{result.expected_source}[/cyan]  "
                f"Current: [cyan]{result.current_source}[/cyan]",
                style="bold white on dark_blue",
                width=table_width,
            )
        )

        summary_table = Table(
            box=box.ROUNDED, show_header=False, show_lines=True, width=table_width
        )
        summary_table.add_column("Metric", style="bold white")
        summary_table.add_column("Value", style="white")
        summary_table.add_row("Breaking Changes", f"[bold red]{result.total_breaking}[/bold red]")
        summary_table.add_row("Warnings", f"[bold yellow]{result.total_warnings}[/bold yellow]")
        summary_table.add_row("Safe Changes", f"[bold green]{result.total_safe}[/bold green]")
        summary_table.add_row("Total Changes", str(len(result.changes)))
        compatible_label = (
            "[bold green]Yes[/bold green]" if result.is_compatible else "[bold red]No[/bold red]"
        )
        summary_table.add_row("Compatible", compatible_label)
        console.print(summary_table)
        console.print()

        # Uma tabela unificada por schema table, com severidade como coluna.
        changes_by_table = result.changes_by_table()
        _sev_order = {Severity.BREAKING: 0, Severity.WARNING: 1, Severity.SAFE: 2}

        for table_key, changes in changes_by_table.items():
            breaking_n = sum(1 for c in changes if c.severity == Severity.BREAKING)
            warning_n = sum(1 for c in changes if c.severity == Severity.WARNING)
            safe_n = sum(1 for c in changes if c.severity == Severity.SAFE)

            header_parts = []
            if breaking_n:
                header_parts.append(f"[bold red]{breaking_n} BREAKING[/bold red]")
            if warning_n:
                header_parts.append(f"[bold yellow]{warning_n} WARNING[/bold yellow]")
            if safe_n:
                header_parts.append(f"[bold green]{safe_n} SAFE[/bold green]")

            console.print(
                Panel(
                    f"[bold white]{table_key}[/bold white]  " + "  ".join(header_parts),
                    style="dim",
                    width=table_width,
                )
            )

            visible = [c for c in changes if self.show_safe or c.severity != Severity.SAFE]
            visible.sort(key=lambda c: _sev_order.get(c.severity, 99))

            tbl = Table(
                box=box.SIMPLE_HEAVY,
                show_header=True,
                header_style="bold white",
                show_lines=True,
                width=table_width,
            )
            tbl.add_column("Column", style="cyan", no_wrap=True)
            tbl.add_column("Severity", no_wrap=True)
            tbl.add_column("Change Type", style="white", no_wrap=True)
            tbl.add_column("Before", style="white", no_wrap=True)
            tbl.add_column("After", style="white", no_wrap=True)
            tbl.add_column("Description", style="white", ratio=1)

            for change in visible:
                tbl.add_row(
                    change.column_name or "—",
                    _severity_label(change.severity),
                    change.change_type.value,
                    str(change.old_value) if change.old_value is not None else "—",
                    str(change.new_value) if change.new_value is not None else "—",
                    change.description,
                )
            console.print(tbl)
            console.print()

        # Painel final: mensagem e estilo dependem do modo (check vs diff).
        if self.mode == "diff":
            if not result.is_compatible:
                console.print(
                    Panel(
                        "[bold yellow]DIFFERENCES DETECTED[/bold yellow]\n"
                        "Breaking changes found. This is an exploratory diff — exit code is 0.",
                        style="yellow",
                        width=table_width,
                    )
                )
            else:
                console.print(
                    Panel(
                        "[bold green]NO BREAKING DIFFERENCES[/bold green]\n"
                        "No breaking changes found between the two schemas.",
                        style="green",
                        width=table_width,
                    )
                )
        else:
            if not result.is_compatible:
                console.print(
                    Panel(
                        "[bold red]DRIFTBRAKE CHECK FAILED[/bold red]\n"
                        "Breaking changes detected. Check the report above.",
                        style="red",
                        width=table_width,
                    )
                )
            else:
                console.print(
                    Panel(
                        "[bold green]DRIFTBRAKE CHECK PASSED[/bold green]\n"
                        "No breaking changes detected.",
                        style="green",
                        width=table_width,
                    )
                )

    def _print_plain(self, result: DiffResult) -> None:
        # Saída em texto simples como alternativa quando Rich não está disponível.
        print(f"\nSchema Comparison Report — {result.compared_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if not result.changes:
            print("Schemas compatible — 0 changes detected.")
            return
        print(
            f"Breaking: {result.total_breaking}  "
            f"Warnings: {result.total_warnings}  "
            f"Safe: {result.total_safe}"
        )
        print()
        for change in result.changes:
            print(
                f"[{change.severity.value}] {change.schema_name}.{change.table_name}"
                f" | col={change.column_name or '-'} | {change.change_type.value}"
                f" | {change.old_value} -> {change.new_value}"
            )
        print()
        if self.mode == "diff":
            if not result.is_compatible:
                print("DIFFERENCES DETECTED")
            else:
                print("NO BREAKING DIFFERENCES")
        else:
            if result.is_compatible:
                print("DRIFTBRAKE CHECK PASSED")
            else:
                print("DRIFTBRAKE CHECK FAILED — Breaking changes detected.")
