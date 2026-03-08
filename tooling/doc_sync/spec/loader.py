"""
Parse openapi.json and index operations for fast lookup.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load(spec_path: str | Path) -> dict[str, Any]:
    """Load the full OpenAPI spec from a JSON file."""
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(
            f"OpenAPI spec not found at {path}. "
            "Run `make export-spec` first."
        )
    with open(path) as f:
        return json.load(f)


import re as _re

_PATH_PARAM_RE = _re.compile(r"\{[^}]+\}")


def _normalize_path(path: str) -> str:
    """Replace all path parameter names with `{*}` for fuzzy matching.

    Example: /parse/{task_id}  →  /parse/{*}
    """
    return _PATH_PARAM_RE.sub("{*}", path)


def index_operations(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Build a lookup map: "METHOD /path" -> operation object.

    Keys are stored both as exact ("GET /parse/{task_id}") and normalized
    ("GET /parse/{*}") so that MDX files using different param names
    (e.g. {job_id} vs {task_id}) still match correctly.
    """
    index: dict[str, dict[str, Any]] = {}
    paths = spec.get("paths", {})

    for path, path_item in paths.items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            operation = path_item.get(method)
            if operation is None:
                continue

            entry = {
                "method": method.upper(),
                "path": path,
                "operation": operation,
                "operation_id": operation.get("operationId", ""),
                "summary": operation.get("summary", ""),
                "description": operation.get("description", ""),
                "parameters": operation.get("parameters", []),
                "request_body": operation.get("requestBody"),
                "responses": operation.get("responses", {}),
                "tags": operation.get("tags", []),
            }

            exact_key = f"{method.upper()} {path}"
            normalized_key = f"{method.upper()} {_normalize_path(path)}"

            index[exact_key] = entry
            # Only add normalized key if it differs (avoids overwriting with
            # a different operation that shares a normalized path)
            if normalized_key not in index:
                index[normalized_key] = entry

    return index


def get_schemas(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the components/schemas section of the spec."""
    return spec.get("components", {}).get("schemas", {})
