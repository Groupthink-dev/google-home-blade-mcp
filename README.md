# google-home-blade-mcp

**Security-first, token-efficient MCP server for Google Home and Nest devices via the Smart Device Management API.**

Control thermostats, stream cameras, monitor doorbells, and pull device events — all through a hardened MCP interface designed for LLM-driven home automation.

## Why This Exists

| | ghome-mcp-server | Google's Cloud MCPs | **google-home-blade-mcp** |
|---|---|---|---|
| **Device coverage** | Smart plugs only | No Google Home MCP | Full SDM: thermostats, cameras, doorbells, displays |
| **Security model** | None | IAM-only | Write gates + confirm gates + credential scrubbing |
| **Token efficiency** | Verbose JSON | N/A | Pipe-delimited, null-omission, ~25 tokens/device |
| **Thermostat control** | No | No | Mode, setpoint, eco, fan — all with safety gates |
| **Camera streams** | No | No | WebRTC/RTSP with 5-min session management |
| **Event streaming** | No | No | Pub/Sub integration for motion, person, doorbell events |
| **Batch operations** | No | N/A | `ghome_status` dashboard, `ghome_thermostats` overview |
| **Marketplace ready** | No | No | `sidereal-plugin.yaml`, `home-v1` contract, SKILL.md |

### Design Principles

1. **Security-first** — Every device command requires explicit write enablement. Destructive operations require double confirmation. OAuth tokens never appear in output. Access tokens live in memory only.
2. **Token efficiency** — Compact pipe-delimited output. Null fields omitted. Dashboard views compress entire device fleets into minimal tokens. One `ghome_status` call replaces N individual queries.
3. **Event-driven** — Pub/Sub integration enables webhook-style triggers for motion detection, doorbell presses, and state changes. No polling required.

## Quick Start

```bash
# Install
git clone https://github.com/groupthink-dev/google-home-blade-mcp.git
cd google-home-blade-mcp
make install-dev

# Set up OAuth (one-time interactive flow)
export GOOGLE_HOME_CLIENT_ID="your-client-id"
export GOOGLE_HOME_CLIENT_SECRET="your-client-secret"
export GOOGLE_HOME_PROJECT_ID="your-sdm-project-id"
make auth
# → Opens browser → Google consent → prints refresh token

# Configure
export GOOGLE_HOME_REFRESH_TOKEN="the-refresh-token-from-above"
export GOOGLE_HOME_WRITE_ENABLED=true   # optional: enable device commands

# Run
make run
```

### Prerequisites

1. **Google Cloud project** with [Smart Device Management API](https://console.cloud.google.com/apis/library/smartdevicemanagement.googleapis.com) enabled
2. **Device Access Console** registration at [console.nest.google.com/device-access](https://console.nest.google.com/device-access) ($5 USD one-time fee)
3. **OAuth 2.0 credentials** (Web application type) in GCP Console
4. At least one Nest device linked to your Google account

## Tools (15)

### Read (8 tools)

| Tool | Purpose | Tokens |
|------|---------|--------|
| `ghome_info` | Health check: API status, device counts, write gate | ~30 |
| `ghome_structures` | List homes | ~15/structure |
| `ghome_rooms` | List rooms in a structure | ~10/room |
| `ghome_devices` | List all devices (filterable by type) | ~25/device |
| `ghome_device` | Full device detail with all traits | ~80-120 |
| `ghome_status` | Compact dashboard — all devices, one line each | ~25/device |
| `ghome_thermostats` | All thermostats at a glance | ~30/thermostat |
| `ghome_events` | Pull recent events from Pub/Sub | ~20/event |

### Write (7 tools, gated)

| Tool | Purpose | Gate |
|------|---------|------|
| `ghome_thermostat_mode` | Set mode: HEAT, COOL, HEATCOOL, OFF | write |
| `ghome_thermostat_setpoint` | Set target temperature (heat, cool, or range) | write |
| `ghome_thermostat_eco` | Toggle eco mode | write |
| `ghome_fan_set` | Fan timer control | write |
| `ghome_camera_stream` | Generate live stream URL (WebRTC/RTSP) | write |
| `ghome_camera_image` | Get snapshot from camera event | write |
| `ghome_command` | Execute any SDM command (escape hatch) | write + confirm |

## Output Format

Token-efficient pipe-delimited output with null-field omission:

```
# ghome_status
## Devices: 4 total, 4 online
Living Room | Thermostat | room=Living Room | online | 21.5°C | mode=HEAT | hvac=HEATING | id=abc123
Master Bedroom | Thermostat | room=Bedroom | online | 19.8°C | mode=ECO | hvac=OFF | id=def456
Front Door | Doorbell | room=Entry | online | events=motion,person,chime | id=ghi789
Garden | Camera | room=Outdoor | online | events=motion,person | id=jkl012

# ghome_thermostats
Living Room | Living Room | ambient=21.5°C | humidity=45% | mode=HEAT | heat→22.0°C | hvac=HEATING | online | id=abc123
Master Bedroom | Bedroom | ambient=19.8°C | humidity=52% | mode=HEAT | eco=MANUAL_ECO | hvac=OFF | online | id=def456
```

## Security Model

### Three-layer protection

1. **Write gate** — All device commands blocked unless `GOOGLE_HOME_WRITE_ENABLED=true`. Read operations always allowed.
2. **Confirm gate** — `ghome_command` (raw SDM command execution) requires `confirm=true` as an additional parameter.
3. **Credential scrubbing** — OAuth access tokens (`ya29.*`), refresh tokens (`1//*`), Bearer headers, and client secrets are stripped from all error messages before output.

### Token lifecycle

- **Refresh token** stored in env var (never in code, never on disk beyond env)
- **Access tokens** refreshed automatically, kept in memory only, 60-second pre-expiry buffer
- **401 responses** trigger automatic token invalidation and re-auth on next request
- **Bearer auth** available for HTTP transport (optional `GOOGLE_HOME_MCP_API_TOKEN`)

## Claude Code Integration

Add to your `settings.json` or `claude.nix`:

```json
{
  "mcpServers": {
    "google-home": {
      "command": "uv",
      "args": ["--directory", "/path/to/google-home-blade-mcp", "run", "google-home-blade-mcp"],
      "env": {
        "GOOGLE_HOME_CLIENT_ID": "your-client-id",
        "GOOGLE_HOME_CLIENT_SECRET": "your-secret",
        "GOOGLE_HOME_REFRESH_TOKEN": "your-refresh-token",
        "GOOGLE_HOME_PROJECT_ID": "your-project-id",
        "GOOGLE_HOME_WRITE_ENABLED": "false"
      }
    }
  }
}
```

## Pub/Sub Event Streaming

For event-driven automation (motion alerts, doorbell presses, temperature changes):

1. Create a Pub/Sub topic in GCP Console linked to your Device Access project
2. Create a subscription for the topic
3. Set `GOOGLE_HOME_PUBSUB_SUBSCRIPTION=projects/{project}/subscriptions/{name}`
4. Use `ghome_events` to pull and acknowledge events

Events include device trait updates, camera motion/person detection, and doorbell chime events — enabling webhook-style triggers without polling.

## Supported Devices

| Device | Read | Control | Stream | Events |
|--------|------|---------|--------|--------|
| Nest Thermostat | ambient, humidity, mode, setpoint, HVAC, eco | mode, setpoint, eco, fan | — | trait updates |
| Nest Camera | status, capabilities | — | WebRTC, RTSP | motion, person, sound |
| Nest Doorbell | status, capabilities | — | WebRTC | motion, person, chime |
| Nest Hub Max | status | — | — | — |

## Development

```bash
make install-dev    # Install with dev + test dependencies
make test           # Run unit tests
make test-cov       # Run with coverage report
make lint           # Ruff linter
make format         # Ruff formatter
make type-check     # MyPy strict mode
make check          # All quality checks
```

### Architecture

```
src/google_home_blade_mcp/
├── server.py       # 15 FastMCP tools (read + write-gated)
├── client.py       # SDM API client (httpx, error classification)
├── auth.py         # OAuth2 token manager (memory-only access tokens)
├── traits.py       # Trait parsing + command builders
├── formatters.py   # Token-efficient output (pipe-delimited, null-omission)
├── models.py       # Config, device types, exceptions, credential scrubbing
└── auth_setup.py   # Interactive OAuth2 setup (make auth)
```

### Rate Limits

| Operation | Limit |
|-----------|-------|
| Device commands | 5/min per device |
| API aggregate | 6,000 req/60s per project |
| Camera streams | 5-min sessions (extendable) |
| Sandbox users | 25 max across 5 structures |

## Sidereal Marketplace

This blade ships with full marketplace scaffolding:

- `sidereal-plugin.yaml` — Plugin manifest with `home-v1` contract, OAuth2 setup block, conformance declaration
- `SKILL.md` — Token efficiency rules, workflow examples, tool reference for Claude
- Security model aligned with Sidereal trust tiers (write gates, confirm gates, credential scrubbing)

## License

MIT
