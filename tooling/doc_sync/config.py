"""
Centralized configuration — all tunables come from environment variables / .env.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the tooling directory (docs_v2/tooling/.env)
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Amazon Bedrock ───────────────────────────────────────────────────────────
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
BEDROCK_MODEL = os.environ.get("BEDROCK_MODEL", "us.anthropic.claude-opus-4-5-20251101-v1:0")
BEDROCK_JUDGE_MODEL = os.environ.get("BEDROCK_JUDGE_MODEL", "us.anthropic.claude-opus-4-6-20250514-v1:0")

# ── Google Cloud Vertex AI ───────────────────────────────────────────────────
VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT", "")
VERTEX_REGION = os.environ.get("VERTEX_REGION", "us-east5")
VERTEX_MODEL = os.environ.get("VERTEX_MODEL", "claude-sonnet-4-6")
VERTEX_JUDGE_MODEL = os.environ.get("VERTEX_JUDGE_MODEL", "claude-opus-4-6")
