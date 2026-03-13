#!/usr/bin/env python3
"""
judge — validate existing MDX files against the current spec and source code.

Runs the LLM judge on already-written MDX files without re-generating them.
Useful as a standalone CI check or for auditing docs that were written manually.

Usage:
    # Validate all MDX files
    uv run doc-judge \\
        --spec ../../parser/docs/openapi/v1.json \\
        --docs-root .. \\
        --source-root ../../parser

    # Validate a single file
    uv run doc-judge \\
        --spec ../../parser/docs/openapi/v1.json \\
        --docs-root .. \\
        --source-root ../../parser \\
        --file api-reference/parser/parse-document.mdx \\
        --fail-on-issues
"""
from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from doc_sync.spec import loader as load_spec
from doc_sync.mdx import loader as load_mdx
from doc_sync.judge import judge as judge_module
from doc_sync.judge.source_collector import collect_source_context
from doc_sync.mdx.writer import FileResult, print_judge_report

console = Console()


@click.command()
@click.option(
    "--spec",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to openapi.json.",
)
@click.option(
    "--docs-root",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Root of the Mintlify docs repo (contains api-reference/).",
)
@click.option(
    "--source-root",
    default=None,
    type=click.Path(file_okay=False),
    help="Path to the API source repo root (for Rust source code collection).",
)
@click.option(
    "--file",
    "target_file",
    default=None,
    type=str,
    help="Validate only this MDX file (relative to docs-root).",
)
@click.option(
    "--model",
    default=None,
    show_default=False,
    help=(
        "Claude model ID for the judge. Defaults to 'claude-opus-4-6' (Anthropic API) or "
        "'us.anthropic.claude-opus-4-6-20250514-v1:0' (Bedrock)."
    ),
)
@click.option(
    "--bedrock",
    is_flag=True,
    default=False,
    help="Route requests via Amazon Bedrock.",
)
@click.option(
    "--vertex",
    is_flag=True,
    default=False,
    help="Route requests via Google Cloud Vertex AI (uses GOOGLE_APPLICATION_CREDENTIALS).",
)
@click.option(
    "--fail-on-issues",
    is_flag=True,
    default=False,
    help="Exit with code 1 if any file fails the judge.",
)
def main(
    spec: str,
    docs_root: str,
    source_root: str | None,
    target_file: str | None,
    model: str | None,
    bedrock: bool,
    vertex: bool,
    fail_on_issues: bool,
) -> None:
    from doc_sync import config

    if bedrock and vertex:
        console.print("[red]Cannot use both --bedrock and --vertex.[/red]")
        raise SystemExit(1)

    if model is None:
        if vertex:
            model = config.VERTEX_JUDGE_MODEL
        elif bedrock:
            model = config.BEDROCK_JUDGE_MODEL
        else:
            model = "claude-opus-4-6"

    spec_path = Path(spec).resolve()
    docs_path = Path(docs_root).resolve()
    source_path = Path(source_root).resolve() if source_root else None

    if source_path is None:
        console.print(
            "[yellow]⚠[/yellow] --source-root not provided. "
            "Judge will rely on spec only — source code grounding disabled."
        )

    # ── Load spec ─────────────────────────────────────────────────────────────
    console.rule("[bold blue]Loading OpenAPI spec")
    full_spec = load_spec.load(spec_path)
    operations = load_spec.index_operations(full_spec)
    schemas = load_spec.get_schemas(full_spec)
    console.print(
        f"  [green]✓[/green] {len(operations)} operations, {len(schemas)} schemas"
    )

    # ── Discover MDX files ────────────────────────────────────────────────────
    console.rule("[bold blue]Discovering MDX files")
    all_mdx = load_mdx.discover(docs_path)

    if target_file:
        target_path = (docs_path / target_file).resolve()
        all_mdx = [f for f in all_mdx if f.path.resolve() == target_path]
        if not all_mdx:
            console.print(f"[red]No MDX file with openapi: frontmatter found at {target_file}[/red]")
            raise SystemExit(1)

    matched: list[load_mdx.MdxFile] = []
    for mdx_file in all_mdx:
        key = mdx_file.operation_key
        norm_key = mdx_file.operation_key_normalized
        resolved = key if key in operations else (norm_key if norm_key in operations else None)
        if resolved:
            mdx_file.operation_key = resolved
            matched.append(mdx_file)
        else:
            console.print(f"  [yellow]⚠[/yellow] {mdx_file.path.name} — operation not in spec, skipping")

    console.print(f"  [green]✓[/green] {len(matched)} file(s) to judge")

    # ── Judge each file ───────────────────────────────────────────────────────
    console.rule("[bold blue]Running LLM Judge")
    any_failed = False
    results: list[FileResult] = []

    for mdx_file in matched:
        operation_data = operations[mdx_file.operation_key]
        console.print(f"  [cyan]⚖[/cyan] {mdx_file.path.name}  ({mdx_file.operation_key})")

        source_context = ""
        if source_path:
            source_context = collect_source_context(mdx_file.operation_key, source_path)
            if source_context:
                console.print(f"    [dim]Source: {len(source_context)} chars[/dim]")

        try:
            jr = judge_module.judge_file(
                mdx_content=mdx_file.raw_text,
                operation=operation_data,
                schemas=schemas,
                source_context=source_context,
                model=model,
                bedrock=bedrock,
                vertex=vertex,
            )
        except Exception as e:
            console.print(f"    [red]✗ Judge call failed: {e}[/red]")
            continue

        result = FileResult(
            path=mdx_file.path,
            original=mdx_file.raw_text,
            updated=mdx_file.raw_text,
            operation_key=mdx_file.operation_key,
            judge_result=jr,
        )
        results.append(result)

        if jr.passed:
            console.print(f"    [green]✓ PASS[/green]  {jr.summary}")
        else:
            any_failed = True
            console.print(f"    [red]✗ FAIL[/red]  {jr.summary}")

    # ── Print detailed reports ────────────────────────────────────────────────
    console.rule("[bold blue]Judge Reports")
    for result in results:
        print_judge_report(result)

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r.judge_result and r.judge_result.passed)
    failed = len(results) - passed
    console.print()
    console.print(
        f"  [bold]{passed}[/bold] passed  "
        f"[bold {'red' if failed else 'dim'}]{failed}[/bold] failed  "
        f"[dim]{len(matched) - len(results)} skipped (judge errors)[/dim]"
    )

    if fail_on_issues and any_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
