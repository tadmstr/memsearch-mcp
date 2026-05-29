"""Pydantic models for memsearch-mcp."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Tier classification roots
# ---------------------------------------------------------------------------

_HOME = Path.home()
_DOCS_ROOT = _HOME / ".claude/memory/docs"
_WORKING_ROOT = _HOME / ".claude/memory"
_OPT_SESSION_ROOT = Path("/opt/agents/memory")


def infer_tier(source: str) -> str:
    """Infer memory tier from the source file path.

    Uses Path.is_relative_to() for strict prefix matching — substring
    matching would allow crafted paths like /tmp/evil/.claude/memory/x.md
    to misclassify as a trusted tier.
    # SECURITY[resolved]: Replaced substring 'in' operator with Path.is_relative_to()
    # to prevent tier misclassification via crafted paths. Audit: 2026-05-28/memsearch-mcp-2026-05.
    """
    p = Path(source)
    # Session: plugin-managed session dirs (.memsearch component in path)
    if any(part == ".memsearch" for part in p.parts):
        return "session"
    if p.is_relative_to(_OPT_SESSION_ROOT):
        return "session"
    # Docs: check before working (docs is a subdirectory of working)
    if p.is_relative_to(_DOCS_ROOT):
        return "docs"
    # Working: main claude memory
    if p.is_relative_to(_WORKING_ROOT):
        return "working"
    return "unknown"


class MemoryResult(BaseModel):
    path: str
    score: float
    snippet: str
    heading: Optional[str]
    tier: str
    start_line: int
    end_line: int

    @classmethod
    def from_hit(cls, hit: dict) -> "MemoryResult":
        source = hit.get("source", "")
        return cls(
            path=source,
            score=round(hit.get("score", 0.0), 4),
            snippet=hit.get("content", ""),
            heading=hit.get("heading") or None,
            tier=infer_tier(source),
            start_line=hit.get("start_line", 0),
            end_line=hit.get("end_line", 0),
        )
