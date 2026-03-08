#!/usr/bin/env python3
"""
generate_inventory.py — Auto-generate parse-api-inventory.md from openapi.json.

Reads the OpenAPI spec and produces a structured Markdown reference covering
every endpoint, parameter, response field, schema, and enum — replacing the
hand-written parse-api-inventory.md.

Usage:
    uv run generate_inventory.py --spec ../../parser/openapi.json
    uv run generate_inventory.py --spec ../../parser/openapi.json \
        --output ../../parser/docs/api-documentation/parse-api-inventory.md
    uv run generate_inventory.py --spec ../../parser/openapi.json --endpoint /parse
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_ref(ref: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Follow a $ref like '#/components/schemas/Foo' and return the schema."""
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        node = node[part]
    return node


def _get_schema(obj: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in obj:
        return _resolve_ref(obj["$ref"], spec)
    return obj


def _type_str(schema: dict[str, Any], spec: dict[str, Any]) -> str:
    """Human-readable type string for a schema node."""
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    t = schema.get("type", "")
    fmt = schema.get("format", "")
    if t == "array":
        items = schema.get("items", {})
        return f"{_type_str(items, spec)}[]"
    if t == "object":
        return "object"
    if fmt:
        return f"{t} ({fmt})"
    if schema.get("anyOf") or schema.get("oneOf"):
        variants = schema.get("anyOf") or schema.get("oneOf")
        return " | ".join(_type_str(v, spec) for v in variants)
    if schema.get("allOf"):
        return _type_str(schema["allOf"][0], spec)
    return t or "any"


def _default_str(schema: dict[str, Any]) -> str:
    if "default" in schema:
        return f"`{schema['default']}`"
    return ""


def _enum_str(schema: dict[str, Any]) -> str:
    if "enum" in schema:
        return ", ".join(f"`{v}`" for v in schema["enum"])
    return ""


def _required_marker(name: str, required: list[str]) -> str:
    return "✓" if name in required else ""


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(cells)) + " |"

    sep = "| " + " | ".join("-" * w for w in col_widths) + " |"
    lines = [fmt_row(headers), sep] + [fmt_row(row) for row in rows]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_endpoint_section(
    method: str,
    path: str,
    operation: dict[str, Any],
    spec: dict[str, Any],
) -> str:
    lines: list[str] = []
    op_id = operation.get("operationId", f"{method}_{path}")
    summary = operation.get("summary", "")
    description = operation.get("description", "")
    tags = operation.get("tags", [])

    lines.append(f"### `{method.upper()} {path}`")
    if summary:
        lines.append(f"\n**{summary}**")
    if tags:
        lines.append(f"\nTag: `{'`, `'.join(tags)}`")
    if description:
        lines.append(f"\n{description}")

    # Parameters
    params = operation.get("parameters", [])
    if params:
        lines.append("\n**Parameters**\n")
        rows = []
        for p in params:
            schema = _get_schema(p.get("schema", {}), spec)
            rows.append([
                f"`{p['name']}`",
                p.get("in", ""),
                _type_str(schema, spec),
                "✓" if p.get("required") else "",
                _default_str(schema),
                p.get("description", "").replace("\n", " "),
            ])
        lines.append(_md_table(
            ["Name", "In", "Type", "Req", "Default", "Description"],
            rows,
        ))

    # Request body
    req_body = operation.get("requestBody", {})
    if req_body:
        lines.append("\n**Request Body**\n")
        for content_type, content in req_body.get("content", {}).items():
            schema = _get_schema(content.get("schema", {}), spec)
            if schema.get("type") == "object" or "properties" in schema:
                props = schema.get("properties", {})
                required_fields = schema.get("required", [])
                rows = []
                for field_name, field_schema in props.items():
                    resolved = _get_schema(field_schema, spec)
                    enum_vals = _enum_str(resolved)
                    desc = resolved.get("description", "").replace("\n", " ")
                    if enum_vals:
                        desc = f"{desc} Values: {enum_vals}".strip()
                    rows.append([
                        f"`{field_name}`",
                        _type_str(field_schema, spec),
                        _required_marker(field_name, required_fields),
                        _default_str(resolved),
                        desc,
                    ])
                if rows:
                    lines.append(f"Content-Type: `{content_type}`\n")
                    lines.append(_md_table(
                        ["Field", "Type", "Req", "Default", "Description"],
                        rows,
                    ))
            else:
                ref_name = content.get("schema", {}).get("$ref", "").split("/")[-1]
                if ref_name:
                    lines.append(f"See schema: [`{ref_name}`](#{ref_name.lower()})")

    # Responses
    responses = operation.get("responses", {})
    if responses:
        lines.append("\n**Responses**\n")
        rows = []
        for status_code, response in sorted(responses.items()):
            desc = response.get("description", "")
            content = response.get("content", {})
            schema_ref = ""
            for ct, ct_data in content.items():
                s = ct_data.get("schema", {})
                if "$ref" in s:
                    schema_ref = f"[`{s['$ref'].split('/')[-1]}`](#{s['$ref'].split('/')[-1].lower()})"
            rows.append([str(status_code), desc, schema_ref])
        lines.append(_md_table(["Status", "Description", "Schema"], rows))

    return "\n".join(lines)


def _build_schema_section(
    schema_name: str,
    schema: dict[str, Any],
    spec: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(f"### `{schema_name}`")

    top_desc = schema.get("description", "")
    if top_desc:
        lines.append(f"\n{top_desc}")

    # Enum schema
    if "enum" in schema:
        lines.append("\n**Enum values**\n")
        rows = [[f"`{v}`", ""] for v in schema["enum"]]
        lines.append(_md_table(["Value", "Description"], rows))
        return "\n".join(lines)

    # Object schema
    props = schema.get("properties", {})
    required_fields = schema.get("required", [])
    if props:
        lines.append("\n**Properties**\n")
        rows = []
        for field_name, field_schema in props.items():
            resolved = _get_schema(field_schema, spec)
            enum_vals = _enum_str(resolved)
            desc = resolved.get("description", "").replace("\n", " ")
            if enum_vals:
                desc = f"{desc} Values: {enum_vals}".strip()
            rows.append([
                f"`{field_name}`",
                _type_str(field_schema, spec),
                _required_marker(field_name, required_fields),
                _default_str(resolved),
                desc,
            ])
        lines.append(_md_table(
            ["Field", "Type", "Req", "Default", "Description"],
            rows,
        ))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate(spec: dict[str, Any], endpoint_filter: str | None = None) -> str:
    paths = spec.get("paths", {})
    schemas = spec.get("components", {}).get("schemas", {})
    info = spec.get("info", {})

    lines: list[str] = []

    # Header
    lines.append(f"# {info.get('title', 'API')} — Reference Inventory")
    lines.append(
        f"\n> Auto-generated from `openapi.json`. "
        f"Do not edit manually — run `make generate-inventory` to regenerate."
    )
    lines.append(f"\n**Version:** {info.get('version', 'unknown')}")

    # Endpoint overview table
    lines.append("\n---\n\n## Endpoints\n")
    overview_rows = []
    for path, path_item in sorted(paths.items()):
        if endpoint_filter and endpoint_filter not in path:
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not op:
                continue
            overview_rows.append([
                f"`{method.upper()}`",
                f"`{path}`",
                op.get("summary", ""),
                ", ".join(op.get("tags", [])),
            ])
    if overview_rows:
        lines.append(_md_table(["Method", "Path", "Summary", "Tags"], overview_rows))

    # Detailed endpoint sections
    lines.append("\n---\n\n## Endpoint Details\n")
    for path, path_item in sorted(paths.items()):
        if endpoint_filter and endpoint_filter not in path:
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not op:
                continue
            lines.append("\n" + _build_endpoint_section(method, path, op, spec))
            lines.append("\n---")

    # Schema reference
    lines.append("\n## Schema Reference\n")
    for schema_name, schema in sorted(schemas.items()):
        if endpoint_filter:
            # Only include schemas referenced by matching endpoints
            pass
        lines.append("\n" + _build_schema_section(schema_name, schema, spec))
        lines.append("\n---")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--spec",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to openapi.json",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(dir_okay=False),
    help="Output path for generated Markdown. Defaults to stdout.",
)
@click.option(
    "--endpoint",
    default=None,
    help="Filter to a specific path prefix, e.g. /parse",
)
def main(spec: str, output: str | None, endpoint: str | None) -> None:
    data = json.loads(Path(spec).read_text(encoding="utf-8"))
    inventory = generate(data, endpoint_filter=endpoint)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(inventory, encoding="utf-8")
        console.print(f"[green]✓[/green] Inventory written to [bold]{out_path}[/bold]")
        console.print(f"  {inventory.count(chr(10))+1} lines, {len(inventory)} bytes")
    else:
        sys.stdout.write(inventory)


if __name__ == "__main__":
    main()
