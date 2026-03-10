"""Tests for doc_sync.spec.loader."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_sync.spec import loader

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def spec_path(tmp_path: Path) -> Path:
    src = (FIXTURES / "sample_spec.json").read_text()
    dest = tmp_path / "spec.json"
    dest.write_text(src)
    return dest


@pytest.fixture()
def full_spec(spec_path: Path) -> dict:
    return loader.load(spec_path)


class TestLoad:
    def test_returns_dict(self, full_spec):
        assert isinstance(full_spec, dict)

    def test_has_paths(self, full_spec):
        assert "paths" in full_spec

    def test_has_components(self, full_spec):
        assert "components" in full_spec

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            loader.load(tmp_path / "nonexistent.json")

    def test_invalid_json_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json")
        with pytest.raises(json.JSONDecodeError):
            loader.load(bad)


class TestIndexOperations:
    def test_indexes_post(self, full_spec):
        ops = loader.index_operations(full_spec)
        assert "POST /sample" in ops

    def test_indexes_get(self, full_spec):
        ops = loader.index_operations(full_spec)
        assert "GET /sample/{id}" in ops

    def test_operation_has_summary(self, full_spec):
        ops = loader.index_operations(full_spec)
        assert ops["POST /sample"]["summary"] == "Create a sample resource"

    def test_empty_paths(self):
        ops = loader.index_operations({"paths": {}, "components": {}})
        assert ops == {}


class TestGetSchemas:
    def test_returns_schemas(self, full_spec):
        schemas = loader.get_schemas(full_spec)
        assert "SampleResponse" in schemas

    def test_empty_components(self):
        schemas = loader.get_schemas({})
        assert schemas == {}
