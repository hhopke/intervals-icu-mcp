# Remote Deployment (HTTP / SSE)

How to run the server over HTTP/SSE for remote or hosted use, the available transport flags, and the security model you must apply before exposing it.

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

## Container liveness check

The image runs the stdlib probe every 30 seconds with a 5-second hard timeout,
a 5-second start period, and 3 retries. Its own deadline defaults to 2 seconds.
By default it reads Linux `/proc/1/cmdline` and recognizes the image's Python
module entrypoint. A known stdio server gets an import-only check; HTTP,
streamable HTTP, and SSE servers receive exactly `GET /health` at their
configured target. The probe requires HTTP 200 and `{"status":"ok"}`. It does
not verify MCP initialization, credentials, or upstream API availability.

For wrappers such as Docker `--init`, unknown entrypoints, or unreadable process
information, the default check falls back to the previous import-only check.
That fallback does not verify HTTP liveness. For an HTTP server behind a
wrapper, pass either or both target flags; this skips `/proc` and checks HTTP.
The omitted value defaults to host `127.0.0.1` or port `8000`. Wildcard hosts
map to loopback. For example:

```yaml
services:
  intervals-icu-mcp:
    image: ghcr.io/hhopke/intervals-icu-mcp:latest
    command: ["--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
    # Supply credentials using your existing environment/secret configuration.
    healthcheck:
      test: ["CMD", "python", "-m", "intervals_icu_mcp.healthcheck", "--host", "0.0.0.0", "--port", "8000"]
```

The health route stays at `/health` regardless of MCP's `--path`; the server
rejects HTTP MCP paths `/health` and `/health/` because they collide with it.
The probe deadline bounds connect/read work; Docker's hard timeout bounds the
whole check, including process startup, DNS resolution, and slow HTTP framing.
