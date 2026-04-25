<!-- mcp-name: io.github.hhopke/intervals-icu-mcp -->

# Intervals.icu MCP Server

![intervals-icu-mcp demo](https://raw.githubusercontent.com/hhopke/intervals-icu-mcp/main/docs/demo.gif)

A Model Context Protocol (MCP) server for Intervals.icu integration. Access your training data, wellness metrics, and performance analysis through Claude, ChatGPT, and other LLMs.

> Originally based on [eddmann/intervals-icu-mcp](https://github.com/eddmann/intervals-icu-mcp) (MIT licensed). This project is an independent continuation with significant bug fixes and new features — see [CHANGELOG.md](https://github.com/hhopke/intervals-icu-mcp/blob/main/CHANGELOG.md) for details.

[![Tests](https://github.com/hhopke/intervals-icu-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/hhopke/intervals-icu-mcp/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/hhopke/intervals-icu-mcp/blob/main/LICENSE)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue?logo=docker)](https://github.com/hhopke/intervals-icu-mcp/pkgs/container/intervals-icu-mcp)

## Overview

51 tools spanning activities, activity analysis, athlete profile, wellness, events/calendar, performance curves, workout library, gear, and sport settings — plus 2 MCP Resources (athlete profile, workout syntax reference) and 7 MCP Prompts (training analysis, recovery check, weekly planning, and more). See [Available Tools](#available-tools) for the per-category breakdown.

## Quick Start

Running with Claude Desktop, in 30 seconds:

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

## Installation

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

> ⚠️ **Unverified.** The steps below are derived from OpenAI's and FastMCP's docs but have not been confirmed end-to-end against this server. Plan-tier eligibility for custom MCP connectors changes frequently — always check OpenAI's [current connector docs](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta) before assuming your plan supports it. PRs from anyone who has confirmed the flow are welcome.

**Requirements (as of writing)**
- A ChatGPT plan that supports custom MCP connectors and Developer Mode (typically a paid tier — Free does not qualify; check OpenAI docs for the current list).
- **Developer Mode** enabled in ChatGPT settings.
- A public HTTPS URL pointing at the server (a tunnel is the easiest way).

**Step 1 — Start the server in HTTP mode**

```bash
intervals-icu-mcp --transport http --host 127.0.0.1 --port 8000
```

**Step 2 — Expose it via a tunnel**

*Cloudflare Tunnel (free, recommended):*
```bash
brew install cloudflared   # macOS — or download from developers.cloudflare.com
cloudflared tunnel --url http://127.0.0.1:8000
```
Cloudflare prints a URL like `https://abc-def-123.trycloudflare.com`. Your MCP endpoint is `https://abc-def-123.trycloudflare.com/mcp`.

*ngrok (quick to try, URL changes on free-tier restart):*
```bash
ngrok http 8000
```
Your endpoint is `https://<random>.ngrok-free.app/mcp`.

**Step 3 — Add the connector in ChatGPT**

1. ChatGPT → **Settings** → **Connectors** → enable **Developer Mode** (Advanced settings) if you haven't already.
2. **Connectors** → **Create** (or **Add new connector**).
3. **MCP Server URL**: your tunnel URL with `/mcp` appended.
4. **Authentication**: *No authentication* is fine for personal use behind a tunnel; configure OAuth if you've put one in front.
5. Click **Create** and trust the provider.
6. In each new chat, enable the connector from the chat's tools menu — it isn't enabled globally.

**Security note:** The server runs with your personal `INTERVALS_ICU_API_KEY` — anyone who knows the tunnel URL can query your account. Add [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/) or [Tailscale Funnel](https://tailscale.com/kb/1223/tailscale-funnel) to restrict who can reach the endpoint.

> Deep Research mode (a separate ChatGPT feature) requires `search` and `fetch` tools that this server doesn't expose, so it will reject the connector there. Regular chat with Developer Mode works.

</details>

## Remote Deployment (HTTP / SSE)

By default the server runs over **stdio** — the right transport for local clients like Claude Desktop, Claude Code, and Cursor. For remote deployment (hosted MCP, reverse proxy, Docker-on-a-server, ChatGPT connector), pass `--transport`:

```bash
# Streamable HTTP (recommended — used by ChatGPT and modern remote clients)
intervals-icu-mcp --transport http --host 127.0.0.1 --port 8000

# Legacy SSE (for clients that haven't moved to streamable HTTP yet)
intervals-icu-mcp --transport sse --host 127.0.0.1 --port 8000
```

| Flag | Default | Description |
|---|---|---|
| `--transport` | `stdio` | One of `stdio`, `http`, `sse`, `streamable-http` |
| `--host` | `127.0.0.1` | Interface to bind. Use `0.0.0.0` only inside a container where Docker controls the exposure. |
| `--port` | `8000` | TCP port |
| `--path` | (framework default) | URL path to mount the server under |

> ⚠️ **Security: do not expose an HTTP-mode server to untrusted networks.**
>
> The MCP protocol has **no built-in authentication**. Anyone who can reach the URL can exercise every tool with your credentials — read every activity, delete activities, modify your FTP, create calendar events, etc. Binding to `0.0.0.0` on a direct-exposed host (VPS, LAN with open port) is equivalent to publishing your Intervals.icu API key.
>
> For remote access, prefer one of the following:
> - **Tailscale / Cloudflare Tunnel / ZeroTier** — only your authenticated devices can reach the endpoint. Zero code changes, simplest option.
> - **Reverse proxy with auth** (nginx + basic auth, Cloudflare Access, etc.) — terminates TLS and gates access.
> - **SSH tunnel** — `ssh -L 8000:localhost:8000 host` if you just need occasional access from one machine.
>
> Credentials are always read from `INTERVALS_ICU_API_KEY` and `INTERVALS_ICU_ATHLETE_ID` — use env vars (not a committed `.env`) when deploying to a shared host.

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

51 tools, 2 resources, and 7 prompt templates. One-line summary below — full reference in [docs/tools.md](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md).

| Category | Tools | Summary |
|---|---|---|
| [Activities](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#activities-12-tools) | 12 | Query, search, update, delete, download activities |
| [Activity Analysis](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#activity-analysis-8-tools) | 8 | Streams, intervals, best efforts, histograms |
| [Athlete](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#athlete-2-tools) | 2 | Profile and CTL/ATL/TSB fitness analysis |
| [Wellness](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#wellness-3-tools) | 3 | HRV, sleep, recovery metrics |
| [Events / Calendar](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#events--calendar-10-tools) | 10 | Planned workouts, races, notes (bulk ops supported) |
| [Performance / Curves](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#performance--curves-3-tools) | 3 | Power, HR, and pace curves with zones |
| [Workout Library](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#workout-library-2-tools) | 2 | Browse workout folders and training plans |
| [Gear Management](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#gear-management-6-tools) | 6 | Track equipment and maintenance reminders |
| [Sport Settings](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md#sport-settings-5-tools) | 5 | FTP, FTHR, pace thresholds, and zones |

## Documentation

- [Example prompts](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/examples.md) — full catalogue of natural-language prompts by category
- [Tool reference](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/tools.md) — complete tool, resource, and prompt inventory
- [Architecture overview](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/architecture.md) — how the server, middleware, client, and tools fit together
- [Testing guide](https://github.com/hhopke/intervals-icu-mcp/blob/main/docs/testing.md) — conventions for pytest + respx, fixtures, and running the suite
- [Changelog](CHANGELOG.md) — release history
- [Adding a new tool](https://github.com/hhopke/intervals-icu-mcp/blob/main/.claude/skills/add-tool/SKILL.md) — step-by-step workflow for contributors

## Contributing

Issues and pull requests are welcome. Before opening a PR, run `make can-release` locally to match what CI enforces (ruff, pyright, pytest). For new tools, follow the pattern in [`.claude/skills/add-tool/SKILL.md`](https://github.com/hhopke/intervals-icu-mcp/blob/main/.claude/skills/add-tool/SKILL.md) and add a respx-mocked test file alongside the implementation.

## License

MIT License - see the [LICENSE](https://github.com/hhopke/intervals-icu-mcp/blob/main/LICENSE) file for details.

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Intervals.icu. All product names, logos, and brands are property of their respective owners.
