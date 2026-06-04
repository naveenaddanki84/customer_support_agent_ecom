"""Editable knowledge documents (refund policy + FAQs).

The refund policy and the FAQ knowledge base are plain markdown files under
``backend/knowledge/`` so the support team can edit them as documents. They are
read fresh on every call (the files are tiny), so an edit takes effect
immediately — no database, no cache, no redeploy.

Override the directory with the ``KNOWLEDGE_DIR`` environment variable.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Default: <backend>/knowledge  (this file is <backend>/app/knowledge.py)
_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "knowledge"

REFUND_POLICY_FILE = "refund_policy.md"
FAQS_FILE = "faqs.md"


def _dir() -> Path:
    override = os.getenv("KNOWLEDGE_DIR")
    return Path(override) if override else _DEFAULT_DIR


def _read(filename: str) -> str:
    """Read a knowledge document, returning '' (and logging) if it's missing."""
    path = _dir() / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("Knowledge document not found: %s", path)
        return ""
    except OSError as e:  # noqa: BLE001 - surface read errors but never crash a turn
        logger.error("Failed to read knowledge document %s: %s", path, e)
        return ""


def read_refund_policy() -> str:
    """The current refund policy text the agent reasons against."""
    return _read(REFUND_POLICY_FILE)


def read_faqs() -> str:
    """The current FAQ knowledge base used to ground FAQ answers."""
    return _read(FAQS_FILE)
