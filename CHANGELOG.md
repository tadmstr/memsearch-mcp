# Changelog

## [0.1.0] — 2026-05-29

### Added
- `search_memory(query, limit=10)` — hybrid vector+BM25+reranker semantic search over Milvus-indexed agent memory
- `index_memory(path=None)` — trigger index refresh for allowed memory paths
- Tier labeling: session, working, docs, unknown based on source path
- PM2 deployment on port 8493 using `/opt/venvs/memsearch` Python interpreter
- Registered in all 5 forge agent scoped-mcp manifests

### Security
- `index_memory` restricted to `_ALLOWED_INDEX_ROOTS` whitelist (MEM-01)
- `infer_tier()` uses `Path.is_relative_to()` instead of substring matching (MEM-02)
- `index_memory` denylisted for security, research, and writer agents (MEM-03)
