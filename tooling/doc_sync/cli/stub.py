#!/usr/bin/env python3
"""
stub — Generate a new Mintlify MDX file from scratch for an API operation.

Reads the OpenAPI spec, finds the requested operation, and asks Claude to
produce a complete MDX file with frontmatter, ParamField/ResponseField blocks,
prose overview, and code examples.

Usage:
    uv run doc-stub \\
        --spec ../../parser/docs/openapi/v2.json \\
        --docs-root .. \\
        --operation "POST /v2/parse/upload" \\
        --output api-reference/parser/parse-document-v2.mdx

    # Dry run — print to stdout instead of writing
    uv run doc-stub \\
        --spec ../../parser/docs/openapi/v2.json \\
        --docs-root .. \\
        --operation "GET /parse/{task_id}" \\
        --dry-run
"""
from __future__ import annotations

import json
from pathlib import Path

import anthropic
import click
from rich.console import Console

from doc_sync.spec import loader as load_spec

console = Console()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt() -> str:
    path = _PROMPTS_DIR / "generate_stub.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        "You are an expert technical writer creating Mintlify API documentation. "
        "Generate a complete MDX file for the given OpenAPI operation. "
        "Include frontmatter, overview prose, ParamField/ResponseField blocks, "
        "and cURL/Python/JavaScript code examples. "
        "Return ONLY the MDX content — no explanation, no code fences."
    )


@click.command()
@click.option(
    "--spec",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to openapi.json",
)
@click.option(
    "--docs-root",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Root of the Mintlify docs repo (contains api-reference/).",
)
@click.option(
    "--operation",
    required=True,
    help='Operation to document, e.g. "POST /v2/parse/upload".',
)
@click.option(
    "--output",
    default=None,
    type=str,
    help="Output path relative to docs-root. Defaults to stdout (--dry-run implied).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print generated content to stdout; do not write any files.",
)
@click.option(
    "--model",
    default=None,
    show_default=False,
    help=(
        "Claude model ID. Defaults to 'claude-sonnet-4-6' (Anthropic API) or "
        "'us.anthropic.claude-opus-4-6-v1' (Bedrock)."
    ),
)
@click.option(
    "--bedrock",
    is_flag=True,
    default=False,
    help="Route requests via Amazon Bedrock using the current AWS credentials.",
)
def main(
    spec: str,
    docs_root: str,
    operation: str,
    output: str | None,
    dry_run: bool,
    model: str | None,
    bedrock: bool,
) -> None:
    from doc_sync.enrichment.enrich import _BEDROCK_DEFAULT_MODEL
    if model is None:
        model = _BEDROCK_DEFAULT_MODEL if bedrock else "claude-sonnet-4-6"
    spec_path = Path(spec).resolve()
    docs_path = Path(docs_root).resolve()

    # ── Load spec ─────────────────────────────────────────────────────────────
    full_spec = load_spec.load(spec_path)
    operations = load_spec.index_operations(full_spec)
    schemas = load_spec.get_schemas(full_spec)

    # ── Resolve operation ─────────────────────────────────────────────────────
    op_parts = operation.strip().split(None, 1)
    if len(op_parts) != 2:
        console.print(f"[red]Invalid --operation format. Expected 'METHOD /path', got: {operation!r}[/red]")
        raise SystemExit(1)

    method, path = op_parts
    key = f"{method.upper()} {path}"

    if key not in operations:
        available = "\n  ".join(sorted(operations.keys()))
        console.print(f"[red]Operation {key!r} not found in spec.[/red]")
        console.print(f"[dim]Available operations:\n  {available}[/dim]")
        raise SystemExit(1)

    operation_data = operations[key]
    console.print(f"  [cyan]→[/cyan] Generating stub for [bold]{key}[/bold]")

    # ── Determine output path ─────────────────────────────────────────────────
    if output:
        # Convert to a spec-relative frontmatter reference
        # e.g. "api-reference/parser/parse-document-v2.mdx" → "/api-reference/parser/openapi-v2.json POST /v2/parse/upload"
        spec_filename = spec_path.name
        spec_rel = f"/api-reference/parser/{spec_filename}"
        frontmatter_openapi = f"{spec_rel} {key}"
    else:
        spec_rel = f"/api-reference/parser/{spec_path.name}"
        frontmatter_openapi = f"{spec_rel} {key}"
        dry_run = True

    # ── Call Claude ────────────────────────────────────────────────────────────
    system_prompt = _load_prompt()
    user_message = (
        f"Generate a complete Mintlify MDX documentation page for this API operation.\n\n"
        f"Frontmatter `openapi` value to use exactly: `{frontmatter_openapi}`\n\n"
        f"## Operation JSON\n\n```json\n{json.dumps(operation_data, indent=2)}\n```\n\n"
        f"## Referenced Schemas\n\n```json\n{json.dumps(schemas, indent=2)}\n```"
    )

    try:
        if bedrock:
            client = anthropic.AnthropicBedrock(aws_region="us-east-1")
        else:
            client = anthropic.Anthropic()
        message = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        content = message.content[0].text
    except Exception as e:
        console.print(f"[red]✗ Claude call failed: {e}[/red]")
        raise SystemExit(1)

    # ── Write or print ─────────────────────────────────────────────────────────
    if dry_run or not output:
        console.rule("[dim]Generated MDX[/dim]")
        console.print(content)
        console.rule()
        if not output:
            console.print("[dim]No --output specified — printed to stdout.[/dim]")
        else:
            console.print("[dim]Dry run — file not written.[/dim]")
    else:
        out_path = docs_path / output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        console.print(f"  [green]✓[/green] Written to [bold]{out_path}[/bold]")
        console.print(f"    {content.count(chr(10)) + 1} lines")


if __name__ == "__main__":
    main()
