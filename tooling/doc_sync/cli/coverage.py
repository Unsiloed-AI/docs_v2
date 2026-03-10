#!/usr/bin/env python3
"""
check_coverage.py — Report OpenAPI schema description coverage.

Reads openapi.json and reports what percentage of schema properties,
operation parameters, and operations have descriptions. Optionally
fails if coverage is below a minimum threshold.

Usage:
    uv run check_coverage.py --spec ../../parser/openapi.json
    uv run check_coverage.py --spec ../../parser/openapi.json --min-coverage 80
    uv run check_coverage.py --spec ../../parser/openapi.json --verbose
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _check_schema_properties(schemas: dict) -> tuple[int, int, list[str]]:
    total = 0
    documented = 0
    missing: list[str] = []
    for schema_name, schema in schemas.items():
        props = schema.get("properties", {})
        for prop_name, prop in props.items():
            total += 1
            desc = prop.get("description", "")
            if desc and desc.strip():
                documented += 1
            else:
                missing.append(f"{schema_name}.{prop_name}")
    return total, documented, missing


def _check_operations(paths: dict) -> tuple[int, int, list[str]]:
    total = 0
    documented = 0
    missing: list[str] = []
    for path, path_item in paths.items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            operation = path_item.get(method)
            if not operation:
                continue
            total += 1
            desc = operation.get("description", "") or operation.get("summary", "")
            if desc and desc.strip():
                documented += 1
            else:
                missing.append(f"{method.upper()} {path}")
    return total, documented, missing


def _check_parameters(paths: dict) -> tuple[int, int, list[str]]:
    total = 0
    documented = 0
    missing: list[str] = []
    for path, path_item in paths.items():
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if not operation:
                continue
            for param in operation.get("parameters", []):
                total += 1
                desc = param.get("description", "")
                if desc and desc.strip():
                    documented += 1
                else:
                    missing.append(f"{method.upper()} {path} → {param.get('name', '?')}")
    return total, documented, missing


@click.command()
@click.option(
    "--spec",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to openapi.json",
)
@click.option(
    "--min-coverage",
    default=0,
    show_default=True,
    help="Fail with exit code 1 if overall coverage is below this percentage.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Print all missing field names.",
)
def main(spec: str, min_coverage: int, verbose: bool) -> None:
    data = json.loads(Path(spec).read_text(encoding="utf-8"))
    schemas = data.get("components", {}).get("schemas", {})
    paths = data.get("paths", {})

    prop_total, prop_doc, prop_missing = _check_schema_properties(schemas)
    op_total, op_doc, op_missing = _check_operations(paths)
    param_total, param_doc, param_missing = _check_parameters(paths)

    def pct(doc: int, tot: int) -> int:
        return (doc * 100 // tot) if tot else 100

    prop_pct = pct(prop_doc, prop_total)
    op_pct = pct(op_doc, op_total)
    param_pct = pct(param_doc, param_total)

    all_total = prop_total + op_total + param_total
    all_doc = prop_doc + op_doc + param_doc
    overall = pct(all_doc, all_total)

    table = Table(title="OpenAPI Description Coverage", show_header=True)
    table.add_column("Category", style="bold")
    table.add_column("Documented", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Coverage", justify="right")

    def _fmt_pct(p: int) -> str:
        color = "green" if p >= 80 else ("yellow" if p >= 50 else "red")
        return f"[{color}]{p}%[/{color}]"

    table.add_row("Schema properties", str(prop_doc), str(prop_total), _fmt_pct(prop_pct))
    table.add_row("Operations", str(op_doc), str(op_total), _fmt_pct(op_pct))
    table.add_row("Parameters", str(param_doc), str(param_total), _fmt_pct(param_pct))
    table.add_row(
        "[bold]Overall[/bold]",
        f"[bold]{all_doc}[/bold]",
        f"[bold]{all_total}[/bold]",
        f"[bold]{_fmt_pct(overall)}[/bold]",
    )
    console.print(table)

    if verbose and (prop_missing or op_missing or param_missing):
        if prop_missing:
            console.print("\n[yellow]Schema properties missing descriptions:[/yellow]")
            for name in prop_missing:
                console.print(f"  [dim]·[/dim] {name}")
        if op_missing:
            console.print("\n[yellow]Operations missing descriptions:[/yellow]")
            for name in op_missing:
                console.print(f"  [dim]·[/dim] {name}")
        if param_missing:
            console.print("\n[yellow]Parameters missing descriptions:[/yellow]")
            for name in param_missing:
                console.print(f"  [dim]·[/dim] {name}")

    if min_coverage > 0 and overall < min_coverage:
        console.print(
            f"\n[red]✗ Overall coverage {overall}% is below --min-coverage {min_coverage}%.[/red]"
        )
        console.print("[dim]Run `make annotate-rust` to auto-annotate Rust models with Claude.[/dim]")
        sys.exit(1)
    elif min_coverage > 0:
        console.print(f"\n[green]✓ Coverage {overall}% meets minimum {min_coverage}%.[/green]")


if __name__ == "__main__":
    main()
