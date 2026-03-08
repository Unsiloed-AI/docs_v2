"""
Integration tests for the end-to-end sync pipeline.

These tests run without a real Claude API key.
The enrichment step is mocked to return the original MDX unchanged —
we test that the pipeline correctly discovers files, matches operations,
and calls the writer with the right data.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from doc_sync.spec import loader as load_spec
from doc_sync.mdx import loader as load_mdx
from doc_sync.mdx.writer import FileResult, write_results

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def sample_spec_path(tmp_path: Path) -> Path:
    src = (FIXTURES / "sample_spec.json").read_text()
    dest = tmp_path / "spec.json"
    dest.write_text(src)
    return dest


@pytest.fixture()
def sample_docs_root(tmp_path: Path) -> Path:
    api_ref = tmp_path / "api-reference" / "sample"
    api_ref.mkdir(parents=True)
    sample_mdx = FIXTURES / "sample.mdx"
    (api_ref / "sample.mdx").write_text(sample_mdx.read_text(), encoding="utf-8")
    return tmp_path


class TestEndToEndPipeline:
    def test_spec_loads_and_indexes_correctly(self, sample_spec_path):
        full_spec = load_spec.load(sample_spec_path)
        operations = load_spec.index_operations(full_spec)
        assert "POST /sample" in operations
        assert "GET /sample/{id}" in operations

    def test_mdx_discovery_finds_fixture(self, sample_docs_root):
        results = load_mdx.discover(sample_docs_root)
        assert len(results) == 1
        assert results[0].operation_key == "POST /sample"

    def test_full_pipeline_with_mocked_enrich(self, sample_spec_path, sample_docs_root):
        full_spec = load_spec.load(sample_spec_path)
        operations = load_spec.index_operations(full_spec)
        schemas = load_spec.get_schemas(full_spec)

        mdx_files = load_mdx.discover(sample_docs_root)
        assert mdx_files, "No MDX files discovered — check fixture"

        results: list[FileResult] = []
        for mdx_file in mdx_files:
            key = mdx_file.operation_key
            norm_key = mdx_file.operation_key_normalized
            resolved_key = key if key in operations else (norm_key if norm_key in operations else None)

            if resolved_key is None:
                continue

            # Mock the enrich call — returns original unchanged
            with patch("doc_sync.enrichment.enrich.enrich_file", return_value=mdx_file.raw_text):
                from doc_sync.enrichment import enrich
                updated = enrich.enrich_file(
                    mdx_raw=mdx_file.raw_text,
                    operation=operations[resolved_key],
                    schemas=schemas,
                    model="claude-sonnet-4-6",
                )

            results.append(FileResult(
                path=mdx_file.path,
                original=mdx_file.raw_text,
                updated=updated,
                operation_key=resolved_key,
            ))

        assert len(results) == 1

        # Dry run — no files written
        write_results(results, dry_run=True, show_diff=False)
        # File unchanged on disk
        assert results[0].path.read_text() == results[0].original

    def test_unmatched_operation_is_skipped(self, sample_docs_root, tmp_path):
        # Build a spec with NO /sample operation — MDX should be skipped
        import json
        empty_spec = {
            "openapi": "3.1.0",
            "info": {"title": "Empty", "version": "1.0.0"},
            "paths": {},
            "components": {"schemas": {}},
        }
        spec_path = tmp_path / "empty_spec.json"
        spec_path.write_text(json.dumps(empty_spec))

        full_spec = load_spec.load(spec_path)
        operations = load_spec.index_operations(full_spec)
        mdx_files = load_mdx.discover(sample_docs_root)

        matched = []
        for mdx_file in mdx_files:
            key = mdx_file.operation_key
            norm_key = mdx_file.operation_key_normalized
            if key in operations or norm_key in operations:
                matched.append(mdx_file)

        assert matched == [], "No files should match an empty spec"
