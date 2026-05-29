"""Pydantic models for memsearch-mcp."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel


def infer_tier(source: str) -> str:
    """Infer memory tier from the source file path."""
    p = source.replace(str(Path.home()), "~")
    if ".memsearch/memory/" in source or ".memsearch/memory/" in p:
        return "session"
    if "/.claude/memory/docs/" in source or "~/.claude/memory/docs/" in p:
        return "docs"
    if "/.claude/memory/" in source or "~/.claude/memory/" in p:
        return "working"
    if "/opt/agents/memory/" in source:
        return "session"
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
