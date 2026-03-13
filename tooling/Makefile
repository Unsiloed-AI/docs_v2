TOOLING_DIR := $(CURDIR)
DOCS_ROOT   := $(CURDIR)/..
PARSER_DIR  := $(CURDIR)/../../parser
SPEC_V1     := $(PARSER_DIR)/docs/openapi/v1.json
SPEC_V2     := $(PARSER_DIR)/docs/openapi/v2.json

# Provider flag: override with PROVIDER=--bedrock or PROVIDER=--vertex
PROVIDER    ?= --vertex

.PHONY: export-spec copy-specs \
        sync-docs sync-docs-v2 sync-docs-dry sync-docs-v2-dry \
        sync-docs-judged sync-docs-v2-judged \
        judge-docs judge-docs-v2 \
        generate-inventory spec-coverage \
        generate-mdx-stubs

# ── Spec export ──────────────────────────────────────────────────────────────

## Generate v1.json and v2.json from the Rust utoipa annotations.
export-spec:
	cd $(PARSER_DIR)/core && cargo run --bin dump-openapi

## Copy generated specs into the docs repo for Mintlify rendering.
copy-specs: export-spec
	cp $(SPEC_V1) $(DOCS_ROOT)/api-reference/parser/openapi-v1.json
	cp $(SPEC_V2) $(DOCS_ROOT)/api-reference/parser/openapi-v2.json

# ── Doc sync ─────────────────────────────────────────────────────────────────

## Sync all v1 MDX files to the current spec (writes files).
sync-docs: export-spec
	uv run doc-sync \
		--spec $(SPEC_V1) \
		--docs-root $(DOCS_ROOT) \
		$(PROVIDER)

## Sync all v2 MDX files to the current spec (writes files).
sync-docs-v2: export-spec
	uv run doc-sync \
		--spec $(SPEC_V2) \
		--docs-root $(DOCS_ROOT) \
		$(PROVIDER)

## Preview what sync-docs would change for v1 — no files written.
sync-docs-dry: export-spec
	uv run doc-sync \
		--spec $(SPEC_V1) \
		--docs-root $(DOCS_ROOT) \
		$(PROVIDER) \
		--dry-run

## Preview what sync-docs-v2 would change — no files written.
sync-docs-v2-dry: export-spec
	uv run doc-sync \
		--spec $(SPEC_V2) \
		--docs-root $(DOCS_ROOT) \
		$(PROVIDER) \
		--dry-run

# ── Sync + judge ─────────────────────────────────────────────────────────────

## Sync v1 MDX files, run LLM judge, and revise any files that fail.
sync-docs-judged: export-spec
	uv run doc-sync \
		--spec $(SPEC_V1) \
		--docs-root $(DOCS_ROOT) \
		--source-root $(PARSER_DIR) \
		$(PROVIDER) \
		--judge --revise

## Sync v2 MDX files, run LLM judge, and revise any files that fail.
sync-docs-v2-judged: export-spec
	uv run doc-sync \
		--spec $(SPEC_V2) \
		--docs-root $(DOCS_ROOT) \
		--source-root $(PARSER_DIR) \
		$(PROVIDER) \
		--judge --revise

# ── Judge only ───────────────────────────────────────────────────────────────

## Validate existing v1 MDX files without resyncing. Exits 1 if issues found (CI-safe).
judge-docs: export-spec
	uv run doc-judge \
		--spec $(SPEC_V1) \
		--docs-root $(DOCS_ROOT) \
		--source-root $(PARSER_DIR) \
		$(PROVIDER) \
		--fail-on-issues

## Validate existing v2 MDX files without resyncing.
judge-docs-v2: export-spec
	uv run doc-judge \
		--spec $(SPEC_V2) \
		--docs-root $(DOCS_ROOT) \
		--source-root $(PARSER_DIR) \
		$(PROVIDER) \
		--fail-on-issues

# ── Inventory & coverage ─────────────────────────────────────────────────────

## Generate the full API inventory Markdown from the v1 spec.
generate-inventory: export-spec
	uv run doc-inventory \
		--spec $(SPEC_V1) \
		--output $(PARSER_DIR)/docs/api-documentation/parse-api-inventory.md

## Report spec description coverage. Fails if overall < 80%.
spec-coverage: export-spec
	uv run doc-coverage \
		--spec $(SPEC_V1) \
		--min-coverage 80 \
		--verbose

# ── Stub generation ──────────────────────────────────────────────────────────

## Scaffold a new MDX file for an operation not yet documented.
## Usage: make generate-mdx-stubs OP="POST /v2/parse/upload" OUT=api-reference/parser/parse-document-v2.mdx
generate-mdx-stubs: export-spec
	uv run doc-stub \
		--spec $(SPEC_V1) \
		--docs-root $(DOCS_ROOT) \
		--operation "$(OP)" \
		--output "$(OUT)" \
		$(PROVIDER)
