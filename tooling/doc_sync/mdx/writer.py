"""
Write enriched MDX files to disk and print a rich diff summary.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

if TYPE_CHECKING:
    from doc_sync.judge.judge import JudgeResult

console = Console()


@dataclass
class FileResult:
    path: Path
    original: str
    updated: str
    operation_key: str
    judge_result: "JudgeResult | None" = field(default=None, compare=False)


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

        if result.judge_result is not None:
            jr = result.judge_result
            if jr.passed:
                score = jr.scores.get("accuracy", "?")
                label.append(f"  Judge: ", style="dim")
                label.append(f"PASS {score}/5", style="bold green")
            else:
                n_critical = len(jr.critical_issues)
                n_minor = len(jr.minor_issues)
                label.append(f"  Judge: ", style="dim")
                label.append("FAIL", style="bold red")
                parts = []
                if n_critical:
                    parts.append(f"{n_critical} critical")
                if n_minor:
                    parts.append(f"{n_minor} minor")
                label.append(f" — {', '.join(parts)}", style="red")

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


def print_judge_report(result: FileResult) -> None:
    """Print a detailed judge verdict panel for a single file."""
    jr = result.judge_result
    if jr is None:
        return

    verdict_style = "green" if jr.passed else "red"
    verdict_label = "PASS" if jr.passed else "FAIL"

    scores_str = "  ".join(
        f"{k}: {v}/5" for k, v in jr.scores.items()
    )

    lines: list[str] = [
        f"[{verdict_style}]{verdict_label}[/{verdict_style}]  {scores_str}",
        "",
        f"[dim]{jr.summary}[/dim]",
    ]

    if jr.issues:
        lines.append("")
        for issue in jr.issues:
            colour = "red" if issue.severity == "critical" else "yellow"
            lines.append(
                f"  [{colour}][{issue.severity.upper()}][/{colour}]  "
                f"[bold]{issue.location}[/bold]"
            )
            if issue.claim_in_doc:
                lines.append(f"    doc:  {issue.claim_in_doc}")
            if issue.truth_in_code:
                lines.append(f"    code: {issue.truth_in_code}")
            lines.append(f"    fix:  [italic]{issue.fix}[/italic]")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[cyan]Judge — {result.path.name}[/cyan]  [dim]{result.operation_key}[/dim]",
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

    # Print judge reports after diffs
    for result in results:
        if result.judge_result is not None:
            print_judge_report(result)

    if not dry_run:
        for result in changed:
            result.path.write_text(result.updated, encoding="utf-8")

    print_summary(results, dry_run=dry_run)
