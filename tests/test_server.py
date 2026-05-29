"""Smoke tests for memsearch-mcp server."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path

from memsearch_mcp.models import MemoryResult, infer_tier


# ---------------------------------------------------------------------------
# Unit tests — models
# ---------------------------------------------------------------------------


def test_infer_tier_session():
    assert infer_tier("/home/ted/.memsearch/memory/2026-05-28.md") == "session"


def test_infer_tier_working():
    assert infer_tier("/home/ted/.claude/memory/shared/context.md") == "working"
    assert infer_tier("/home/ted/.claude/memory/agents/developer/notes.md") == "working"


def test_infer_tier_docs():
    assert infer_tier("/home/ted/.claude/memory/docs/architecture.md") == "docs"


def test_infer_tier_agents_memory():
    assert infer_tier("/opt/agents/memory/session.md") == "session"


def test_infer_tier_unknown():
    assert infer_tier("/tmp/something.md") == "unknown"


# MEM-02 regression: crafted paths with .claude/memory substring must not misclassify
def test_infer_tier_crafted_path_not_misclassified():
    """MEM-02: substring match would classify these as working/session; is_relative_to must not."""
    assert infer_tier("/tmp/evil/.claude/memory/attack.md") == "unknown"
    assert infer_tier("/tmp/evil/.memsearch/memory/attack.md") == "session"  # .memsearch in parts → session is ok
    assert infer_tier("/var/evil/.claude/memory/docs/attack.md") == "unknown"


def test_memory_result_from_hit():
    hit = {
        "source": "/home/ted/.claude/memory/shared/notes.md",
        "score": 0.87654,
        "content": "Some memory content here.",
        "heading": "## Notes",
        "start_line": 10,
        "end_line": 25,
    }
    result = MemoryResult.from_hit(hit)
    assert result.path == hit["source"]
    assert result.score == 0.8765
    assert result.snippet == hit["content"]
    assert result.heading == "## Notes"
    assert result.tier == "working"
    assert result.start_line == 10
    assert result.end_line == 25


def test_memory_result_from_hit_null_heading():
    hit = {
        "source": "/home/ted/.claude/memory/shared/notes.md",
        "score": 0.5,
        "content": "Content",
        "heading": "",
        "start_line": 1,
        "end_line": 5,
    }
    result = MemoryResult.from_hit(hit)
    assert result.heading is None


# ---------------------------------------------------------------------------
# Unit tests — index_memory path whitelist (MEM-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_memory_rejects_etc():
    """MEM-01: /etc/ is outside allowed roots and must be rejected."""
    from memsearch_mcp.server import index_memory
    result = await index_memory("/etc/passwd")
    assert "error" in result
    assert "allowed index roots" in result["error"]


@pytest.mark.asyncio
async def test_index_memory_rejects_secrets():
    """MEM-01: ~/.secrets/ is outside allowed roots and must be rejected."""
    from memsearch_mcp.server import index_memory
    result = await index_memory(str(Path.home() / ".secrets"))
    assert "error" in result
    assert "allowed index roots" in result["error"]


@pytest.mark.asyncio
async def test_index_memory_rejects_crafted_traversal():
    """MEM-01: path traversal attempt must be rejected after resolve()."""
    from memsearch_mcp.server import index_memory
    result = await index_memory(str(Path.home() / ".claude/memory/../../.secrets"))
    assert "error" in result


@pytest.mark.asyncio
async def test_index_memory_nonexistent_path():
    """index_memory returns error for a path that doesn't exist."""
    from memsearch_mcp.server import index_memory
    result = await index_memory("/nonexistent/path/that/does/not/exist")
    assert "error" in result


# ---------------------------------------------------------------------------
# Integration smoke test — search_memory tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_memory_returns_list():
    """search_memory returns a list of dicts (mocked memsearch)."""
    mock_hits = [
        {
            "source": "/home/ted/.claude/memory/shared/test.md",
            "score": 0.9,
            "content": "Test content",
            "heading": "# Test",
            "start_line": 1,
            "end_line": 10,
        }
    ]
    with patch("memsearch_mcp.server._ms") as mock_ms:
        mock_ms.search = AsyncMock(return_value=mock_hits)
        from memsearch_mcp.server import search_memory
        results = await search_memory("test query", limit=5)
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["tier"] == "working"
    assert results[0]["score"] == 0.9


@pytest.mark.asyncio
async def test_search_memory_error_returns_error_dict():
    """search_memory returns an error dict on exception (no raise)."""
    with patch("memsearch_mcp.server._ms") as mock_ms:
        mock_ms.search = AsyncMock(side_effect=RuntimeError("Milvus down"))
        from memsearch_mcp.server import search_memory
        results = await search_memory("query")
    assert len(results) == 1
    assert "error" in results[0]
