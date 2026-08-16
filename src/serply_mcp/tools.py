"""All Serply MCP tools registered in one place."""
from __future__ import annotations

import hashlib
import urllib.parse
from datetime import UTC, datetime
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

ListingSort = Literal["hot", "new", "top", "rising", "controversial"]
UserSort = Literal["hot", "new", "top", "controversial"]
CommentSort = Literal["confidence", "top", "new", "controversial", "old", "qa"]
TimeWindow = Literal["hour", "day", "week", "month", "year", "all"]

REDDIT_WEB = "https://www.reddit.com"


def _clean_url(url: str) -> str:
    """Decode percent-encoding and strip Bing/Google tracking parameters."""
    decoded = urllib.parse.unquote(url)
    for marker in ("&sa=", "&ved=", "&usg=", "&ntb=", "!&&p="):
        idx = decoded.find(marker)
        if idx != -1:
            decoded = decoded[:idx]
    return decoded


# ── Reddit helpers ────────────────────────────────────────────────────────────

def _strip_prefix(value: str, *prefixes: str) -> str:
    """Accept `r/python`, `/r/python`, `t3_1vfemi1`, … and return the bare name."""
    stripped = value.strip().lstrip("/")
    for prefix in prefixes:
        if stripped.lower().startswith(prefix):
            return stripped[len(prefix):]
    return stripped


def _reddit_path(*segments: str, **params: Any) -> str:
    """Build a /v1/reddit path, percent-encoding each segment as one path part."""
    encoded = "/".join(urllib.parse.quote(s, safe="") for s in segments)
    query = {k: v for k, v in params.items() if v is not None}
    qs = f"?{urllib.parse.urlencode(query)}" if query else ""
    return f"/v1/reddit/{encoded}{qs}"


def _children(payload: Any) -> list[dict[str, Any]]:
    """Pull `data.children` out of a Reddit Listing envelope, defensively."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    children = data.get("children")
    if not isinstance(children, list):
        return []
    return [c for c in children if isinstance(c, dict)]


def _after_cursor(payload: Any) -> str:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and data.get("after"):
            return str(data["after"])
    return ""


def _fmt_epoch(value: Any) -> str:
    """Reddit timestamps are float epoch seconds; render them as UTC."""
    try:
        return datetime.fromtimestamp(float(value), tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _squash(text: str, limit: int) -> str:
    """Collapse whitespace and truncate — Reddit selftext runs to thousands of chars."""
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _count(value: Any) -> str:
    return f"{value:,}" if isinstance(value, int) else str(value or "")


def _permalink(data: dict[str, Any]) -> str:
    permalink = data.get("permalink")
    if permalink:
        return f"{REDDIT_WEB}{permalink}"
    return str(data.get("url") or "")


def _render_post(data: dict[str, Any], *, index: int | None = None, body_limit: int = 400) -> list[str]:
    """One t3 (link/self post) record as titled lines with an indented body."""
    title = str(data.get("title") or "").strip()
    lines = [f"{index}. {title}" if index is not None else title]

    meta: list[str] = []
    subreddit = data.get("subreddit_name_prefixed") or (
        f"r/{data['subreddit']}" if data.get("subreddit") else ""
    )
    if subreddit:
        meta.append(str(subreddit))
    if data.get("author"):
        meta.append(f"u/{data['author']}")
    if data.get("score") is not None:
        meta.append(f"▲ {_count(data.get('score'))}")
    if data.get("num_comments") is not None:
        meta.append(f"{_count(data.get('num_comments'))} comments")
    created = _fmt_epoch(data.get("created_utc"))
    if created:
        meta.append(created)
    if data.get("link_flair_text"):
        meta.append(str(data["link_flair_text"]))
    if data.get("over_18"):
        meta.append("NSFW")
    if data.get("stickied"):
        meta.append("pinned")
    if meta:
        lines.append(f"   {' · '.join(meta)}")

    permalink = _permalink(data)
    if permalink:
        lines.append(f"   {permalink}")

    post_id = data.get("id")
    if post_id:
        lines.append(f"   id: {post_id}")

    # Link posts point somewhere off Reddit; self posts point at themselves.
    external = str(data.get("url") or "")
    if external and not data.get("is_self") and external not in permalink:
        lines.append(f"   links to: {external}")

    body = _squash(str(data.get("selftext") or ""), body_limit)
    if body:
        lines.append(f"   {body}")

    return lines


def _render_comment(child: dict[str, Any], depth: int, max_depth: int, out: list[str]) -> None:
    """Append one comment and its replies, indented by depth."""
    data = child.get("data")
    if not isinstance(data, dict):
        return
    indent = "  " * depth

    if child.get("kind") == "more":
        more = data.get("count") or len(data.get("children") or [])
        if more:
            out.append(f"{indent}… {more} more replies not loaded")
        return
    if child.get("kind") != "t1":
        return

    header = f"{indent}u/{data.get('author') or '[deleted]'}"
    bits: list[str] = []
    if data.get("score") is not None:
        bits.append(f"▲ {_count(data.get('score'))}")
    created = _fmt_epoch(data.get("created_utc"))
    if created:
        bits.append(created)
    if data.get("is_submitter"):
        bits.append("OP")
    if data.get("stickied"):
        bits.append("pinned")
    if bits:
        header += f" · {' · '.join(bits)}"
    out.append(header)

    body = _squash(str(data.get("body") or ""), 700)
    if body:
        out.append(f"{indent}  {body}")

    replies = data.get("replies")
    if depth >= max_depth or not isinstance(replies, dict):
        return
    for reply in _children(replies):
        _render_comment(reply, depth + 1, max_depth, out)


def register_tools(mcp: FastMCP, client: SerplyClient, settings: Settings) -> None:
    """Register all 13 Serply tools and the account/usage resource on *mcp*."""

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
    async def google_maps_search(
        query: Annotated[
            str,
            Field(
                description="Place, business, category, or location to search.",
                max_length=2048,
            ),
        ],
        num: Annotated[
            int,
            Field(ge=1, le=200, description="Number of places to request (1–200)."),
        ] = 20,
        hl: Annotated[
            str,
            Field(
                min_length=2,
                max_length=8,
                pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?$",
                description="Google interface language code, such as 'en' or 'en-US'.",
            ),
        ] = "en",
        gl: Annotated[
            str,
            Field(
                min_length=2,
                max_length=2,
                pattern=r"^[A-Za-z]{2}$",
                description="Two-letter country code, such as 'us' or 'gb'.",
            ),
        ] = "us",
    ) -> dict[str, Any]:
        """Search Google Maps and return structured local-business places via Serply.

        Use this for local and commercial intent: businesses, services, venues,
        addresses, ratings, review counts, phone numbers, hours, and direct websites.
        This endpoint uses Serply's direct non-JavaScript Maps transport, so it does
        not accept browser-device or proxy-location controls.

        The response includes `places`, `result_count`, query metadata, and for each
        place the available Google IDs, Maps URL, website, address, coordinates,
        rating, reviews, categories, phone, timezone, thumbnail, and opening hours.

        Put the location in the query, for example `coffee shops in 60601`,
        `coffee shops in Chicago, IL`, or `coffee shops near 41.8781,-87.6298`.
        Coordinates are natural-language query context; separate latitude,
        longitude, radius, and pagination arguments are not currently available.
        `gl` must be a two-letter country code such as `us`, `gb`, or `ca`.
        """
        try:
            encoded_query = urllib.parse.quote(query, safe="")
            query_string = urllib.parse.urlencode(
                {"num": num, "hl": hl, "gl": gl.lower()}
            )
            data = await client.get(
                f"/v1/maps/search/{encoded_query}?{query_string}"
            )
            places = data.get("places", [])
            return {
                **data,
                "summary": f"Found {len(places)} Google Maps places for '{query}'",
            }
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
            # /v1/request has two response shapes. response_type="full" returns
            # JSON with the HTML under "data"; response_type="markdown" returns
            # the text raw, which SerplyClient wraps into "content". Reading
            # only "content" made "full" return 0 chars with no error at all.
            content = data.get("content") or data.get("data") or ""
            final_url = data.get("url", url)
            content_hash = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()

            header = f"[Scraped {final_url} — {response_type}, {len(content):,} chars, sha256:{content_hash[:8]}]"
            return f"{header}\n\n{content}"
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    # ── reddit ────────────────────────────────────────────────────────────────

    @mcp.tool()
    async def reddit_subreddit_posts(
        subreddit: Annotated[
            str,
            Field(
                pattern=r"^(?:/?r/)?[A-Za-z0-9][A-Za-z0-9_]{1,20}$",
                description="Subreddit name, with or without the 'r/' prefix — e.g. 'python' or 'r/AskReddit'.",
            ),
        ],
        limit: Annotated[int, Field(ge=1, le=100, description="Number of posts to return (1–100).")] = 25,
        sort: Annotated[ListingSort, Field(description="Listing order.")] = "hot",
        t: Annotated[
            TimeWindow | None,
            Field(description="Time window — only meaningful for sort='top' or 'controversial'. Defaults to all-time."),
        ] = None,
        after: Annotated[
            str | None,
            Field(
                max_length=64,
                pattern=r"^[A-Za-z0-9_]+$",
                description="Pagination cursor — pass the 'Next page' value from a previous call.",
            ),
        ] = None,
    ) -> str:
        """List posts from a subreddit via the Serply Reddit API.

        Use this to see what a community is currently discussing: trending posts in
        r/python, top-of-the-week in r/MachineLearning, new posts in a niche subreddit,
        or the general sentiment around a product or topic.

        Each post includes title, author, score, comment count, timestamp, permalink,
        post id, and a snippet of the body. Feed a post id to `reddit_post_comments`
        to read the discussion.

        Use `sort="top"` with `t="week"`/`"month"`/`"year"` for the best-of over a period.
        Paginate by passing the returned cursor back as `after`.
        """
        try:
            name = _strip_prefix(subreddit, "r/")
            path = _reddit_path("subreddit", name, limit=limit, sort=sort, t=t, after=after)
            data = await client.get(path)
            children = _children(data)

            window = f", t={t}" if t else ""
            lines: list[str] = [f"{len(children)} posts from r/{name} (sort={sort}{window})"]

            rank = 0
            for child in children:
                post = child.get("data")
                if child.get("kind") != "t3" or not isinstance(post, dict):
                    continue
                rank += 1
                lines.append("")
                lines.extend(_render_post(post, index=rank))

            if not rank:
                lines.append("\nNo posts found. The subreddit may be empty, private, or banned.")

            cursor = _after_cursor(data)
            if cursor:
                lines.append(f"\nNext page: after={cursor}")

            return "\n".join(lines)
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def reddit_subreddit_about(
        subreddit: Annotated[
            str,
            Field(
                pattern=r"^(?:/?r/)?[A-Za-z0-9][A-Za-z0-9_]{1,20}$",
                description="Subreddit name, with or without the 'r/' prefix.",
            ),
        ],
    ) -> str:
        """Get a subreddit's metadata (subscribers, description, rules blurb) via Serply.

        Use this to size up a community before or after reading its posts: how many
        subscribers it has, how many people are online, when it was created, whether
        it is public/restricted/private, and what it says it is about.

        Takes no listing options — it describes the subreddit itself, not its posts.
        """
        try:
            name = _strip_prefix(subreddit, "r/")
            data = await client.get(_reddit_path("subreddit", name, "about"))
            about = data.get("data")
            if not isinstance(about, dict):
                return f"No metadata returned for r/{name}."

            display = about.get("display_name_prefixed") or f"r/{name}"
            title = str(about.get("title") or "").strip()
            lines: list[str] = [f"{display}" + (f" — {title}" if title else "")]

            meta: list[str] = []
            if about.get("subscribers") is not None:
                meta.append(f"{_count(about.get('subscribers'))} subscribers")
            if about.get("active_user_count") is not None:
                meta.append(f"{_count(about.get('active_user_count'))} online")
            created = _fmt_epoch(about.get("created_utc"))
            if created:
                meta.append(f"created {created}")
            if about.get("subreddit_type"):
                meta.append(str(about["subreddit_type"]))
            if about.get("lang"):
                meta.append(str(about["lang"]))
            if about.get("over18"):
                meta.append("NSFW")
            if about.get("quarantine"):
                meta.append("quarantined")
            if meta:
                lines.append(" · ".join(meta))

            url = about.get("url")
            if url:
                lines.append(f"{REDDIT_WEB}{url}")

            public_description = _squash(str(about.get("public_description") or ""), 600)
            if public_description:
                lines.append(f"\n{public_description}")

            description = _squash(str(about.get("description") or ""), 1500)
            if description and description != public_description:
                lines.append(f"\nSidebar: {description}")

            return "\n".join(lines)
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def reddit_user_posts(
        username: Annotated[
            str,
            Field(
                pattern=r"^(?:/?u/)?[A-Za-z0-9][A-Za-z0-9_-]{1,19}$",
                description="Reddit account name, with or without the 'u/' prefix — e.g. 'spez'.",
            ),
        ],
        limit: Annotated[int, Field(ge=1, le=100, description="Number of items to return (1–100).")] = 25,
        sort: Annotated[UserSort, Field(description="Ordering of the user's history.")] = "new",
        t: Annotated[
            TimeWindow | None,
            Field(description="Time window — only meaningful for sort='top' or 'controversial'."),
        ] = None,
        after: Annotated[
            str | None,
            Field(
                max_length=64,
                pattern=r"^[A-Za-z0-9_]+$",
                description="Pagination cursor from a previous call.",
            ),
        ] = None,
    ) -> str:
        """Fetch a Reddit user's post and comment history via Serply.

        Use this to understand who someone is on Reddit: what they post about, which
        communities they are active in, and what they have said recently. Useful for
        vetting a source, following a domain expert, or tracing a claim back to context.

        Returns both submissions (t3) and comments (t1) in one timeline, newest first
        by default. Comments show the thread they were left on.
        """
        try:
            name = _strip_prefix(username, "u/")
            path = _reddit_path("user", name, limit=limit, sort=sort, t=t, after=after)
            data = await client.get(path)
            children = _children(data)

            window = f", t={t}" if t else ""
            lines: list[str] = [f"{len(children)} items from u/{name} (sort={sort}{window})"]

            rank = 0
            for child in children:
                item = child.get("data")
                if not isinstance(item, dict):
                    continue
                kind = child.get("kind")
                if kind == "t3":
                    rank += 1
                    lines.append("")
                    lines.extend(_render_post(item, index=rank))
                elif kind == "t1":
                    rank += 1
                    lines.append("")
                    link_title = str(item.get("link_title") or "").strip()
                    subreddit = item.get("subreddit_name_prefixed") or (
                        f"r/{item['subreddit']}" if item.get("subreddit") else ""
                    )
                    lines.append(f"{rank}. Comment on: {link_title or '(unknown thread)'}")

                    meta: list[str] = [str(subreddit)] if subreddit else []
                    if item.get("score") is not None:
                        meta.append(f"▲ {_count(item.get('score'))}")
                    created = _fmt_epoch(item.get("created_utc"))
                    if created:
                        meta.append(created)
                    if meta:
                        lines.append(f"   {' · '.join(meta)}")
                    permalink = _permalink(item)
                    if permalink:
                        lines.append(f"   {permalink}")
                    body = _squash(str(item.get("body") or ""), 400)
                    if body:
                        lines.append(f"   {body}")

            if not rank:
                lines.append("\nNo activity found. The account may be suspended, deleted, or empty.")

            cursor = _after_cursor(data)
            if cursor:
                lines.append(f"\nNext page: after={cursor}")

            return "\n".join(lines)
        except SerplyError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def reddit_post_comments(
        post_id: Annotated[
            str,
            Field(
                pattern=r"^(?:t3_)?[A-Za-z0-9]{4,12}$",
                description="Reddit post id from the URL — e.g. '1vfemi1' in reddit.com/r/Python/comments/1vfemi1/…. The 't3_' prefix is accepted.",
            ),
        ],
        sort: Annotated[CommentSort, Field(description="Comment ordering. 'confidence' is Reddit's default 'best'.")] = "confidence",
        max_depth: Annotated[int, Field(ge=0, le=10, description="How many levels of nested replies to render.")] = 3,
    ) -> str:
        """Read the comment thread on a Reddit post via Serply.

        Use this after `reddit_subreddit_posts`, `reddit_user_posts`, or a web search
        turns up a Reddit thread worth reading: it returns the post itself plus its
        comment tree, so you can see what people actually said rather than just the title.

        Nested replies are indented; branches Reddit did not inline are marked as
        "more replies not loaded". Sorting accepts Reddit's own values — 'confidence'
        (best), 'top', 'new', 'controversial', 'old', 'qa'.
        """
        try:
            ident = _strip_prefix(post_id, "t3_")
            data = await client.get(_reddit_path("comments", ident, sort=sort))

            # Reddit answers /comments/{id} with [post listing, comment
            # listing], which the API wraps as {"cached", "data"};
            # SerplyClient normalises both under "listings". Sort children by
            # kind instead of trusting the order, so a single-listing response
            # (or a reordered one) still renders.
            listings = data.get("listings")
            if not isinstance(listings, list):
                listings = [data]

            posts: list[dict[str, Any]] = []
            comments: list[dict[str, Any]] = []
            for listing in listings:
                for child in _children(listing):
                    if child.get("kind") == "t3":
                        posts.append(child)
                    else:
                        comments.append(child)

            lines: list[str] = []
            if posts:
                post = posts[0].get("data")
                if isinstance(post, dict):
                    lines.extend(_render_post(post, body_limit=2000))
                    lines.append("")

            rendered: list[str] = []
            for child in comments:
                _render_comment(child, 0, max_depth, rendered)
                rendered.append("")

            if rendered:
                top_level = sum(1 for c in comments if c.get("kind") == "t1")
                lines.append(f"Comments ({top_level} top-level, sort={sort}):")
                lines.append("")
                lines.extend(rendered)
            else:
                lines.append("No comments on this post.")

            return "\n".join(lines).rstrip()
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
