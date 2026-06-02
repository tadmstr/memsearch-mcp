"""memsearch-mcp — FastMCP server wrapping the memsearch Python API.

Tool surface:
  search_memory(query, limit=10) — hybrid vector+BM25+reranker search
  index_memory(path=None)        — trigger index refresh for a path
"""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any, Optional

import structlog
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from memsearch import MemSearch
from memsearch.config import resolve_config

from .models import MemoryResult

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[structlog.processors.JSONRenderer()],
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger(__name__)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ---------------------------------------------------------------------------
# memsearch instance (search — paths unused for Milvus vector search)
# ---------------------------------------------------------------------------

_cfg = resolve_config()

_DEFAULT_INDEX_PATHS: list[str] = [
    str(Path.home() / ".claude/memory"),
    "/opt/agents/memory",
]

# The paths list is only used for indexing; for search we need only config.
_ms = MemSearch(
    paths=_DEFAULT_INDEX_PATHS,
    embedding_provider=_cfg.embedding.provider,
    embedding_model=_cfg.embedding.model or None,
    embedding_batch_size=_cfg.embedding.batch_size,
    embedding_base_url=_cfg.embedding.base_url or None,
    embedding_api_key=_cfg.embedding.api_key or None,
    milvus_uri=_cfg.milvus.uri,
    milvus_token=_cfg.milvus.token or None,
    collection=_cfg.milvus.collection,
    max_chunk_size=_cfg.chunking.max_chunk_size,
    overlap_lines=_cfg.chunking.overlap_lines,
    reranker_model=_cfg.reranker.model,
)

log.info(
    "memsearch_mcp_startup",
    milvus_uri=_cfg.milvus.uri,
    collection=_cfg.milvus.collection,
    embedding_provider=_cfg.embedding.provider,
    embedding_model=_cfg.embedding.model,
    reranker=bool(_cfg.reranker.model),
)

# ---------------------------------------------------------------------------
# index_memory path whitelist
# SECURITY[resolved]: Added _ALLOWED_INDEX_ROOTS whitelist to prevent agents
# from triggering indexing of arbitrary paths. Uses Path.is_relative_to() for
# strict prefix matching. Audit: 2026-05-28/memsearch-mcp-2026-05.
# ---------------------------------------------------------------------------

_ALLOWED_INDEX_ROOTS: list[Path] = [
    Path.home() / ".claude/memory",
    Path.home() / ".claude/projects",
    Path("/opt/agents/memory"),
]


def _is_allowed_path(p: Path) -> bool:
    return any(p == root or p.is_relative_to(root) for root in _ALLOWED_INDEX_ROOTS)


# ---------------------------------------------------------------------------
# Bearer token auth middleware (activated only when MEMSEARCH_API_TOKEN is set)
# ---------------------------------------------------------------------------


class _BearerAuthMiddleware:
    """ASGI middleware that enforces static bearer token authentication.

    Only active when MEMSEARCH_API_TOKEN is set in the environment.
    Requests missing a valid Authorization header receive a 401 response.
    Health/liveness paths are not exposed (all traffic goes through MCP).
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            request = Request(scope, receive)
            auth_header = request.headers.get("authorization", "")
            provided = auth_header.removeprefix("Bearer ") if auth_header.lower().startswith("bearer ") else ""
            if not hmac.compare_digest(provided, self._token):
                response = Response(
                    content='{"error":"Unauthorized"}',
                    status_code=401,
                    media_type="application/json",
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="memsearch",
    instructions=(
        "memsearch MCP server. Provides hybrid vector+BM25+reranker semantic "
        "search over forge agent memory indexed in Milvus. Use search_memory "
        "to query past decisions, session notes, working memory, and docs. "
        "Use index_memory to trigger a re-index after writing new memory files."
    ),
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_memory(query: str, limit: int = 10) -> list[dict]:
    """Search indexed agent memory using hybrid vector+BM25+reranker.

    Returns results sorted by relevance with path, score, snippet, tier, and heading.
    Tier labels: session (.memsearch/memory/), working (~/.claude/memory/), docs (~/.claude/memory/docs/).
    """
    log.info("search_memory", query=query, limit=limit)
    try:
        hits = await _ms.search(query, top_k=limit)
        results = [MemoryResult.from_hit(h).model_dump() for h in hits]
        log.info("search_memory_done", query=query, results=len(results))
        return results
    except Exception as exc:
        log.error("search_memory_error", query=query, error=str(exc))
        return [{"error": str(exc)}]


@mcp.tool()
async def index_memory(path: Optional[str] = None) -> dict:
    """Trigger a memsearch index refresh.

    If path is given, indexes that directory or file within allowed roots.
    Defaults to ~/.claude/memory/. Returns the number of chunks indexed.
    Allowed roots: ~/.claude/memory/, ~/.claude/projects/, /opt/agents/memory/.
    """
    target = path or str(Path.home() / ".claude/memory")
    log.info("index_memory", path=target)
    try:
        p = Path(target).expanduser().resolve()

        if not _is_allowed_path(p):
            log.warning("index_memory_path_rejected", path=str(p))
            return {"error": f"Path not in allowed index roots: {target}"}

        if not p.exists():
            return {"error": f"Path does not exist: {target}"}

        if p.is_file():
            n = await _ms.index_file(p)
            log.info("index_memory_file_done", path=str(p), chunks=n)
            return {"indexed": n, "path": str(p)}

        # Directory: create a fresh MemSearch instance scoped to this path
        indexer = MemSearch(
            paths=[str(p)],
            embedding_provider=_cfg.embedding.provider,
            embedding_model=_cfg.embedding.model or None,
            embedding_batch_size=_cfg.embedding.batch_size,
            embedding_base_url=_cfg.embedding.base_url or None,
            embedding_api_key=_cfg.embedding.api_key or None,
            milvus_uri=_cfg.milvus.uri,
            milvus_token=_cfg.milvus.token or None,
            collection=_cfg.milvus.collection,
            max_chunk_size=_cfg.chunking.max_chunk_size,
            overlap_lines=_cfg.chunking.overlap_lines,
            reranker_model=_cfg.reranker.model,
        )
        try:
            n = await indexer.index()
        finally:
            indexer.close()

        log.info("index_memory_dir_done", path=str(p), chunks=n)
        return {"indexed": n, "path": str(p)}

    except Exception as exc:
        log.error("index_memory_error", path=target, error=str(exc))
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    port = int(os.getenv("MEMSEARCH_MCP_PORT", "8493"))
    api_token = os.getenv("MEMSEARCH_API_TOKEN")
    middleware: list[Any] = []
    if api_token:
        log.info("memsearch_mcp_bearer_auth_enabled")
        middleware = [Middleware(_BearerAuthMiddleware, token=api_token)]
    else:
        log.info("memsearch_mcp_bearer_auth_disabled", reason="MEMSEARCH_API_TOKEN not set")
    try:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=port, middleware=middleware or None)
    except (KeyboardInterrupt, SystemExit):
        log.info("memsearch_mcp_shutdown")


if __name__ == "__main__":
    main()
