"""All Serply MCP tools registered in one place."""
from __future__ import annotations

import hashlib
import urllib.parse
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from serply_mcp.auth import check_ssrf
from serply_mcp.client import SerplyClient
from serply_mcp.config import Settings
from serply_mcp.errors import SerplyError

ProxyLocation = Literal[
    "US", "EU", "CA", "IE", "GB", "FR", "DE", "SE", "IN", "JP", "KR", "SG", "AU", "BR"
]
Device = Literal["desktop", "mobile"]


def register_tools(mcp: FastMCP, client: SerplyClient, settings: Settings) -> None:
    """Register all 8 Serply tools and the account/usage resource on *mcp*."""

    # ── helpers ──────────────────────────────────────────────────────────────

    def _headers(proxy_location: str, device: str) -> dict[str, str]:
        return {"X-Proxy-Location": proxy_location, "X-User-Agent": device}

    # ── tools ─────────────────────────────────────────────────────────────────

    @mcp.tool()
    async def google_search(
        query: Annotated[str, Field(description="The search query string.", max_length=2048)],
        num: Annotated[int, Field(ge=1, le=100, description="Number of results to return (1–100).")] = 10,
        start: Annotated[int, Field(ge=0, description="Zero-based result offset for pagination.")] = 0,
        proxy_location: Annotated[ProxyLocation, Field(description="Country from which the search is issued.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type — affects ranking and snippets.")] = "desktop",
    ) -> dict[str, Any]:
        """Search Google and return organic results via the Serply API.

        Use this tool whenever you need current, real-world information from the web:
        factual lookups, recent events, product research, technical documentation,
        code examples, or anything that benefits from live Google results.

        Returns up to `num` organic results, each with:
        - title  — page headline
        - link   — canonical URL
        - description — snippet shown in the SERP

        Also includes a top-level `answer` field when Google surfaces a direct answer
        box (e.g. a definition, calculation, or featured snippet), and `total` with the
        estimated total result count.

        Use `start` + `num` to paginate: start=0 is page 1, start=10 is page 2, etc.
        Use `proxy_location` to get geo-specific results (e.g. "GB" for UK results).
        """
        try:
            path = SerplyClient.build_query_path("/v1/search", query, num=num, start=start or None)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            results = data.get("results", [])
            return {
                "results": results,
                "total": data.get("total"),
                "answer": data.get("answer"),
                "summary": f"Found {len(results)} Google results for '{query}'",
            }
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def bing_search(
        query: Annotated[str, Field(description="The search query string.", max_length=2048)],
        proxy_location: Annotated[ProxyLocation, Field(description="Country from which the search is issued.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> dict[str, Any]:
        """Search Bing and return organic results, ads, and shopping ads via Serply.

        Use this tool as a complement to `google_search` when you want:
        - A second opinion on search results from a different index
        - Shopping/product results — Bing surfaces more shopping ads than Google
        - Bing-specific ranking or freshness signals

        Returns:
        - results       — organic web results (title, link, description)
        - ads           — sponsored text ads
        - shopping_ads  — product-level shopping ads with prices and images
        - location      — inferred user location used by Bing
        """
        try:
            path = SerplyClient.build_query_path("/v1/b/search", query)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            results = data.get("results", [])
            ads = data.get("ads", [])
            shopping_ads = data.get("shopping_ads", [])
            return {
                "results": results,
                "ads": ads,
                "shopping_ads": shopping_ads,
                "location": data.get("location"),
                "summary": f"Found {len(results)} Bing results, {len(ads)} ads, {len(shopping_ads)} shopping ads for '{query}'",
            }
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def google_video_search(
        query: Annotated[str, Field(description="The video search query.", max_length=2048)],
        num: Annotated[int, Field(ge=1, le=100, description="Number of video results.")] = 10,
        proxy_location: Annotated[ProxyLocation, Field(description="Country context for the search.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> dict[str, Any]:
        """Search Google Videos and return video results via Serply.

        Use this tool when the user is looking for video content: tutorials,
        product demos, news clips, lectures, or any query where video results
        are more relevant than web pages.

        Results come primarily from YouTube and other indexed video platforms.
        Each result includes:
        - title       — video title
        - link        — URL to the video
        - description — snippet or channel info
        """
        try:
            path = SerplyClient.build_query_path("/v1/video", query, num=num)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            results = data.get("results", [])
            return {
                "results": results,
                "total": data.get("total"),
                "answer": data.get("answer"),
                "summary": f"Found {len(results)} video results for '{query}'",
            }
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def google_news_search(
        query: Annotated[str, Field(description="The news search query.", max_length=2048)],
        ceid: Annotated[str | None, Field(description="Country/language edition filter, e.g. 'US:en' or 'GB:en'. Scopes results to that edition.")] = None,
        proxy_location: Annotated[ProxyLocation, Field(description="Country context for the search.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> dict[str, Any]:
        """Search Google News and return news articles and named entities via Serply.

        Use this tool when you need recent news coverage of a topic: breaking news,
        company announcements, political events, sports scores, or anything time-sensitive.
        Results are fresher than standard web search — typically hours to days old.

        Set `ceid` to scope to a specific country edition:
        - "US:en" → US English news
        - "GB:en" → UK English news
        - "FR:fr" → French news in French

        Returns:
        - feed.entries — list of news articles with title, link, published date, source
        - entities     — named entities (people, orgs, places) extracted from results
        """
        try:
            path = SerplyClient.build_query_path("/v1/news", query)
            if ceid:
                path += f"&ceid={urllib.parse.quote_plus(ceid)}"
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            feed = data.get("feed", {}) or {}
            entries = feed.get("entries", []) if isinstance(feed, dict) else []
            return {
                "feed": feed,
                "entities": data.get("entities", []),
                "summary": f"Found {len(entries)} news articles for '{query}'",
            }
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def google_jobs_search(
        query: Annotated[str, Field(description="Job title, role, or keyword to search for.", max_length=2048)],
        proxy_location: Annotated[ProxyLocation, Field(description="Country for job results. Note: Serply returns North American results only.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> dict[str, Any]:
        """Search Google Jobs and return job postings via Serply.

        Use this tool to find job listings from Google's job search index, which
        aggregates postings from LinkedIn, Indeed, company career pages, and other
        job boards.

        IMPORTANT: Serply's Jobs API returns North American results regardless of
        `proxy_location`. Use it for US/Canada job searches.

        Each job result includes:
        - position       — job title
        - description    — employer details, salary perks, remote/hybrid flags
        - highlights     — key bullet points from the job description
        - link           — URL to apply or view the full posting
        - logo           — employer logo URL
        - metadata       — posting date, location, company name
        """
        try:
            path = SerplyClient.build_query_path("/v1/job/search", query)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            jobs = data.get("jobs", [])
            return {
                "jobs": jobs,
                "ts": data.get("ts"),
                "device_region": data.get("device_region"),
                "summary": f"Found {len(jobs)} job postings for '{query}'",
            }
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def google_scholar_search(
        query: Annotated[str, Field(description="Academic search query — paper title, author name, topic, or DOI fragment.", max_length=2048)],
        num: Annotated[int, Field(ge=1, le=100, description="Number of academic results.")] = 10,
        proxy_location: Annotated[ProxyLocation, Field(description="Country context for the search.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> dict[str, Any]:
        """Search Google Scholar and return academic papers and citations via Serply.

        Use this tool for research tasks: finding peer-reviewed papers, locating
        citations, understanding the academic consensus on a topic, or retrieving
        publication metadata.

        Each result includes:
        - title       — paper title
        - link        — URL to the paper or its Google Scholar entry
        - description — abstract snippet, authors, journal, and year
        """
        try:
            path = SerplyClient.build_query_path("/v1/scholar", query, num=num)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            results = data.get("results", [])
            return {
                "results": results,
                "total": data.get("total"),
                "ts": data.get("ts"),
                "summary": f"Found {len(results)} academic results for '{query}'",
            }
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def amazon_product_search(
        query: Annotated[str, Field(description="Product name, brand, or keyword to search Amazon for.", max_length=2048)],
        proxy_location: Annotated[ProxyLocation, Field(description="Country storefront context.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> dict[str, Any]:
        """Search Amazon products via Google Shopping (Serply) and return product listings.

        Use this tool when the user wants to:
        - Find product prices and availability on Amazon
        - Compare products by rating and review count
        - Look up ASINs for specific products
        - Identify bestsellers or Prime-eligible items in a category

        Each product result includes:
        - title         — product name
        - price         — listed price string (e.g. "$24.99")
        - asin          — Amazon Standard Identification Number
        - rating_stars  — average customer rating (0–5)
        - review_count  — number of customer reviews
        - link          — direct product URL
        - img_url       — product image URL
        - prime         — True if Prime-eligible
        - bestseller    — True if marked as a bestseller
        - is_sponsor    — True if a sponsored/ad result
        """
        try:
            path = SerplyClient.build_query_path("/v1/product/search", query)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            products = data.get("products", [])
            return {
                "products": products,
                "ads": data.get("ads", []),
                "ts": data.get("ts"),
                "summary": f"Found {len(products)} Amazon products for '{query}'",
            }
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def scrape_url(
        url: Annotated[str, Field(description="The full URL to scrape. Must use http:// or https://. Private/internal addresses are blocked.")],
        response_type: Annotated[
            Literal["full", "markdown"],
            Field(description="Output format: 'markdown' strips HTML to clean text (best for LLMs); 'full' returns raw HTML.")
        ] = "markdown",
    ) -> dict[str, Any]:
        """Fetch and return the content of any public web page via Serply.

        Use this tool when you have a specific URL and need to read its content —
        for example, after a search returns a link you want to read in full, or when
        the user pastes a URL and asks you to summarize or extract information from it.

        Prefer `response_type="markdown"` for LLM tasks — it strips navigation, ads,
        and boilerplate, leaving clean readable text. Use `response_type="full"` only
        when you need the raw HTML structure.

        Security: private/internal IP ranges (127.x, 10.x, 172.16-31.x, 192.168.x,
        169.254.x) and non-http(s) schemes are blocked to prevent SSRF attacks.

        Returns:
        - content        — page text or HTML
        - content_hash   — SHA-256 of content (for deduplication)
        - content_length — byte length of content
        - url            — final URL after redirects
        - response_type  — the format returned
        """
        if settings.block_internal_urls:
            try:
                await check_ssrf(url)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
        try:
            data = await client.post("/v1/request", json={"url": url, "response_type": response_type})
            content = data.get("content", "") or ""
            return {
                "content": content,
                "content_hash": hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest(),
                "content_length": len(content),
                "url": data.get("url", url),
                "response_type": data.get("response_type", response_type),
                "summary": f"Scraped {len(content)} chars from {url} as {response_type}",
            }
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    # ── resource ──────────────────────────────────────────────────────────────

    @mcp.resource("serply://account/usage")
    def account_usage() -> str:
        """How to view your Serply.io API usage and quota."""
        return (
            "Log in to https://serply.io/dashboard to view your current plan, "
            "requests used, requests remaining, and billing details. "
            "Rate-limit headers (x-ratelimit-requests-limit, "
            "x-ratelimit-requests-remaining) are also returned with every API response."
        )
