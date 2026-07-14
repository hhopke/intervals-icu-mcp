<!-- mcp-name: io.github.hhopke/intervals-icu-mcp -->

# Intervals.icu MCP Server

![intervals-icu-mcp demo](https://raw.githubusercontent.com/hhopke/intervals-icu-mcp/main/docs/demo.gif)

A Model Context Protocol (MCP) server for Intervals.icu integration. Access your training data, wellness metrics, and performance analysis through Claude, ChatGPT, and other LLMs.

> Originally based on [eddmann/intervals-icu-mcp](https://github.com/eddmann/intervals-icu-mcp) (MIT licensed). This project is an independent continuation with significant bug fixes and new features — see [CHANGELOG.md](https://github.com/hhopke/intervals-icu-mcp/blob/main/CHANGELOG.md) for details.

[![Tests](https://github.com/hhopke/intervals-icu-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/hhopke/intervals-icu-mcp/actions/workflows/test.yml)
[![intervals-icu-mcp MCP server](https://glama.ai/mcp/servers/hhopke/intervals-icu-mcp/badges/score.svg)](https://glama.ai/mcp/servers/hhopke/intervals-icu-mcp)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/hhopke/intervals-icu-mcp/blob/main/LICENSE)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue?logo=docker)](https://github.com/hhopke/intervals-icu-mcp/pkgs/container/intervals-icu-mcp)

## Overview

61 tools spanning activities, activity analysis, activity messages, athlete profile, wellness, events/calendar, performance curves, workout library, gear, sport settings, and custom items — plus 4 MCP Resources (athlete profile, workout syntax, event categories, custom item schemas) and 7 MCP Prompts (training analysis, recovery check, weekly planning, and more). See [Available Tools](#available-tools) for the per-category breakdown.

## Quick Start

<a href="https://cursor.com/en/install-mcp?name=intervals-icu&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJpbnRlcnZhbHMtaWN1LW1jcCJdLCJlbnYiOnsiSU5URVJWQUxTX0lDVV9BUElfS0VZIjoiIiwiSU5URVJWQUxTX0lDVV9BVEhMRVRFX0lEIjoiIn19"><picture><source media="(prefers-color-scheme: dark)" srcset="https://cursor.com/deeplink/mcp-install-dark.svg"><img alt="Install in Cursor" src="https://cursor.com/deeplink/mcp-install-light.svg"></picture></a>

Or for Claude Desktop, in 30 seconds:

1. Get your [API key and athlete ID](#intervalsicu-api-key-setup)
2. Add this to your Claude Desktop config:

```json
{
  "mcpServers": {
    "intervals-icu": {
      "command": "uvx",
      "args": ["intervals-icu-mcp"],
      "env": {
        "INTERVALS_ICU_API_KEY": "your-api-key-here",
        "INTERVALS_ICU_ATHLETE_ID": "i123456"
      }
    }
  }
}
```

3. Restart Claude and ask *"Show me my activities from the last 7 days."*

Prefer Claude Code, Cursor, or ChatGPT? See [Client Configuration](#client-configuration). Want to run from source or with Docker? See [Installation & Setup](#installation--setup).

## Prerequisites

Install [uv](https://github.com/astral-sh/uv) — it handles Python, dependencies, and execution in one tool. `brew install uv` on macOS/Linux, or `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` on Windows. From there, `uvx` fetches Python and the package automatically. Docker is also supported as an alternative.

## Intervals.icu API Key Setup

Before installation, obtain your Intervals.icu API key:

1. Go to https://intervals.icu/settings → **Developer** → **Create API Key**.
2. Copy the key, and note your **Athlete ID** from your profile URL (format: `i123456`).

## Installation & Setup

**Nothing to install separately if you use the recommended setup.** `uvx` (which ships with `uv`) automatically downloads and caches the `intervals-icu-mcp` package the first time your MCP client launches it — just paste the config snippet from [Client Configuration](#client-configuration) into your client and you're done.

<details>
<summary><b>Alternative: from source</b> — for development or local modifications</summary>

```bash
git clone https://github.com/hhopke/intervals-icu-mcp.git
cd intervals-icu-mcp
uv sync
uv run intervals-icu-mcp-auth  # interactive credential setup; or create .env manually:
#   INTERVALS_ICU_API_KEY=your_api_key_here
#   INTERVALS_ICU_ATHLETE_ID=i123456
```

Then point your MCP client at this checkout — see the **From source** snippet inside each client below.

</details>

<details>
<summary><b>Alternative: Docker</b></summary>

```bash
docker build -t intervals-icu-mcp .

# Interactive credential setup (creates intervals-icu-mcp.env in the current directory):
touch intervals-icu-mcp.env  # pre-create the file so Docker mounts it as a file, not a dir
docker run -it --rm \
  -v "$(pwd)/intervals-icu-mcp.env:/app/.env" \
  --entrypoint= intervals-icu-mcp:latest \
  python -m intervals_icu_mcp.scripts.setup_auth
```

Or create `intervals-icu-mcp.env` manually (same format as the `.env` above).

Then point your MCP client at the Docker image — see the **Docker** snippet inside each client below.

</details>

## Client Configuration

The server speaks MCP over stdio and works with any compliant client. Click a client to expand. If you followed Quick Start (uvx), use the first config block; if you used the source or Docker alternative above, use the matching variant inside the same collapsible.

<details>
<summary><b>Claude Desktop</b></summary>

Add to your configuration file:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "intervals-icu": {
      "command": "uvx",
      "args": ["intervals-icu-mcp"],
      "env": {
        "INTERVALS_ICU_API_KEY": "your-api-key-here",
        "INTERVALS_ICU_ATHLETE_ID": "i123456"
      }
    }
  }
}
```

**From source** (requires `git clone` + `uv sync` + `uv run intervals-icu-mcp-auth`):

```json
{
  "mcpServers": {
    "intervals-icu": {
      "command": "uv",
      "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/intervals-icu-mcp", "intervals-icu-mcp"]
    }
  }
}
```

**Docker**:

```json
{
  "mcpServers": {
    "intervals-icu": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "/ABSOLUTE/PATH/TO/intervals-icu-mcp.env:/app/.env", "intervals-icu-mcp:latest"]
    }
  }
}
```

</details>

<details>
<summary><b>Claude Code</b></summary>

Register the server as a user-scoped MCP server:

```bash
claude mcp add intervals-icu --scope user \
  --env INTERVALS_ICU_API_KEY=your-key \
  --env INTERVALS_ICU_ATHLETE_ID=i123456 \
  -- uvx intervals-icu-mcp
```

Then in any Claude Code session, run `/mcp` to confirm `intervals-icu` is connected.

</details>

<details>
<summary><b>Cursor</b></summary>

Add to `~/.cursor/mcp.json` (or the project-local `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "intervals-icu": {
      "command": "uvx",
      "args": ["intervals-icu-mcp"],
      "env": {
        "INTERVALS_ICU_API_KEY": "your-api-key-here",
        "INTERVALS_ICU_ATHLETE_ID": "i123456"
      }
    }
  }
}
```

Restart Cursor and open *Settings → MCP* to verify the server is listed.

</details>

<details>
<summary><b>ChatGPT</b> — requires a paid plan, Developer Mode, and a publicly reachable URL <em>(walkthrough not yet verified end-to-end)</em></summary>

ChatGPT's custom MCP connector flow requires running the server over HTTP and exposing it via a tunnel, then registering the URL in ChatGPT's Developer Mode settings. See [docs/chatgpt-connector.md](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/chatgpt-connector.md) for the full walkthrough, plan-tier requirements, and security notes.

</details>

## Usage

Ask Claude to interact with your Intervals.icu data in natural language. A few starter prompts:

```
"Show me my activities from the last 30 days"
"Am I overtraining? Check my CTL, ATL, and TSB"
"How's my recovery this week? Show HRV and sleep trends"
"Create a sweet spot cycling workout for tomorrow"
"What's my 20-minute power and FTP?"
```

For the full catalogue of example prompts by category, see [docs/examples.md](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/examples.md).

## Available Tools

61 tools, 4 resources, and 7 prompt templates. One-line summary below — full reference in [docs/tools.md](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md).

| Category | Tools | Summary |
|---|---|---|
| [Activities](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#activities-12-tools) | 12 | Query, search, update, delete, download activities |
| [Activity Analysis](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#activity-analysis-8-tools) | 8 | Streams, intervals, best efforts, histograms |
| [Activity Messages](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#activity-messages-2-tools) | 2 | Read and post notes/comments/coach feedback on activities |
| [Athlete](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#athlete-3-tools) | 3 | Profile, CTL/ATL/TSB analysis, and fitness chart time-series |
| [Wellness](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#wellness-3-tools) | 3 | HRV, sleep, recovery metrics |
| [Events / Calendar](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#events--calendar-11-tools) | 11 | Planned workouts, races, notes, ATP periodization (bulk ops supported) |
| [Performance / Curves](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#performance--curves-3-tools) | 3 | Power, HR, and pace curves with zones |
| [Workout Library](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#workout-library-2-tools) | 2 | Browse workout folders and training plans |
| [Gear Management](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#gear-management-6-tools) | 6 | Track equipment and maintenance reminders |
| [Sport Settings](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#sport-settings-5-tools) | 5 | FTP, FTHR, pace thresholds, and zones |
| [Custom Items](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#custom-items-5-tools) | 5 | User customizations: custom charts, fields, zones, dashboard panels |

## Delete Safety Mode

Destructive tools are gated by the optional `INTERVALS_ICU_DELETE_MODE` env var (`safe` / `full` / `none`, default `safe`) — a server-side gate outside the model's reach, so unregistered tools can't be invoked. See [docs/tools.md](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#delete-safety-mode) for the full mode table, response envelope, and TZ-buffer rationale.

## Remote Deployment (HTTP / SSE)

The server runs over **stdio** by default — the right transport for local clients like Claude Desktop, Claude Code, and Cursor. HTTP and SSE transports are available for remote or hosted use.

> ⚠️ MCP has **no built-in authentication** — never expose an HTTP-mode server to an untrusted network without a tunnel (Tailscale, Cloudflare Tunnel) or an authenticating reverse proxy.

See [docs/remote-deployment.md](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/remote-deployment.md) for transport flags and the full security model.

## Documentation

- [Example prompts](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/examples.md) — full catalogue of natural-language prompts by category
- [Tool reference](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md) — complete tool, resource, and prompt inventory
- [Architecture overview](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/architecture.md) — how the server, middleware, client, and tools fit together
- [Remote deployment (HTTP/SSE)](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/remote-deployment.md) — transports, flags, and the security model for hosted/remote setups
- [Testing guide](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/testing.md) — conventions for pytest + respx, fixtures, and running the suite
- [Changelog](CHANGELOG.md) — release history
- [Adding a new tool](https://github.com/hhopke/intervals-icu-mcp/blob/main/.claude/skills/add-tool/SKILL.md) — step-by-step workflow for contributors

## Contributing

Issues and pull requests are welcome. Before opening a PR, run `make can-release` locally to match what CI enforces (ruff, pyright, pytest). For new tools, follow the pattern in [`.claude/skills/add-tool/SKILL.md`](https://github.com/hhopke/intervals-icu-mcp/blob/main/.claude/skills/add-tool/SKILL.md) and add a respx-mocked test file alongside the implementation.

## License

MIT License - see the [LICENSE](https://github.com/hhopke/intervals-icu-mcp/blob/main/LICENSE) file for details.

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Intervals.icu. All product names, logos, and brands are property of their respective owners.
