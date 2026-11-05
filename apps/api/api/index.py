"""Vercel Python runtime entrypoint for the FastAPI app.

Vercel imports `api.index.app` from the project root (Root Directory = apps/api).
The repo-relative import path stays the same as local development.
"""
from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


# Vercel looks for an ASGI callable named `app` in api/index.py
