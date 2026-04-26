# ChatGPT Custom Connector Setup

> ⚠️ **Unverified.** The steps below are derived from OpenAI's and FastMCP's docs but have not been confirmed end-to-end against this server. Plan-tier eligibility for custom MCP connectors changes frequently — always check OpenAI's [current connector docs](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta) before assuming your plan supports it. PRs from anyone who has confirmed the flow are welcome.

## Requirements (as of writing)

- A ChatGPT plan that supports custom MCP connectors and Developer Mode (typically a paid tier — Free does not qualify; check OpenAI docs for the current list).
- **Developer Mode** enabled in ChatGPT settings.
- A public HTTPS URL pointing at the server (a tunnel is the easiest way).

## Step 1 — Start the server in HTTP mode

```bash
intervals-icu-mcp --transport http --host 127.0.0.1 --port 8000
```

## Step 2 — Expose it via a tunnel

**Cloudflare Tunnel (free, recommended):**

```bash
brew install cloudflared   # macOS — or download from developers.cloudflare.com
cloudflared tunnel --url http://127.0.0.1:8000
```

Cloudflare prints a URL like `https://abc-def-123.trycloudflare.com`. Your MCP endpoint is `https://abc-def-123.trycloudflare.com/mcp`.

**ngrok (quick to try, URL changes on free-tier restart):**

```bash
ngrok http 8000
```

Your endpoint is `https://<random>.ngrok-free.app/mcp`.

## Step 3 — Add the connector in ChatGPT

1. ChatGPT → **Settings** → **Connectors** → enable **Developer Mode** (Advanced settings) if you haven't already.
2. **Connectors** → **Create** (or **Add new connector**).
3. **MCP Server URL**: your tunnel URL with `/mcp` appended.
4. **Authentication**: *No authentication* is fine for personal use behind a tunnel; configure OAuth if you've put one in front.
5. Click **Create** and trust the provider.
6. In each new chat, enable the connector from the chat's tools menu — it isn't enabled globally.

## Security note

The server runs with your personal `INTERVALS_ICU_API_KEY` — anyone who knows the tunnel URL can query your account. Add [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/) or [Tailscale Funnel](https://tailscale.com/kb/1223/tailscale-funnel) to restrict who can reach the endpoint.

> Deep Research mode (a separate ChatGPT feature) requires `search` and `fetch` tools that this server doesn't expose, so it will reject the connector there. Regular chat with Developer Mode works.
