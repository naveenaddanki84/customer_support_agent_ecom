"""
Prompt registry — loads versioned prompt text files for each agent.

Prompts live as text files under ``app/prompts/<agent>/<version>.md``. The
active version per agent defaults to ``settings.prompt_version_default`` ("v1")
and can be overridden per agent via a ``PROMPT_VERSION_<AGENT>`` environment
variable, e.g. ``PROMPT_VERSION_REFUND=v2``.

To add a new version, drop a new ``<version>.md`` file in the agent's folder and
point the env var at it — no code changes required.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from app.config import settings

_PROMPTS_DIR = Path(__file__).resolve().parent


def _active_version(agent: str) -> str:
    """Resolve the active prompt version for an agent (env override > default)."""
    return os.getenv(f"PROMPT_VERSION_{agent.upper()}") or settings.prompt_version_default


@lru_cache(maxsize=None)
def _load(agent: str, version: str) -> str:
    """Read and cache a prompt file. Versions are immutable once created."""
    path = _PROMPTS_DIR / agent / f"{version}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {agent}/{version}.md")
    return path.read_text(encoding="utf-8").strip()


def get_prompt(agent: str, version: Optional[str] = None) -> str:
    """Return the prompt text for an agent at the active (or given) version."""
    return _load(agent, version or _active_version(agent))


def active_version(agent: str) -> str:
    """Return the active version label for an agent."""
    return _active_version(agent)


def available_versions(agent: str) -> List[str]:
    """List the available prompt versions for an agent (sorted)."""
    agent_dir = _PROMPTS_DIR / agent
    if not agent_dir.is_dir():
        return []
    return sorted(p.stem for p in agent_dir.glob("*.md"))


def list_agents() -> List[str]:
    """List agents that have a prompt folder."""
    return sorted(p.name for p in _PROMPTS_DIR.iterdir() if p.is_dir() and not p.name.startswith("__"))
