"""
source_collector — extract relevant source code for a given API operation.

Given an operation key like "POST /parse" and a path to the source repo root,
this module finds the Rust handler files and related model files, and returns
a condensed context string the judge can read alongside the MDX doc.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


# Patterns to detect Rust import lines that reference model files
_USE_RE = re.compile(r'^\s*use\s+crate::(models|utils)::[^;]+;', re.MULTILINE)

# Maximum total characters of source code to include.
# Opus has a 200k-token context window; 100k chars ≈ 25k tokens — well within budget.
# At this size: handler budget = 66k (fits parse.rs in full), model reserve = 33k
# (fits upload.rs in full + first ~12k of task.rs).
_DEFAULT_MAX_CHARS = 100_000


def collect_source_context(
    operation_key: str,
    source_root: Path,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """
    Return a formatted string of relevant Rust source snippets for the given operation.

    Strategy:
    1. Extract the URL path from the operation key (e.g. "/parse" from "POST /parse")
    2. Grep .rs files under source_root/core/src for that path string
    3. Include those handler files in full (up to budget)
    4. Follow crate::models / crate::upload imports to include referenced model files
    5. Truncate to max_chars total, prioritising handler files over model files

    Returns an empty string if source_root does not exist or nothing is found.
    """
    source_root = Path(source_root)
    core_src = source_root / "core" / "src"
    if not core_src.exists():
        return ""

    # Extract URL path from "METHOD /path/{param}" → "/path"
    parts = operation_key.split(" ", 1)
    url_path = parts[1] if len(parts) == 2 else operation_key
    # Use the first two segments as the search term (e.g. "/parse" from "/parse/{id}")
    search_term = "/" + url_path.strip("/").split("/")[0]

    # ── Step 1: find handler files ────────────────────────────────────────────
    all_matches = _grep_rs_files(core_src, search_term)

    # Prefer files in routes/ (actual handlers); fall back to all matches if none found
    route_files = [p for p in all_matches if "/routes/" in str(p)]
    handler_files = route_files if route_files else all_matches

    # Sort by name similarity to the URL path so the most relevant file comes first.
    # Files whose stem matches the first path segment (e.g. "parse") rank highest.
    path_stem = url_path.strip("/").split("/")[0]  # "parse" from "/parse/{id}"

    def _relevance(p: Path) -> tuple[int, int]:
        name = p.stem.lower()
        parts = str(p).split("/")
        # Penalise versioned sub-routes (v2/, v3/, …) — they're less relevant for v1 sync
        version_penalty = 1 if any(re.match(r"^v\d+$", part) for part in parts) else 0
        if name == path_stem:
            return (0 + version_penalty, 0)   # exact match → highest priority
        if path_stem in name:
            return (1 + version_penalty, 0)
        return (2 + version_penalty, 0)

    handler_files = sorted(handler_files, key=_relevance)

    # ── Step 2: follow model imports from handler files ───────────────────────
    model_files: list[Path] = []
    seen: set[Path] = set(handler_files)

    for hf in handler_files:
        try:
            text = hf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _USE_RE.finditer(text):
            # Convert "use crate::models::upload::{...}" → models/upload.rs
            stmt = match.group(0).strip().removeprefix("use crate::").split("::")[0:2]
            rel = Path(*stmt).with_suffix(".rs")
            candidate = core_src / rel
            if candidate.exists() and candidate not in seen:
                seen.add(candidate)
                model_files.append(candidate)

    # Ensure upload.rs and task.rs are always at the front of model_files — they
    # hold enum defaults and response schemas the judge needs most. Whether or not
    # the regex already found them, move/insert them first.
    must_have = [core_src / p for p in ("models/upload.rs", "models/task.rs") if (core_src / p).exists()]
    # Remove from wherever they currently sit in the list, then prepend.
    model_files = must_have + [p for p in model_files if p not in must_have]
    # Keep seen consistent.
    seen.update(must_have)

    # ── Step 3: build context string within budget ────────────────────────────
    # Reserve 30% of the budget for model files so they always get included,
    # even when the primary handler file is large.
    model_reserve = max_chars // 3
    handler_budget = max_chars - model_reserve

    sections: list[str] = []

    def _add_file(path: Path, label: str, budget: int) -> int:
        """Append file content up to budget chars. Returns chars consumed."""
        if budget <= 0:
            return 0
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return 0
        snippet = content[:budget]
        truncated = len(content) > budget
        sections.append(
            f"### {label}: {path.relative_to(source_root)}\n\n"
            f"```rust\n{snippet}"
            + (" ... [truncated]\n" if truncated else "\n")
            + "```"
        )
        return len(snippet)

    handler_remaining = handler_budget
    for path in handler_files:
        consumed = _add_file(path, "Handler", handler_remaining)
        handler_remaining -= consumed

    model_remaining = model_reserve
    for path in model_files:
        consumed = _add_file(path, "Model", model_remaining)
        model_remaining -= consumed

    if not sections:
        return ""

    header = f"## Source code context for `{operation_key}`\n\n"
    return header + "\n\n".join(sections)


def _grep_rs_files(search_dir: Path, pattern: str) -> list[Path]:
    """Return .rs files under search_dir that contain pattern (literal string match)."""
    try:
        result = subprocess.run(
            ["grep", "-rl", "--include=*.rs", pattern, str(search_dir)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode not in (0, 1):
            return []
        paths = [Path(p.strip()) for p in result.stdout.splitlines() if p.strip()]
        # Exclude test files and target/ directory
        return [
            p for p in paths
            if "target/" not in str(p) and "/tests/" not in str(p)
        ]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
