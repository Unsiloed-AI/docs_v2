"""
Write enriched MDX files to disk and print a rich diff summary.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

console = Console()


@dataclass
class FileResult:
    path: Path
    original: str
    updated: str
    operation_key: str


def _unified_diff(original: str, updated: str, path: Path) -> str:
    original_lines = original.splitlines(keepends=True)
    updated_lines = updated.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
        n=3,
    )
    return "".join(diff)


def _count_changes(original: str, updated: str) -> tuple[int, int]:
    """Return (lines_added, lines_removed)."""
    diff = difflib.ndiff(original.splitlines(), updated.splitlines())
    added = sum(1 for l in diff if l.startswith("+ "))
    # Re-run diff since the generator is exhausted
    diff2 = difflib.ndiff(original.splitlines(), updated.splitlines())
    removed = sum(1 for l in diff2 if l.startswith("- "))
    return added, removed


def print_summary(results: list[FileResult], dry_run: bool) -> None:
    action = "[dim]dry run[/dim]" if dry_run else "[green]written[/green]"
    changed = [r for r in results if r.original != r.updated]
    unchanged = [r for r in results if r.original == r.updated]

    console.print()
    console.rule("[bold]Sync Summary")

    if not changed:
        console.print("[green]✓ All files are already up to date.[/green]")
        return

    for result in changed:
        added, removed = _count_changes(result.original, result.updated)
        label = Text()
        label.append(f"  {result.path.name}", style="bold cyan")
        label.append(f"  ({result.operation_key})", style="dim")
        label.append(f"  +{added}", style="green")
        label.append(f" -{removed}", style="red")
        label.append(f"  {action}")
        console.print(label)

    console.print()
    console.print(
        f"  [bold]{len(changed)}[/bold] file(s) changed, "
        f"[dim]{len(unchanged)} unchanged[/dim]"
    )


def print_diff(result: FileResult) -> None:
    diff = _unified_diff(result.original, result.updated, result.path)
    if not diff:
        return
    console.print(
        Panel(
            Syntax(diff, "diff", theme="monokai", line_numbers=False),
            title=f"[cyan]{result.path.name}[/cyan]  [dim]{result.operation_key}[/dim]",
            expand=False,
        )
    )


def write_results(
    results: list[FileResult],
    dry_run: bool,
    show_diff: bool = True,
) -> None:
    changed = [r for r in results if r.original != r.updated]

    if show_diff:
        for result in changed:
            print_diff(result)

    if not dry_run:
        for result in changed:
            result.path.write_text(result.updated, encoding="utf-8")

    print_summary(results, dry_run=dry_run)
