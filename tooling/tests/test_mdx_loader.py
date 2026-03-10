"""Tests for doc_sync.mdx.loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from doc_sync.mdx.loader import MdxFile, discover, _parse_operation_key

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseOperationKey:
    def test_simple_post(self):
        result = _parse_operation_key("/api-reference/openapi.json POST /parse")
        assert result is not None
        exact, normalized = result
        assert exact == "POST /parse"
        assert normalized == "POST /parse"

    def test_get_with_path_param(self):
        result = _parse_operation_key("/api-reference/openapi.json GET /parse/{task_id}")
        assert result is not None
        exact, normalized = result
        assert exact == "GET /parse/{task_id}"
        assert normalized == "GET /parse/{*}"

    def test_no_spec_file_prefix(self):
        result = _parse_operation_key("POST /v2/parse/upload")
        assert result is not None
        exact, _ = result
        assert exact == "POST /v2/parse/upload"

    def test_v2_spec_path(self):
        result = _parse_operation_key(
            "/api-reference/parser/openapi-v2.json POST /v2/parse/upload"
        )
        assert result is not None
        exact, normalized = result
        assert exact == "POST /v2/parse/upload"
        assert normalized == "POST /v2/parse/upload"

    def test_invalid_ref_returns_none(self):
        assert _parse_operation_key("not an openapi ref") is None

    def test_empty_string_returns_none(self):
        assert _parse_operation_key("") is None


class TestDiscover:
    def _make_docs_root(self, tmp_path: Path, mdx_content: str, filename: str = "test.mdx") -> Path:
        api_ref = tmp_path / "api-reference" / "parser"
        api_ref.mkdir(parents=True)
        (api_ref / filename).write_text(mdx_content, encoding="utf-8")
        return tmp_path

    def test_discovers_file_with_openapi_frontmatter(self, tmp_path):
        content = FIXTURES.joinpath("sample.mdx").read_text()
        docs_root = self._make_docs_root(tmp_path, content)
        results = discover(docs_root)
        assert len(results) == 1
        assert results[0].operation_key == "POST /sample"

    def test_skips_file_without_openapi_frontmatter(self, tmp_path):
        content = "---\ntitle: No OpenAPI\n---\n\nSome content."
        docs_root = self._make_docs_root(tmp_path, content)
        results = discover(docs_root)
        assert results == []

    def test_returns_mdx_file_dataclass(self, tmp_path):
        content = FIXTURES.joinpath("sample.mdx").read_text()
        docs_root = self._make_docs_root(tmp_path, content)
        results = discover(docs_root)
        mdx = results[0]
        assert isinstance(mdx, MdxFile)
        assert mdx.title == "Sample Endpoint"
        assert "POST /sample" in mdx.openapi_ref

    def test_normalized_key_replaces_path_params(self, tmp_path):
        content = (
            "---\ntitle: Get Result\n"
            "openapi: \"/api-reference/openapi.json GET /parse/{job_id}\"\n---\n\nContent."
        )
        docs_root = self._make_docs_root(tmp_path, content)
        results = discover(docs_root)
        assert results[0].operation_key == "GET /parse/{job_id}"
        assert results[0].operation_key_normalized == "GET /parse/{*}"

    def test_missing_api_reference_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            discover(tmp_path)

    def test_raw_text_is_preserved(self, tmp_path):
        content = FIXTURES.joinpath("sample.mdx").read_text()
        docs_root = self._make_docs_root(tmp_path, content)
        results = discover(docs_root)
        assert results[0].raw_text == content
