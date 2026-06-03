# memsearch-mcp

FastMCP server wrapping the `memsearch` Python library for hybrid vector+BM25+reranker semantic search over agent memory files.

## What it does

Provides two tools for searching and re-indexing the forge agent memory store backed by Milvus.

## Tools

- `search_memory(query, limit=10)` — Hybrid search: vector (Milvus) + BM25 + reranker. Returns ranked `MemoryResult` objects with path, snippet, score, tier, and tags.
- `index_memory(path=None)` — Trigger index refresh for a path. Path must be within `_ALLOWED_INDEX_ROOTS`.

## Structure

```
memsearch_mcp/
  __init__.py
  server.py         FastMCP server — 2 tools, MemSearch init, HMAC auth middleware, path whitelist
  models.py         MemoryResult pydantic model
tests/              pytest tests
ecosystem.config.js PM2 config
pyproject.toml
```

## Dependencies

| Package    | Role                                       |
|------------|--------------------------------------------|
| fastmcp    | MCP server framework                       |
| memsearch  | Hybrid search library (Milvus + BM25)      |
| pydantic   | Result model                               |
| structlog  | JSON structured logging                    |

## Configuration

| Env var            | Purpose                                                     |
|--------------------|-------------------------------------------------------------|
| `MEMSEARCH_SECRET` | Optional HMAC secret for `X-Memsearch-Token` auth header   |
| `LOG_LEVEL`        | Logging verbosity                                           |
| `MCP_PORT`         | Server port                                                 |

Milvus URI, collection name, embedding provider/model, and reranker model are sourced from the `memsearch` package's own config via `memsearch.config.resolve_config()` — not from this server's env vars.

## Key architecture decisions

- **`_ALLOWED_INDEX_ROOTS` whitelist** — `index_memory` only accepts paths under `~/.claude/memory` or `/opt/agents/memory`. Uses `Path.is_relative_to()` for strict prefix matching after symlink resolution. This prevents agents from triggering indexing of arbitrary filesystem paths. Do not widen this without a security review (resolved from a 2026-05-28 audit finding).
- **HMAC auth middleware** — optional Starlette middleware validates `X-Memsearch-Token` if `MEMSEARCH_SECRET` is set. Enable this when the server is exposed beyond localhost.

## Testing

```bash
pip install -e ".[dev]"
pytest
```

## Git workflow

Branch before editing — do not commit directly to `main`.
