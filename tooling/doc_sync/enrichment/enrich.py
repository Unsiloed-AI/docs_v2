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
from dotenv import load_dotenv

# Load .env from the tooling directory (docs_v2/tooling/.env)
load_dotenv(Path(__file__).parent.parent.parent / ".env")

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "enrich_endpoint.md"

_BEDROCK_DEFAULT_MODEL = "us.anthropic.claude-opus-4-5-20251101-v1:0"
_BEDROCK_REGION = "us-east-1"


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


def _make_client(bedrock: bool = False) -> anthropic.Anthropic | anthropic.AnthropicBedrock:
    if bedrock:
        return anthropic.AnthropicBedrock(aws_region=_BEDROCK_REGION)
    return anthropic.Anthropic()


def enrich_file(
    mdx_raw: str,
    operation: dict[str, Any],
    schemas: dict[str, Any],
    model: str = "claude-sonnet-4-6",
    bedrock: bool = False,
) -> str:
    """
    Call Claude to update the MDX file based on the current spec.
    Returns the full updated MDX string.

    Set bedrock=True to route via Amazon Bedrock using the current AWS credentials.
    When bedrock=True the model should be a Bedrock inference profile ID such as
    "us.anthropic.claude-opus-4-6-v1".
    """
    client = _make_client(bedrock=bedrock)
    system_prompt = _load_system_prompt()
    user_message = _build_user_message(mdx_raw, operation, schemas)

    message = client.messages.create(
        model=model,
        max_tokens=8192,
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
