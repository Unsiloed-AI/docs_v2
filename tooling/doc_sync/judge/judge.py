"""
LLM judge — validates an MDX documentation page against source code and spec.

Uses Claude with a structured rubric to detect inaccuracies, missing fields,
and hallucinations. Returns a JudgeResult with per-dimension scores and a list
of actionable issues.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from doc_sync import config

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_JUDGE_PROMPT_PATH = _PROMPTS_DIR / "judge_endpoint.md"

# Temperature 0.1: deterministic enough for reproducibility, preserves reasoning quality
_JUDGE_TEMPERATURE = 0.1


@dataclass
class Issue:
    severity: str        # "critical" | "minor"
    dimension: str       # "accuracy" | "completeness" | "hallucination"
    location: str        # which ParamField / section
    claim_in_doc: str
    truth_in_code: str
    fix: str


@dataclass
class JudgeResult:
    verdict: str                    # "pass" | "fail"
    scores: dict[str, int]          # {"accuracy": 4, "completeness": 5, "hallucination_count": 5}
    issues: list[Issue]
    summary: str
    reasoning: str                  # free-form chain-of-thought from the judge
    raw_response: str               # full response text for debugging

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    @property
    def critical_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "critical"]

    @property
    def minor_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "minor"]


def _load_system_prompt() -> str:
    return _JUDGE_PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_user_message(
    mdx_content: str,
    operation: dict[str, Any],
    schemas: dict[str, Any],
    source_context: str,
) -> str:
    spec_section = {
        "operation": operation,
        "referenced_schemas": _collect_schemas(operation, schemas),
    }
    parts = [
        "## UPDATED MDX DOCUMENTATION\n\n" + mdx_content,
        "## OPENAPI SPEC FOR THIS ENDPOINT\n\n```json\n"
        + json.dumps(spec_section, indent=2)
        + "\n```",
    ]
    if source_context:
        parts.append(source_context)
    return "\n\n---\n\n".join(parts)


def _collect_schemas(
    operation: dict[str, Any],
    schemas: dict[str, Any],
    max_depth: int = 2,
) -> dict[str, Any]:
    """Collect schemas referenced by the operation (depth-2 transitive expansion)."""
    refs: set[str] = set()
    _find_refs(operation, refs)
    result: dict[str, Any] = {}
    for _ in range(max_depth):
        new_refs: set[str] = set()
        for ref in refs:
            name = ref.split("/")[-1]
            if name in schemas and name not in result:
                result[name] = schemas[name]
                _find_refs(schemas[name], new_refs)
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


def _parse_judge_response(raw: str) -> tuple[str, dict[str, Any]]:
    """
    Split the raw response into (reasoning, verdict_dict).
    The reasoning is everything before the final ```json block.
    The verdict is parsed from that block.
    """
    # Find the last ```json ... ``` block
    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if not json_match:
        raise ValueError("Judge response did not contain a ```json block.")

    json_str = json_match.group(1)
    reasoning = raw[: json_match.start()].strip()

    try:
        verdict = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Judge JSON block is not valid JSON: {e}\n\nRaw:\n{json_str}") from e

    return reasoning, verdict


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


def judge_file(
    mdx_content: str,
    operation: dict[str, Any],
    schemas: dict[str, Any],
    source_context: str = "",
    model: str = "claude-opus-4-6",
    bedrock: bool = False,
    vertex: bool = False,
) -> JudgeResult:
    """
    Run the LLM judge on an MDX file and return a structured JudgeResult.

    On any failure (API error, parse error), returns a JudgeResult with
    verdict="fail" and a single meta-issue describing the failure — so the
    caller always gets a usable object back.
    """
    client = _make_client(bedrock=bedrock, vertex=vertex)
    system_prompt = _load_system_prompt()
    user_message = _build_user_message(mdx_content, operation, schemas, source_context)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=_JUDGE_TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text
    except Exception as e:
        return _error_result(f"Judge API call failed: {e}")

    try:
        reasoning, verdict_dict = _parse_judge_response(raw)
    except ValueError as e:
        return _error_result(f"Could not parse judge response: {e}", raw_response=raw)

    issues = [
        Issue(
            severity=i.get("severity", "minor"),
            dimension=i.get("dimension", "accuracy"),
            location=i.get("location", ""),
            claim_in_doc=i.get("claim_in_doc", ""),
            truth_in_code=i.get("truth_in_code", ""),
            fix=i.get("fix", ""),
        )
        for i in verdict_dict.get("issues", [])
    ]

    return JudgeResult(
        verdict=verdict_dict.get("verdict", "fail"),
        scores=verdict_dict.get("scores", {}),
        issues=issues,
        summary=verdict_dict.get("summary", ""),
        reasoning=reasoning,
        raw_response=raw,
    )


def _error_result(message: str, raw_response: str = "") -> JudgeResult:
    return JudgeResult(
        verdict="fail",
        scores={},
        issues=[
            Issue(
                severity="critical",
                dimension="accuracy",
                location="judge",
                claim_in_doc="",
                truth_in_code="",
                fix=message,
            )
        ],
        summary=message,
        reasoning="",
        raw_response=raw_response,
    )
