"""All Serply MCP tools registered in one place."""
from __future__ import annotations

import hashlib
import urllib.parse
from typing import Annotated, Literal

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


def _clean_url(url: str) -> str:
    """Decode percent-encoding and strip Bing/Google tracking parameters."""
    decoded = urllib.parse.unquote(url)
    for marker in ("&sa=", "&ved=", "&usg=", "&ntb=", "!&&p="):
        idx = decoded.find(marker)
        if idx != -1:
            decoded = decoded[:idx]
    return decoded


def register_tools(mcp: FastMCP, client: SerplyClient, settings: Settings) -> None:
    """Register all 8 Serply tools and the account/usage resource on *mcp*."""

    def _headers(proxy_location: str, device: str) -> dict[str, str]:
        return {"X-Proxy-Location": proxy_location, "X-User-Agent": device}

    @mcp.tool()
    async def google_search(
        query: Annotated[str, Field(description="The search query string.", max_length=2048)],
        num: Annotated[int, Field(ge=1, le=100, description="Number of results to return (1–100).")] = 10,
        start: Annotated[int, Field(ge=0, description="Zero-based result offset for pagination.")] = 0,
        proxy_location: Annotated[ProxyLocation, Field(description="Country from which the search is issued.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type — affects ranking and snippets.")] = "desktop",
    ) -> str:
        """Search Google and return organic results via the Serply API.

        Use this tool whenever you need current, real-world information from the web:
        factual lookups, recent events, product research, technical documentation,
        code examples, or anything that benefits from live Google results.

        Returns up to `num` organic results, each with title, URL, and snippet.
        Also includes a direct answer when Google surfaces a featured snippet.

        Use `start` + `num` to paginate: start=0 is page 1, start=10 is page 2, etc.
        Use `proxy_location` to get geo-specific results (e.g. "GB" for UK results).
        """
        try:
            path = SerplyClient.build_query_path("/v1/search", query, num=num, start=start or None)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            results = data.get("results", [])

            lines: list[str] = []
            total = data.get("total")
            header = f'{len(results)} results for "{query}"'
            if total:
                header += f" (est. {total:,} total)"
            lines.append(header)

            answer = data.get("answer") or (data.get("answers") or [None])[0]
            if answer:
                lines.append(f"\nAnswer: {answer}")

            for i, r in enumerate(results, 1):
                title = (r.get("title") or "").strip()
                link = r.get("link", "")
                desc = (r.get("description") or "").strip()
                lines.append(f"\n{i}. {title}")
                lines.append(f"   {link}")
                if desc:
                    lines.append(f"   {desc}")

            if not results:
                lines.append("\nNo results found.")

            return "\n".join(lines)
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def bing_search(
        query: Annotated[str, Field(description="The search query string.", max_length=2048)],
        proxy_location: Annotated[ProxyLocation, Field(description="Country from which the search is issued.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> str:
        """Search Bing and return organic results, ads, and shopping ads via Serply.

        Use this tool as a complement to `google_search` when you want:
        - A second opinion on search results from a different index
        - Shopping/product results — Bing surfaces more shopping ads than Google
        - Bing-specific ranking or freshness signals
        """
        try:
            path = SerplyClient.build_query_path("/v1/b/search", query)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            results = data.get("results", [])
            ads = data.get("ads", [])
            shopping = data.get("shoppingAds", data.get("shopping_ads", []))

            lines: list[str] = [f'{len(results)} results for "{query}"']

            for i, r in enumerate(results, 1):
                title = (r.get("title") or "").strip()
                link = _clean_url(r.get("link", ""))
                desc = (r.get("description") or "").strip()
                lines.append(f"\n{i}. {title}")
                lines.append(f"   {link}")
                if desc:
                    lines.append(f"   {desc}")

            if not results:
                lines.append("\nNo organic results found.")

            if ads:
                lines.append(f"\nAds ({len(ads)}):")
                for ad in ads:
                    title = (ad.get("title") or "").strip()
                    domain = ad.get("displayUrl", "").split("›")[0].strip()
                    content = (ad.get("content") or "").strip()
                    ad_line = f"- {title}"
                    if domain:
                        ad_line += f" ({domain})"
                    if content:
                        ad_line += f" — {content}"
                    lines.append(ad_line)

            if shopping:
                lines.append(f"\nShopping ({len(shopping)}):")
                for item in shopping[:5]:
                    title = (item.get("title") or item.get("name") or "").strip()
                    price = item.get("price", "")
                    lines.append(f"- {title}" + (f" — {price}" if price else ""))

            return "\n".join(lines)
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def google_video_search(
        query: Annotated[str, Field(description="The video search query.", max_length=2048)],
        num: Annotated[int, Field(ge=1, le=100, description="Number of video results.")] = 10,
        proxy_location: Annotated[ProxyLocation, Field(description="Country context for the search.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> str:
        """Search Google Videos and return video results via Serply.

        Use this tool when the user is looking for video content: tutorials,
        product demos, news clips, lectures, or any query where video results
        are more relevant than web pages.

        Results come primarily from YouTube and other indexed video platforms.
        """
        try:
            path = SerplyClient.build_query_path("/v1/video", query, num=num)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            results = data.get("results", [])

            lines: list[str] = [f'{len(results)} video results for "{query}"']

            for i, r in enumerate(results, 1):
                title = (r.get("title") or "").strip()
                link = _clean_url(r.get("link", ""))
                desc = (r.get("description") or "").strip()
                lines.append(f"\n{i}. {title}")
                lines.append(f"   {link}")
                if desc:
                    lines.append(f"   {desc}")

            if not results:
                lines.append("\nNo video results found.")

            return "\n".join(lines)
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def google_news_search(
        query: Annotated[str, Field(description="The news search query.", max_length=2048)],
        ceid: Annotated[str | None, Field(description="Country/language edition filter, e.g. 'US:en' or 'GB:en'. Scopes results to that edition.")] = None,
        proxy_location: Annotated[ProxyLocation, Field(description="Country context for the search.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> str:
        """Search Google News and return news articles via Serply.

        Use this tool when you need recent news coverage of a topic: breaking news,
        company announcements, political events, sports scores, or anything time-sensitive.
        Results are fresher than standard web search — typically hours to days old.

        Set `ceid` to scope to a specific country edition:
        - "US:en" → US English news
        - "GB:en" → UK English news
        - "FR:fr" → French news in French
        """
        try:
            path = SerplyClient.build_query_path("/v1/news", query)
            if ceid:
                path += f"&ceid={urllib.parse.quote_plus(ceid)}"
            data = await client.get(path, extra_headers=_headers(proxy_location, device))

            # Entries are at the top level, not nested inside feed
            entries = data.get("entries", [])
            if not entries:
                feed = data.get("feed", {}) or {}
                entries = feed.get("entries", []) if isinstance(feed, dict) else []

            lines: list[str] = [f'{len(entries)} articles for "{query}"']

            for i, entry in enumerate(entries, 1):
                title = (entry.get("title") or "").strip()
                link = entry.get("link", "")
                published = entry.get("published", "")
                source = (entry.get("source") or {})
                source_name = source.get("title") if isinstance(source, dict) else str(source)

                meta = " · ".join(filter(None, [source_name, published]))
                lines.append(f"\n{i}. {title}")
                if meta:
                    lines.append(f"   {meta}")
                lines.append(f"   {link}")

            if not entries:
                lines.append("\nNo articles found.")

            return "\n".join(lines)
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def google_jobs_search(
        query: Annotated[str, Field(description="Job title, role, or keyword to search for.", max_length=2048)],
        proxy_location: Annotated[ProxyLocation, Field(description="Country for job results. Note: Serply returns North American results only.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> str:
        """Search Google Jobs and return job postings via Serply.

        Use this tool to find job listings from Google's job search index, which
        aggregates postings from LinkedIn, Indeed, company career pages, and other
        job boards.

        IMPORTANT: Serply's Jobs API returns North American results regardless of
        `proxy_location`. Use it for US/Canada job searches.
        """
        try:
            path = SerplyClient.build_query_path("/v1/job/search", query)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            jobs = data.get("jobs", [])

            lines: list[str] = [f'{len(jobs)} job postings for "{query}"']

            for i, job in enumerate(jobs, 1):
                position = (job.get("position") or "").strip()
                link = job.get("link", "")
                desc = job.get("description") or {}
                employer = desc.get("employer", "") if isinstance(desc, dict) else ""
                is_remote = desc.get("is_remote", False) if isinstance(desc, dict) else False
                is_hybrid = desc.get("is_hybrid", False) if isinstance(desc, dict) else False
                perks = desc.get("perks", []) if isinstance(desc, dict) else []
                meta = job.get("metadata") or {}
                location = meta.get("location", "") if isinstance(meta, dict) else ""
                date_posted = meta.get("date_posted", "") if isinstance(meta, dict) else ""
                highlights = job.get("highlights", [])

                title_line = position
                if employer:
                    title_line += f" at {employer}"
                lines.append(f"\n{i}. {title_line}")

                tags: list[str] = []
                if location:
                    tags.append(location)
                if is_remote:
                    tags.append("Remote")
                elif is_hybrid:
                    tags.append("Hybrid")
                if date_posted:
                    tags.append(f"Posted: {date_posted}")
                if tags:
                    lines.append(f"   {' | '.join(tags)}")

                if highlights:
                    lines.append(f"   {' · '.join(highlights[:3])}")
                elif perks:
                    lines.append(f"   {' · '.join(str(p) for p in perks[:3])}")

                lines.append(f"   {link}")

            if not jobs:
                lines.append("\nNo job postings found.")

            return "\n".join(lines)
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def google_scholar_search(
        query: Annotated[str, Field(description="Academic search query — paper title, author name, topic, or DOI fragment.", max_length=2048)],
        num: Annotated[int, Field(ge=1, le=100, description="Number of academic results.")] = 10,
        proxy_location: Annotated[ProxyLocation, Field(description="Country context for the search.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> str:
        """Search Google Scholar and return academic papers and citations via Serply.

        Use this tool for research tasks: finding peer-reviewed papers, locating
        citations, understanding the academic consensus on a topic, or retrieving
        publication metadata.

        Each result includes title, URL, and an abstract snippet with authors and year.
        """
        try:
            path = SerplyClient.build_query_path("/v1/scholar", query, num=num)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            results = data.get("results", [])

            lines: list[str] = [f'{len(results)} academic results for "{query}"']

            for i, r in enumerate(results, 1):
                title = (r.get("title") or "").strip()
                link = r.get("link", "")
                desc = (r.get("description") or "").strip()
                lines.append(f"\n{i}. {title}")
                lines.append(f"   {link}")
                if desc:
                    lines.append(f"   {desc}")

            if not results:
                lines.append("\nNo academic results found.")

            return "\n".join(lines)
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def amazon_product_search(
        query: Annotated[str, Field(description="Product name, brand, or keyword to search Amazon for.", max_length=2048)],
        proxy_location: Annotated[ProxyLocation, Field(description="Country storefront context.")] = "US",
        device: Annotated[Device, Field(description="Emulated device type.")] = "desktop",
    ) -> str:
        """Search Amazon products via Google Shopping (Serply) and return product listings.

        Use this tool when the user wants to:
        - Find product prices and availability on Amazon
        - Compare products by rating and review count
        - Look up ASINs for specific products
        - Identify bestsellers or Prime-eligible items in a category

        Each result includes title, price, rating, review count, ASIN, and direct link.
        """
        try:
            path = SerplyClient.build_query_path("/v1/product/search", query)
            data = await client.get(path, extra_headers=_headers(proxy_location, device))
            # API returns products under either "products" or "results" key
            products = data.get("products") or data.get("results", [])
            ads = data.get("ads", [])

            lines: list[str] = [f'{len(products)} products for "{query}"']

            for i, p in enumerate(products, 1):
                title = (p.get("title") or "").strip()
                price = p.get("price") or ""
                asin = p.get("asin") or ""
                rating = p.get("rating_stars")
                reviews = p.get("review_count")
                link = p.get("link", "")
                prime = p.get("prime", False)
                bestseller = p.get("bestseller", False)
                sponsor = p.get("is_sponsor", False)

                title_line = title
                if price:
                    title_line += f" — {price}"
                lines.append(f"\n{i}. {title_line}")

                meta_parts: list[str] = []
                if rating is not None:
                    star = f"★ {rating:.1f}"
                    if reviews:
                        star += f" ({reviews:,} reviews)"
                    meta_parts.append(star)
                if asin:
                    meta_parts.append(f"ASIN: {asin}")
                if prime:
                    meta_parts.append("Prime")
                if bestseller:
                    meta_parts.append("Bestseller")
                if sponsor:
                    meta_parts.append("Sponsored")
                if meta_parts:
                    lines.append(f"   {' | '.join(meta_parts)}")
                if link:
                    lines.append(f"   {link}")

            if not products:
                lines.append("\nNo products found.")

            if ads:
                lines.append(f"\nSponsored ({len(ads)}):")
                for ad in ads[:3]:
                    ad_title = (ad.get("title") or "").strip()
                    if ad_title:
                        lines.append(f"- {ad_title}")

            return "\n".join(lines)
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def scrape_url(
        url: Annotated[str, Field(description="The full URL to scrape. Must use http:// or https://. Private/internal addresses are blocked.")],
        response_type: Annotated[
            Literal["full", "markdown"],
            Field(description="Output format: 'markdown' strips HTML to clean text (best for LLMs); 'full' returns raw HTML.")
        ] = "markdown",
    ) -> str:
        """Fetch and return the content of any public web page via Serply.

        Use this tool when you have a specific URL and need to read its content —
        for example, after a search returns a link you want to read in full, or when
        the user pastes a URL and asks you to summarize or extract information from it.

        Prefer `response_type="markdown"` for LLM tasks — it strips navigation, ads,
        and boilerplate, leaving clean readable text. Use `response_type="full"` only
        when you need the raw HTML structure.

        Security: private/internal IP ranges (127.x, 10.x, 172.16-31.x, 192.168.x,
        169.254.x) and non-http(s) schemes are blocked to prevent SSRF attacks.
        """
        if settings.block_internal_urls:
            try:
                await check_ssrf(url)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
        try:
            data = await client.post("/v1/request", json={"url": url, "response_type": response_type})
            content = data.get("content", "") or ""
            final_url = data.get("url", url)
            content_hash = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()

            header = f"[Scraped {final_url} — {response_type}, {len(content):,} chars, sha256:{content_hash[:8]}]"
            return f"{header}\n\n{content}"
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
