from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProxyLocation(str):
    __slots__ = ()


PROXY_LOCATIONS = ("US", "EU", "CA", "IE", "GB", "FR", "DE", "SE", "IN", "JP", "KR", "SG", "AU", "BR")
Device = Literal["desktop", "mobile"]


# Google Search / Video / Scholar
class SearchResult(BaseModel):
    title: str = ""
    link: str = ""
    description: str = ""


class SearchResponse(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    total: int | None = None
    answer: str | None = None


# Bing Search
class BingResult(BaseModel):
    title: str = ""
    link: str = ""
    description: str = ""


class BingResponse(BaseModel):
    results: list[BingResult] = Field(default_factory=list)
    ads: list[dict[str, Any]] = Field(default_factory=list)
    shopping_ads: list[dict[str, Any]] = Field(default_factory=list)
    location: dict[str, Any] | None = None
    ts: str | None = None


# Google Jobs
class JobDescription(BaseModel):
    employer: str | None = None
    perks: list[str] = Field(default_factory=list)
    is_remote: bool = False
    is_hybrid: bool = False


class JobResult(BaseModel):
    highlights: list[str] = Field(default_factory=list)
    link: str = ""
    position: str = ""
    description: JobDescription = Field(default_factory=JobDescription)
    logo: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobsResponse(BaseModel):
    jobs: list[JobResult] = Field(default_factory=list)
    ts: str | None = None
    device_region: str | None = None
    device_type: str | None = None


# Google News
class NewsEntry(BaseModel):
    title: str = ""
    link: str = ""
    published: str | None = None
    summary: str | None = None
    source: str | None = None


class NewsFeed(BaseModel):
    entries: list[NewsEntry] = Field(default_factory=list)
    title: str | None = None


class NewsResponse(BaseModel):
    feed: NewsFeed = Field(default_factory=NewsFeed)
    entities: list[dict[str, Any]] = Field(default_factory=list)


# Amazon Product Search
class ProductResult(BaseModel):
    link: str = ""
    asin: str | None = None
    title: str = ""
    price: str | None = None
    real_position: int | None = None
    img_url: str | None = None
    rating_stars: float | None = None
    review_count: int | None = None
    extras: dict[str, Any] = Field(default_factory=dict)
    bestseller: bool = False
    prime: bool = False
    is_sponsor: bool = False


class ProductResponse(BaseModel):
    products: list[ProductResult] = Field(default_factory=list)
    ads: list[dict[str, Any]] = Field(default_factory=list)
    ts: str | None = None
    device_type: str | None = None


# URL Scraper
class ScrapeResponse(BaseModel):
    content: str = ""
    url: str = ""
    response_type: Literal["full", "markdown"] = "markdown"
