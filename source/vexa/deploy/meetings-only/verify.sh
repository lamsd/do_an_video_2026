#!/usr/bin/env sh
set -eu

gateway_port=$(awk -F= '$1 == "API_GATEWAY_HOST_PORT" { print $2; exit }' project.env)
gateway_port=${gateway_port:-18056}

curl --fail --silent --show-error "http://127.0.0.1:${gateway_port}/health" >/dev/null

# The agent capability is absent at the public edge. MCP is intentionally not
# probed anonymously because the gateway authenticates it before rejecting an
# empty upstream; the Compose file itself contains no mcp service.
status=$(curl --silent --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:${gateway_port}/agent/health")
if [ "$status" != "404" ]; then
  echo "Expected /agent/health to be absent (404), got ${status}" >&2
  exit 1
fi
if docker compose --env-file project.env -f compose.yaml ps --services | grep -qx mcp; then
  echo "mcp service must not run in meetings-only mode" >&2
  exit 1
fi

echo "Verified: meetings-only gateway is healthy; agent route and MCP service are absent."
