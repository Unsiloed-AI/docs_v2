"""
Claude-powered MDX enrichment.

Sends the existing MDX + relevant OpenAPI spec section to Claude
and returns the updated MDX content.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anthropic

from doc_sync import config

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "enrich_endpoint.md"


def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_user_message(
    mdx_content: str,
    operation: dict[str, Any],
    schemas: dict[str, Any],
) -> str:
    spec_section = {
        "operation": operation,
        "referenced_schemas": _collect_referenced_schemas(operation, schemas),
    }
    return (
        "## EXISTING MDX FILE\n\n"
        f"{mdx_content}\n\n"
        "## UPDATED OPENAPI SPEC FOR THIS ENDPOINT\n\n"
        f"```json\n{json.dumps(spec_section, indent=2)}\n```"
    )


def _collect_referenced_schemas(
    operation: dict[str, Any],
    schemas: dict[str, Any],
    max_depth: int = 2,
) -> dict[str, Any]:
    """Extract schema definitions referenced by this operation (shallow)."""
    # First pass: refs directly in the operation
    refs: set[str] = set()
    _find_refs(operation, refs)

    result: dict[str, Any] = {}

    # Iteratively expand refs up to max_depth without mutating the set we iterate
    for _ in range(max_depth):
        new_refs: set[str] = set()
        for ref in refs:
            name = ref.split("/")[-1]
            if name in schemas and name not in result:
                result[name] = schemas[name]
                _find_refs(schemas[name], new_refs)
        # Add newly discovered refs for the next iteration
        refs = refs | new_refs

    return result


def _find_refs(obj: Any, refs: set[str]) -> None:
    if isinstance(obj, dict):
        if "$ref" in obj:
            refs.add(obj["$ref"])
        for v in obj.values():
            _find_refs(v, refs)
    elif isinstance(obj, list):
        for item in obj:
            _find_refs(item, refs)


def _make_client(
    bedrock: bool = False,
    vertex: bool = False,
) -> anthropic.Anthropic | anthropic.AnthropicBedrock | anthropic.AnthropicVertex:
    if vertex:
        return anthropic.AnthropicVertex(
            project_id=config.VERTEX_PROJECT,
            region=config.VERTEX_REGION,
        )
    if bedrock:
        return anthropic.AnthropicBedrock(aws_region=config.BEDROCK_REGION)
    return anthropic.Anthropic()


def enrich_file(
    mdx_raw: str,
    operation: dict[str, Any],
    schemas: dict[str, Any],
    model: str = "claude-sonnet-4-6",
    bedrock: bool = False,
    vertex: bool = False,
) -> str:
    """
    Call Claude to update the MDX file based on the current spec.
    Returns the full updated MDX string.

    Set bedrock=True to route via Amazon Bedrock using the current AWS credentials.
    Set vertex=True to route via Google Cloud Vertex AI (uses GOOGLE_APPLICATION_CREDENTIALS).
    """
    client = _make_client(bedrock=bedrock, vertex=vertex)
    system_prompt = _load_system_prompt()
    user_message = _build_user_message(mdx_raw, operation, schemas)

    message = client.messages.create(
        model=model,
        max_tokens=16384,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    result = message.content[0].text.strip()

    # Ensure the output starts with frontmatter delimiter
    if not result.startswith("---"):
        # Claude sometimes adds a preamble — strip it
        idx = result.find("---")
        if idx != -1:
            result = result[idx:]

    return result


def enrich_with_critique(
    mdx_raw: str,
    operation: dict[str, Any],
    schemas: dict[str, Any],
    issues: list[Any],
    model: str = "claude-sonnet-4-6",
    bedrock: bool = False,
    vertex: bool = False,
) -> str:
    """
    Second-pass enrichment: send the current MDX + spec + judge critique back
    to the generator so it can fix the identified issues.

    `issues` is a list of judge.Issue objects (or any objects with .location,
    .claim_in_doc, .truth_in_code, .fix attributes).

    Returns the revised MDX string, or the original mdx_raw on failure.
    """
    critique_lines = ["The following issues were found in the documentation:"]
    for i, issue in enumerate(issues, 1):
        critique_lines.append(
            f"\n{i}. [{issue.severity.upper()}] {issue.location}\n"
            f"   Doc says: {issue.claim_in_doc}\n"
            f"   Truth:    {issue.truth_in_code}\n"
            f"   Fix:      {issue.fix}"
        )
    critique_block = "\n".join(critique_lines)

    base_message = _build_user_message(mdx_raw, operation, schemas)
    user_message = (
        base_message
        + "\n\n## JUDGE CRITIQUE — fix all issues listed below before returning the MDX\n\n"
        + critique_block
    )

    client = _make_client(bedrock=bedrock, vertex=vertex)
    system_prompt = _load_system_prompt()

    message = client.messages.create(
        model=model,
        max_tokens=16384,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    result = message.content[0].text.strip()

    if not result.startswith("---"):
        idx = result.find("---")
        if idx != -1:
            result = result[idx:]

    return result
