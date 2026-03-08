"""
Discover and parse MDX files that reference an OpenAPI operation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import frontmatter

_PATH_PARAM_RE = re.compile(r"\{[^}]+\}")


@dataclass
class MdxFile:
    path: Path
    title: str
    description: str
    # The raw openapi: frontmatter value, e.g.
    # "/api-reference/openapi.json POST /parse"
    openapi_ref: str
    # Parsed out: "POST /parse"
    operation_key: str
    # Normalized form for fuzzy matching: "POST /parse/{*}"
    operation_key_normalized: str
    content: str
    raw_text: str


# Matches: optional "<spec-file> " then "METHOD /path"
_OPENAPI_REF_RE = re.compile(
    r"(?:[^\s]+\s+)?"        # optional spec file path + space
    r"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)"
    r"\s+"
    r"(/[^\s\"']*)",         # path
    re.IGNORECASE,
)


def _parse_operation_key(openapi_ref: str) -> Optional[tuple[str, str]]:
    """Extract ('METHOD /path', 'METHOD /path/{*}') from the openapi frontmatter."""
    m = _OPENAPI_REF_RE.search(openapi_ref)
    if m:
        key = f"{m.group(1).upper()} {m.group(2)}"
        normalized = f"{m.group(1).upper()} {_PATH_PARAM_RE.sub('{*}', m.group(2))}"
        return key, normalized
    return None


def discover(docs_root: str | Path) -> list[MdxFile]:
    """
    Walk api-reference/ inside docs_root and return all MDX files
    that have an `openapi:` frontmatter field.
    """
    root = Path(docs_root)
    api_ref_dir = root / "api-reference"

    if not api_ref_dir.exists():
        raise FileNotFoundError(f"api-reference/ directory not found at {api_ref_dir}")

    results: list[MdxFile] = []

    for mdx_path in sorted(api_ref_dir.rglob("*.mdx")):
        raw_text = mdx_path.read_text(encoding="utf-8")
        post = frontmatter.loads(raw_text)

        openapi_ref = post.metadata.get("openapi", "")
        if not openapi_ref:
            continue

        parsed = _parse_operation_key(str(openapi_ref))
        if parsed is None:
            continue

        operation_key, operation_key_normalized = parsed

        results.append(
            MdxFile(
                path=mdx_path,
                title=str(post.metadata.get("title", "")),
                description=str(post.metadata.get("description", "")),
                openapi_ref=str(openapi_ref),
                operation_key=operation_key,
                operation_key_normalized=operation_key_normalized,
                content=post.content,
                raw_text=raw_text,
            )
        )

    return results
