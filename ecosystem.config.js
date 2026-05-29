module.exports = {
  apps: [{
    name: "memsearch-mcp",
    script: "/opt/venvs/memsearch/bin/python3",
    args: ["-m", "memsearch_mcp.server"],
    cwd: "/home/ted/repos/personal/memsearch-mcp",
    interpreter: "none",

    restart_delay: 5000,
    max_restarts: 10,
    min_uptime: "10s",

    out_file: "/home/ted/logs/memsearch-mcp.log",
    error_file: "/home/ted/logs/memsearch-mcp.log",
    merge_logs: true,
    time: true,

    env: {
      LOG_LEVEL: "INFO",
      MEMSEARCH_MCP_PORT: "8493",
    },
  }]
};
