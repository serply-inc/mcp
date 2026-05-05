# serply-mcp

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/protocol-MCP-7b3fe4.svg)](https://modelcontextprotocol.io)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that gives any MCP-compatible AI client live web search, news, academic search, job listings, Amazon product lookup, and URL scraping — powered by the [Serply.io](https://serply.io) API.

> **Disclaimer:** This project is not affiliated with, endorsed by, or sponsored by Serply, Inc. Serply.io is a third-party paid service. You need your own Serply API key to use this server.

---

## What this server provides

Eight tools that give AI assistants real-time access to the web:

| Tool | What it does |
|---|---|
| `google_search` | Google web search — organic results, featured snippets, and answer boxes |
| `bing_search` | Bing web search — organic results, ads, and shopping results |
| `google_video_search` | Google video search — results from YouTube and other video platforms |
| `google_news_search` | Google News — fresh articles with named-entity extraction |
| `google_jobs_search` | Google Jobs — job listings aggregated from LinkedIn, Indeed, and company sites |
| `google_scholar_search` | Google Scholar — peer-reviewed papers, citations, and abstracts |
| `amazon_product_search` | Amazon product listings — prices, ratings, ASINs, and Prime eligibility |
| `scrape_url` | Fetch and convert any public web page to clean Markdown or raw HTML |

---

## Quickstart

### stdio (recommended for local use)

No Docker or auth token required. The MCP client launches the server as a subprocess.

**Step 1 — Install**

```bash
# Using uv (recommended)
uv sync

# Or pip
pip install -e .
```

**Step 2 — Get a Serply API key**

Sign up at [serply.io](https://serply.io) (free tier: 300 requests/month).

**Step 3 — Add to your MCP client**

For **Claude Desktop**, edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "serply": {
      "command": "uv",
      "args": ["run", "python", "-m", "serply_mcp"],
      "cwd": "/path/to/serply-mcp",
      "env": {
        "SERPLY_API_KEY": "your-serply-api-key",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

For **Claude Code**, run:

```bash
claude mcp add serply \
  --command "uv" \
  --args "run,python,-m,serply_mcp" \
  --cwd "/path/to/serply-mcp" \
  --env "SERPLY_API_KEY=your-serply-api-key,MCP_TRANSPORT=stdio"
```

---

## Tools

Detailed descriptions for all 8 tools. Parameters marked `*` are required.

---

### `google_search`

Search Google and return organic results, answer boxes, and featured snippets.

Use this tool for factual lookups, recent events, product research, technical documentation, or anything that benefits from live Google results.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` * | string | — | Search query (max 2048 chars) |
| `num` | integer | `10` | Number of results to return (1–100) |
| `start` | integer | `0` | Result offset for pagination (0 = page 1, 10 = page 2, …) |
| `proxy_location` | string | `"US"` | Country for geo-specific results: `US` `EU` `CA` `IE` `GB` `FR` `DE` `SE` `IN` `JP` `KR` `SG` `AU` `BR` |
| `device` | string | `"desktop"` | Emulated device type: `desktop` or `mobile` |

**Returns:** `results[]` (title, link, description), `total`, `answer` (featured snippet if present)

---

### `bing_search`

Search Bing and return organic results, ads, and shopping results.

Use as a complement to `google_search` for a second opinion, shopping results, or Bing-specific freshness signals.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` * | string | — | Search query (max 2048 chars) |
| `proxy_location` | string | `"US"` | Country context (see `google_search` for values) |
| `device` | string | `"desktop"` | `desktop` or `mobile` |

**Returns:** `results[]`, `ads[]`, `shopping_ads[]`, `location`

---

### `google_video_search`

Search Google Videos and return results from YouTube and other video platforms.

Use when the user is looking for tutorials, product demos, news clips, or any query where video content is more useful than web pages.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` * | string | — | Video search query (max 2048 chars) |
| `num` | integer | `10` | Number of results (1–100) |
| `proxy_location` | string | `"US"` | Country context |
| `device` | string | `"desktop"` | `desktop` or `mobile` |

**Returns:** `results[]` (title, link, description), `total`

---

### `google_news_search`

Search Google News and return fresh articles with named-entity extraction.

Use for breaking news, company announcements, political events, sports, or anything time-sensitive. Results are typically hours to days old — much fresher than standard web search.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` * | string | — | News search query (max 2048 chars) |
| `ceid` | string | `null` | Country/language edition, e.g. `US:en`, `GB:en`, `FR:fr` |
| `proxy_location` | string | `"US"` | Country context |
| `device` | string | `"desktop"` | `desktop` or `mobile` |

**Returns:** `feed.entries[]` (title, link, published date, source), `entities[]` (named people, orgs, places)

---

### `google_jobs_search`

Search Google Jobs and return listings aggregated from LinkedIn, Indeed, and company career pages.

> **Note:** Serply's Jobs API returns North American results regardless of `proxy_location`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` * | string | — | Job title, role, or keyword (max 2048 chars) |
| `proxy_location` | string | `"US"` | Country context |
| `device` | string | `"desktop"` | `desktop` or `mobile` |

**Returns:** `jobs[]` (position, description, salary, remote/hybrid flags, perks, link, logo, posted date)

---

### `google_scholar_search`

Search Google Scholar and return academic papers, citations, and abstracts.

Use for research tasks: finding peer-reviewed papers, locating citations, understanding academic consensus, or retrieving publication metadata.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` * | string | — | Paper title, author, topic, or DOI fragment (max 2048 chars) |
| `num` | integer | `10` | Number of results (1–100) |
| `proxy_location` | string | `"US"` | Country context |
| `device` | string | `"desktop"` | `desktop` or `mobile` |

**Returns:** `results[]` (title, link, abstract snippet, authors, journal, year), `total`

---

### `amazon_product_search`

Search Amazon products and return listings with prices, ratings, and ASINs.

Use to find product prices and availability, compare by rating and review count, look up ASINs, or identify bestsellers and Prime-eligible items.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` * | string | — | Product name, brand, or keyword (max 2048 chars) |
| `proxy_location` | string | `"US"` | Country storefront context |
| `device` | string | `"desktop"` | `desktop` or `mobile` |

**Returns:** `products[]` (title, price, asin, rating_stars, review_count, link, img_url, prime, bestseller, is_sponsor), `ads[]`

---

### `scrape_url`

Fetch and return the content of any public web page.

Use when you have a specific URL and need to read its full content — for example, after a search returns a link you want to summarize, or when the user shares a URL and asks for analysis.

Prefer `response_type="markdown"` for LLM tasks — it strips navigation, ads, and boilerplate, leaving clean readable text. Use `response_type="full"` only when you need the raw HTML structure.

> **Security:** Private/internal IP ranges and non-http(s) schemes are blocked by default to prevent SSRF attacks.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` * | string | — | Full URL to scrape (`http://` or `https://` only) |
| `response_type` | string | `"markdown"` | Output format: `markdown` (clean text) or `full` (raw HTML) |

**Returns:** `content`, `content_hash` (SHA-256), `content_length`, `url` (final URL after redirects), `response_type`

---

## Configuration

All configuration is via environment variables. No config file is required.

| Variable | Required | Default | Description |
|---|---|---|---|
| `SERPLY_API_KEY` | Yes | — | Your Serply.io API key |
| `MCP_TRANSPORT` | No | `stdio` | `stdio` (local) or `http` (Docker/remote) |
| `MCP_AUTH_TOKEN` | For HTTP | — | Bearer token clients must send. Min 32 chars. Generate: `openssl rand -hex 32` |
| `MCP_HTTP_HOST` | No | `0.0.0.0` | HTTP bind host |
| `MCP_HTTP_PORT` | No | `8000` | HTTP bind port |
| `MCP_HTTP_PATH` | No | `/mcp` | HTTP mount path |
| `MCP_RATE_LIMIT_PER_MINUTE` | No | `60` | Per-client request rate limit |
| `SERPLY_BASE_URL` | No | `https://api.serply.io` | Override the Serply API base URL |
| `SERPLY_TIMEOUT_SECONDS` | No | `30` | Per-request timeout in seconds |
| `SERPLY_MAX_RETRIES` | No | `3` | Retry attempts on 429/5xx (exponential backoff) |
| `BLOCK_INTERNAL_URLS` | No | `true` | Block private/loopback IPs in `scrape_url` (SSRF protection) |
| `LOG_LEVEL` | No | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

---

## Running locally

### stdio transport

The simplest way to run the server. Your MCP client starts the process automatically using the config shown in [Quickstart](#quickstart).

To run manually:

```bash
SERPLY_API_KEY=your-key MCP_TRANSPORT=stdio python -m serply_mcp
```

### HTTP transport (Docker)

Suitable for running as a persistent service accessible over a network.

```bash
# 1. Set required environment variables
export SERPLY_API_KEY=your-serply-api-key
export MCP_AUTH_TOKEN=$(openssl rand -hex 32)

# 2. Build and start
docker compose up --build

# 3. Verify the server is healthy
curl http://localhost:8000/healthz
# → {"status":"ok"}
```

The server listens on `http://127.0.0.1:8000/mcp`. Put a TLS-terminating reverse proxy (Caddy, nginx, Traefik) in front before exposing beyond localhost.

---

## Client setup

### Claude Desktop — stdio

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)  
`%APPDATA%\Claude\claude_desktop_config.json` (Windows)

```json
{
  "mcpServers": {
    "serply": {
      "command": "uv",
      "args": ["run", "python", "-m", "serply_mcp"],
      "cwd": "/path/to/serply-mcp",
      "env": {
        "SERPLY_API_KEY": "your-serply-api-key",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

### Claude Desktop — HTTP (remote server)

```json
{
  "mcpServers": {
    "serply": {
      "url": "https://your-server/mcp",
      "headers": {
        "Authorization": "Bearer your-mcp-auth-token"
      }
    }
  }
}
```

### Claude Code — stdio

```bash
claude mcp add serply \
  --command "uv" \
  --args "run,python,-m,serply_mcp" \
  --cwd "/path/to/serply-mcp" \
  --env "SERPLY_API_KEY=your-serply-api-key,MCP_TRANSPORT=stdio"
```

### Cursor / other MCP clients — stdio

```json
{
  "mcpServers": {
    "serply": {
      "command": "uv",
      "args": ["run", "python", "-m", "serply_mcp"],
      "cwd": "/path/to/serply-mcp",
      "env": {
        "SERPLY_API_KEY": "your-serply-api-key",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

---

## Security

- **Bearer auth** — `MCP_AUTH_TOKEN` is required for HTTP transport. Tokens under 32 characters are rejected at startup. Comparison uses `secrets.compare_digest` (timing-safe).
- **SSRF protection** — `scrape_url` resolves hostnames before each request and rejects RFC 1918 private ranges, loopback, link-local (`169.254.x.x`), and CGNAT addresses. Controlled by `BLOCK_INTERNAL_URLS`.
- **Rate limiting** — Per-token sliding-window limiter (in-memory). Default: 60 requests/minute.
- **Secret handling** — `SERPLY_API_KEY` and `MCP_AUTH_TOKEN` are read from env only. Neither appears in any log line.
- **Container hardening** — Runs as uid 10001, read-only root filesystem, all Linux capabilities dropped, `no-new-privileges`.
- **TLS** — The server serves plain HTTP. Always terminate TLS at a reverse proxy when exposing beyond localhost.

---

## Development

```bash
# Install all dependencies including dev tools
uv sync --all-extras

make test         # pytest with coverage
make lint         # ruff check
make type-check   # mypy --strict
make format       # ruff format + autofix
make build        # docker compose build
make run          # docker compose up
```

Coverage target: 90% (currently ~98%).

---

## License

[MIT](LICENSE)

This project is not affiliated with Serply, Inc. Serply.io is a third-party service — see [serply.io](https://serply.io) for pricing and terms.
