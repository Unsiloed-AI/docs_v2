# docs_v2/tooling

Claude-powered tooling for keeping any Mintlify docs site in sync with an OpenAPI spec.
The pipeline reads a generated `openapi.json`, matches it to MDX files via `openapi:` frontmatter,
and uses Claude to update parameter/response field blocks and code examples — adding new fields,
removing deleted ones, enriching descriptions, and keeping request/response examples accurate —
while leaving all hand-written prose, callouts, and accordion blocks untouched.

Works with any API that produces an OpenAPI spec, not just the parser.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- Claude access via **one** of:
  - `ANTHROPIC_API_KEY` set in your environment, **or**
  - AWS credentials with Amazon Bedrock access (use `--bedrock` flag)

```bash
# Option A — Anthropic API
export ANTHROPIC_API_KEY=sk-ant-...

# Option B — Amazon Bedrock (uses current AWS credentials, no extra env var needed)
# Pass --bedrock to any command that calls Claude
```

## Quick start (from the parser repo root)

The recommended way is via the parser `Makefile`, which handles spec export and passes
the correct paths automatically.

```bash
cd ../parser

# Preview what would change — no files written (v1)
make sync-docs-dry

# Preview what would change — no files written (v2)
make sync-docs-v2-dry

# Apply changes to all MDX files (v1 spec)
make sync-docs

# Apply changes to all MDX files (v2 spec)
make sync-docs-v2

# Generate the API inventory Markdown from the spec
make generate-inventory

# Check description coverage across the spec
make spec-coverage

# Scaffold a new MDX file for an undocumented endpoint
make generate-mdx-stubs OP="POST /v2/parse/upload" OUT=api-reference/parser/parse-document-v2.mdx
```

## Running directly

Install dependencies once, then use the CLI commands from anywhere.

```bash
cd docs_v2/tooling
uv sync

# Sync all MDX files against a spec
uv run doc-sync \
  --spec ../../parser/docs/openapi/v1.json \
  --docs-root ..

# Dry run — print diffs, write nothing
uv run doc-sync \
  --spec ../../parser/docs/openapi/v1.json \
  --docs-root .. \
  --dry-run

# Sync using Amazon Bedrock instead of the Anthropic API
uv run doc-sync \
  --spec ../../parser/docs/openapi/v1.json \
  --docs-root .. \
  --bedrock

# Sync a single file
uv run doc-sync \
  --spec ../../parser/docs/openapi/v1.json \
  --docs-root .. \
  --file api-reference/parser/parse-document.mdx

# Generate a new MDX stub for an endpoint not yet documented
uv run doc-stub \
  --spec ../../parser/docs/openapi/v2.json \
  --docs-root .. \
  --operation "POST /v2/parse/upload" \
  --output api-reference/parser/parse-document-v2.mdx

# Stub dry run — print to stdout, write nothing
uv run doc-stub \
  --spec ../../parser/docs/openapi/v2.json \
  --docs-root .. \
  --operation "POST /v2/parse/upload" \
  --dry-run

# Generate the full API inventory Markdown
uv run doc-inventory \
  --spec ../../parser/docs/openapi/v1.json \
  --output ../../parser/docs/api-documentation/parse-api-inventory.md

# Check spec description coverage
uv run doc-coverage \
  --spec ../../parser/docs/openapi/v1.json \
  --verbose

# Fail if coverage is below 80%
uv run doc-coverage \
  --spec ../../parser/docs/openapi/v1.json \
  --min-coverage 80
```

## Commands

### `doc-sync`

Discovers MDX files with `openapi:` frontmatter, matches them to operations in the spec,
and calls Claude to update `<ParamField>` and `<ResponseField>` blocks while preserving
all existing prose.

| Flag | Default | Description |
|---|---|---|
| `--spec <path>` | required | Path to `openapi.json` |
| `--docs-root <path>` | required | Root of the docs repo (contains `api-reference/`) |
| `--file <rel-path>` | all files | Process only one MDX file (relative to docs-root) |
| `--dry-run` | off | Print diffs, write nothing |
| `--model <id>` | auto | Claude model ID (defaults to Sonnet 4.6 or Opus 4.6 on Bedrock) |
| `--bedrock` | off | Route via Amazon Bedrock using current AWS credentials |
| `--no-diff` | off | Suppress per-file diff output |

### `doc-stub`

Generates a complete new MDX file from scratch for an operation not yet documented.
Uses Claude to produce frontmatter, prose overview, `<ParamField>` / `<ResponseField>` blocks,
and cURL / Python / JavaScript code examples.

| Flag | Default | Description |
|---|---|---|
| `--spec <path>` | required | Path to `openapi.json` |
| `--docs-root <path>` | required | Root of the docs repo |
| `--operation <"METHOD /path">` | required | Operation to document, e.g. `"POST /v2/parse/upload"` |
| `--output <rel-path>` | stdout | Output path relative to docs-root |
| `--dry-run` | off | Print to stdout, write nothing |
| `--model <id>` | auto | Claude model ID |
| `--bedrock` | off | Route via Amazon Bedrock |

### `doc-inventory`

Reads the OpenAPI spec and produces a full Markdown reference: all endpoints,
parameters, response fields, schemas, and enums.

| Flag | Default | Description |
|---|---|---|
| `--spec <path>` | required | Path to `openapi.json` |
| `--output <path>` | stdout | Output Markdown file |
| `--endpoint <prefix>` | all | Filter to a path prefix, e.g. `/parse` |

### `doc-coverage`

Reports what percentage of schema properties, operations, and parameters have descriptions.

| Flag | Default | Description |
|---|---|---|
| `--spec <path>` | required | Path to `openapi.json` |
| `--min-coverage <n>` | 0 | Exit code 1 if overall coverage is below N% |
| `--verbose` | off | Print all missing field names |

## Claude backends

All commands that call Claude (`doc-sync`, `doc-stub`) support two backends:

| Backend | Flag | Default model | Requirement |
|---|---|---|---|
| Anthropic API | _(none)_ | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` env var |
| Amazon Bedrock | `--bedrock` | `us.anthropic.claude-opus-4-5-20251101-v1:0` | AWS credentials + Bedrock access |

Pass `--model <id>` to override the default for either backend.

```bash
# Use Bedrock with Sonnet 4.6 explicitly
uv run doc-sync --spec ... --docs-root .. --bedrock --model us.anthropic.claude-sonnet-4-5-20251101-v1:0
```

## How sync works

```
openapi.json  ──►  doc-sync  ──►  Claude  ──►  updated MDX files
                      │
                 (preserves all existing prose,
                  code examples, AccordionGroups)
```

For each MDX file with an `openapi:` frontmatter key, the tool:

1. Matches it to the corresponding operation in the spec
2. Sends the existing MDX + spec operation JSON to Claude
3. Claude updates `<ParamField>` / `<ResponseField>` blocks and code examples inside `<RequestExample>` / `<ResponseExample>`
4. The result is written back (or diffed in `--dry-run` mode)

## How stub generation works

```
openapi.json  ──►  doc-stub  ──►  Claude  ──►  new MDX file
                      │
                 (generates from scratch:
                  frontmatter, overview, ParamFields,
                  ResponseFields, code examples)
```

## Running tests

```bash
cd docs_v2/tooling
uv sync --group dev
uv run pytest tests/ -v
```

38 tests covering `spec/loader`, `mdx/loader`, `mdx/writer`, and an end-to-end
pipeline integration test (Claude call mocked — no API key required for tests).

## Package structure

```
tooling/
├── pyproject.toml          # Package definition + CLI entry points
├── uv.lock
├── README.md
├── docs/
│   └── IMPLEMENTATION_PLAN.md  # Full implementation history and checklist
├── tests/
│   ├── fixtures/
│   │   ├── sample.mdx          # Fixture MDX file for tests
│   │   └── sample_spec.json    # Fixture OpenAPI spec for tests
│   ├── test_spec_loader.py
│   ├── test_mdx_loader.py
│   ├── test_mdx_writer.py
│   └── test_integration_sync.py
└── doc_sync/               # Python package
    ├── cli/
    │   ├── sync.py         # doc-sync entry point
    │   ├── inventory.py    # doc-inventory entry point
    │   ├── coverage.py     # doc-coverage entry point
    │   └── stub.py         # doc-stub entry point
    ├── spec/
    │   └── loader.py       # Parse openapi.json, index by operation key
    ├── mdx/
    │   ├── loader.py       # Discover MDX files with openapi: frontmatter
    │   └── writer.py       # Write results, print rich diff
    ├── enrichment/
    │   ├── enrich.py       # Claude API calls (Anthropic + Bedrock), per-file enrichment
    │   └── stubs.py        # Mintlify scraper for baseline stubs
    └── prompts/
        ├── enrich_endpoint.md  # System prompt for doc-sync
        └── generate_stub.md    # System prompt for doc-stub
```
