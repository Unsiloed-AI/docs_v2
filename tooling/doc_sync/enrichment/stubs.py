"""
Run the Mintlify scraper to generate baseline MDX stubs from the spec.
Returns a dict mapping "METHOD /path" -> stub MDX content.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import frontmatter

_OPENAPI_REF_RE = re.compile(
    r"(?:[^\s]+\s+)?"
    r"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)"
    r"\s+"
    r"(/[^\s\"']*)",
    re.IGNORECASE,
)


def generate(spec_path: str | Path) -> dict[str, str]:
    """
    Run `npx @mintlify/scraping openapi-file` and return a map of
    operation key -> stub MDX content.

    Returns an empty dict if npx / the scraper is not available.
    """
    spec_path = Path(spec_path).resolve()

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = subprocess.run(
            [
                "npx",
                "--yes",
                "@mintlify/scraping@latest",
                "openapi-file",
                str(spec_path),
                "-o",
                tmp_dir,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # Non-fatal: stubs are a nice-to-have reference, not required
            return {}

        stubs: dict[str, str] = {}
        for mdx_file in Path(tmp_dir).rglob("*.mdx"):
            raw = mdx_file.read_text(encoding="utf-8")
            post = frontmatter.loads(raw)
            openapi_ref = str(post.metadata.get("openapi", ""))
            if not openapi_ref:
                continue
            m = _OPENAPI_REF_RE.search(openapi_ref)
            if m:
                key = f"{m.group(1).upper()} {m.group(2)}"
                stubs[key] = raw

    return stubs


def validate(spec_path: str | Path) -> tuple[bool, str]:
    """Run `npx @mintlify/scraping openapi-check` and return (ok, output)."""
    result = subprocess.run(
        [
            "npx",
            "--yes",
            "@mintlify/scraping@latest",
            "openapi-check",
            str(spec_path),
        ],
        capture_output=True,
        text=True,
    )
    combined = (result.stdout + result.stderr).strip()
    return result.returncode == 0, combined
