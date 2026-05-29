# memsearch-mcp

FastMCP server wrapping the [memsearch](https://github.com/TadMSTR/memsearch) semantic memory
search library. Exposes hybrid vector+BM25+reranker search and index-refresh tools to forge agents
over streamable-http MCP transport.

## Overview

Agent memory on forge lives in markdown files across a three-tier hierarchy: session (per-project
plugin dirs), working (`~/.claude/memory/`), and docs. memsearch-mcp lets agents query all of
it with a single tool call — without reading files directly or knowing where they live.

**Who uses it:** All 5 forge resident agents (research, developer, writer, security, sysadmin)
have memsearch-mcp in their scoped-mcp manifests. `index_memory` is denylisted for security,
research, and writer.

## Tools

| Tool | Description | Key Parameters | Returns |
|------|-------------|----------------|---------|
| `search_memory` | Hybrid vector+BM25+reranker search over Milvus-indexed agent memory | `query: str`, `limit: int = 10` | `list[dict]` — results sorted by score |
| `index_memory` | Trigger a memsearch index refresh for a path or default to `~/.claude/memory/` | `path: str \| None` | `{"indexed": N, "path": str}` |

### search_memory result fields

| Field | Type | Description |
|-------|------|-------------|
| `path` | `str` | Absolute path to the source file |
| `score` | `float` | Relevance score (higher = more relevant) |
| `snippet` | `str` | Matching text chunk |
| `heading` | `str \| null` | Nearest markdown heading above the chunk |
| `tier` | `str` | `session`, `working`, `docs`, or `unknown` |
| `start_line` | `int` | First line of the chunk in the source file |
| `end_line` | `int` | Last line of the chunk |

### index_memory path restrictions

`index_memory` accepts only paths under:

- `~/.claude/memory/`
- `~/.claude/projects/`
- `/opt/agents/memory/`

Requests outside these roots are rejected with an error (not forwarded to the library).

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `MEMSEARCH_MCP_PORT` | No | `8493` | Port for the streamable-http server |
| `LOG_LEVEL` | No | `INFO` | structlog log level |
| `MEMSEARCH_CONFIG` | No | (library default) | Path to memsearch config file |

## Installation

Requires Python 3.11+ and an existing memsearch venv with the `memsearch` library installed.

```bash
# From the memsearch venv (forge standard)
/opt/venvs/memsearch/bin/pip install -e /home/ted/repos/personal/memsearch-mcp

# Or from git
/opt/venvs/memsearch/bin/pip install "git+https://github.com/TadMSTR/memsearch-mcp.git"
```

### Dependencies

- `fastmcp>=2.0`
- `pydantic>=2.0`
- `structlog>=24.0`
- `memsearch` (must be installed in the same venv — not in PyPI, install from source)

## Deployment

### PM2

`ecosystem.config.js` in the repo root:

```js
module.exports = {
  apps: [{
    name: "memsearch-mcp",
    script: "/opt/venvs/memsearch/bin/python3",
    args: ["-m", "memsearch_mcp.server"],
    cwd: "/home/ted/repos/personal/memsearch-mcp",
    interpreter: "none",
    env: {
      LOG_LEVEL: "INFO",
      MEMSEARCH_MCP_PORT: "8493",
    },
  }]
};
```

```bash
pm2 start ecosystem.config.js
pm2 save
```

### scoped-mcp wiring

Add to each agent manifest at `~/.claude/manifests/<agent>-agent.yml`:

```yaml
modules:
  - name: memsearch-mcp
    type: mcp_proxy
    url: "http://127.0.0.1:8493/mcp"
    tool_denylist:
      - "index_memory"   # omit for developer and sysadmin
```

No restart of scoped-mcp is needed — manifests are loaded fresh on each agent session start.

## Observability

Logs are written to `~/logs/memsearch-mcp.log` (stdout + stderr merged, timestamped by PM2).

Log lines are JSON (structlog):

```json
{"event": "search_memory", "query": "grafana dashboard", "limit": 10, "level": "info"}
{"event": "search_memory_done", "query": "grafana dashboard", "results": 7, "level": "info"}
{"event": "index_memory_dir_done", "path": "/home/ted/.claude/memory", "chunks": 412, "level": "info"}
```

Tool arguments are **not** included in logs — only query strings and result counts.

To check server health:

```bash
pm2 status memsearch-mcp
curl -s http://127.0.0.1:8493/mcp | head -5   # should return SSE headers or MCP handshake
```
