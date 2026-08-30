"""Pydantic models for KKPhim API responses.

Mapped to the official KKPhim API documentation:
https://kkphim2.com/api-document (Base URL: https://phimapi.com)
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NamedItem(BaseModel):
    """Generic category/country item containing id, name, slug."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str | None = Field(default=None, alias="_id")
    name: str = ""
    slug: str = ""

    @classmethod
    def from_string(cls, val: str) -> NamedItem:
        return cls(id=None, name=val, slug=val.lower().replace(" ", "-"))


class CategoryItem(NamedItem):
    """Movie category/genre."""


class CountryItem(NamedItem):
    """Movie country."""


class YearItem(BaseModel):
    """Release year item."""

    model_config = ConfigDict(extra="ignore")
    year: int


class TMDBInfo(BaseModel):
    """TheMovieDB metadata."""

    model_config = ConfigDict(extra="ignore")

    id: str | int | None = None
    type: str | None = None
    season: int | None = None
    vote_average: float | None = 0.0
    vote_count: int | None = 0


class IMDBInfo(BaseModel):
    """IMDB metadata."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    vote_average: float | None = 0.0
    vote_count: int | None = 0


class MovieEpisode(BaseModel):
    """A single playable episode."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(default="", description="Episode display name, e.g. '01', 'Full'")
    slug: str = Field(default="", description="Episode slug")
    filename: str | None = Field(default=None, description="Full episode title/filename")
    link_embed: str | None = Field(default=None, description="Embed player URL")
    link_m3u8: str | None = Field(default=None, description="HLS m3u8 stream URL")


class MovieServer(BaseModel):
    """A streaming server containing episodes."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(default="Server #1", alias="server_name", description="Server display name")
    episodes: list[MovieEpisode] = Field(
        default_factory=list,
        alias="server_data",
        description="Episodes available on this server",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_server(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "server_name" in data and "name" not in data:
                data["name"] = data["server_name"]
            if "server_data" in data and "episodes" not in data:
                data["episodes"] = data["server_data"]
        return data


class Movie(BaseModel):
    """Full movie details."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str | None = Field(default=None, alias="_id")
    name: str = Field(..., description="Movie title")
    slug: str = Field(..., description="Unique movie slug")
    origin_name: str | None = Field(default=None, description="Original title")
    content: str | None = Field(default=None, description="Plot summary")
    type: str | None = Field(default=None, description="Movie type: single, series, hoathinh, tvshows...")
    status: str | None = Field(default=None, description="ongoing / completed")
    thumb_url: str | None = Field(default=None, description="Thumbnail image URL")
    poster_url: str | None = Field(default=None, description="Poster image URL")
    is_copyright: bool | None = None
    sub_docquyen: bool | None = None
    chieurap: bool | None = None
    trailer_url: str | None = None
    time: str | None = Field(default=None, description="Duration")
    episode_current: str | None = None
    episode_total: str | int | None = None
    quality: str | None = None
    lang: str | None = None
    notify: str | None = None
    showtimes: str | None = None
    year: int | None = Field(default=None, alias="publish_year")
    view: int | None = 0
    actor: list[str] = Field(default_factory=list, alias="actors")
    director: list[str] = Field(default_factory=list, alias="directors")
    category: list[CategoryItem] = Field(default_factory=list, alias="genres")
    country: list[CountryItem] = Field(default_factory=list, alias="countries")
    tmdb: TMDBInfo | None = None
    imdb: IMDBInfo | None = None
    servers: list[MovieServer] = Field(default_factory=list, alias="episodes")

    @model_validator(mode="before")
    @classmethod
    def _normalize_movie_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # year / publish_year fallback
            if "year" in data and "publish_year" not in data:
                data["publish_year"] = data["year"]
            elif "publish_year" in data and "year" not in data:
                data["year"] = data["publish_year"]

            # actor / actors
            if "actor" in data and "actors" not in data:
                data["actors"] = data["actor"]
            # director / directors
            if "director" in data and "directors" not in data:
                data["directors"] = data["director"]

            # category / genres conversion
            raw_cats = data.get("category") or data.get("genres") or []
            if raw_cats and isinstance(raw_cats, list):
                norm_cats = []
                for c in raw_cats:
                    if isinstance(c, str):
                        norm_cats.append({"name": c, "slug": c.lower().replace(" ", "-")})
                    elif isinstance(c, dict):
                        norm_cats.append(c)
                data["category"] = norm_cats
                data["genres"] = norm_cats

            # country / countries conversion
            raw_countries = data.get("country") or data.get("countries") or []
            if raw_countries and isinstance(raw_countries, list):
                norm_countries = []
                for c in raw_countries:
                    if isinstance(c, str):
                        norm_countries.append({"name": c, "slug": c.lower().replace(" ", "-")})
                    elif isinstance(c, dict):
                        norm_countries.append(c)
                data["country"] = norm_countries
                data["countries"] = norm_countries

            # servers / episodes
            if "episodes" in data and "servers" not in data:
                data["servers"] = data["episodes"]
        return data

    @property
    def publish_year(self) -> int | None:
        return self.year

    @property
    def genres(self) -> list[str]:
        return [c.name for c in self.category if c.name]

    @property
    def countries(self) -> list[str]:
        return [c.name for c in self.country if c.name]

    @property
    def actors(self) -> list[str]:
        return self.actor

    @property
    def directors(self) -> list[str]:
        return self.director


class MovieSearchResult(BaseModel):
    """Lightweight movie item returned from search/list endpoints."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str | None = Field(default=None, alias="_id")
    slug: str
    name: str
    origin_name: str | None = None
    thumb_url: str | None = None
    poster_url: str | None = None
    year: int | None = Field(default=None, alias="publish_year")
    type: str | None = None
    quality: str | None = None
    lang: str | None = None
    episode_current: str | None = None
    time: str | None = None
    category: list[CategoryItem] = Field(default_factory=list, alias="genres")
    country: list[CountryItem] = Field(default_factory=list, alias="countries")
    tmdb: TMDBInfo | None = None
    imdb: IMDBInfo | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_search_result(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "year" in data and "publish_year" not in data:
                data["publish_year"] = data["year"]
            elif "publish_year" in data and "year" not in data:
                data["year"] = data["publish_year"]

            raw_cats = data.get("category") or data.get("genres") or []
            if raw_cats and isinstance(raw_cats, list):
                norm_cats = []
                for c in raw_cats:
                    if isinstance(c, str):
                        norm_cats.append({"name": c, "slug": c.lower().replace(" ", "-")})
                    elif isinstance(c, dict):
                        norm_cats.append(c)
                data["category"] = norm_cats
                data["genres"] = norm_cats

            raw_countries = data.get("country") or data.get("countries") or []
            if raw_countries and isinstance(raw_countries, list):
                norm_countries = []
                for c in raw_countries:
                    if isinstance(c, str):
                        norm_countries.append({"name": c, "slug": c.lower().replace(" ", "-")})
                    elif isinstance(c, dict):
                        norm_countries.append(c)
                data["country"] = norm_countries
                data["countries"] = norm_countries
        return data

    @property
    def publish_year(self) -> int | None:
        return self.year

    @property
    def genres(self) -> list[str]:
        return [c.name for c in self.category if c.name]

    @property
    def countries(self) -> list[str]:
        return [c.name for c in self.country if c.name]


class Pagination(BaseModel):
    """Pagination metadata."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    current_page: int = Field(default=1, alias="currentPage")
    total_pages: int = Field(default=1, alias="totalPages")
    total_items: int = Field(default=0, alias="totalItems")
    items_per_page: int = Field(default=10, alias="totalItemsPerPage")


class PaginatedResult(BaseModel):
    """Paginated list of movies."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    items: list[MovieSearchResult] = Field(default_factory=list)
    pagination: Pagination = Field(default_factory=Pagination)


class MovieDetailResponse(BaseModel):
    """Wrapper returned by movie detail endpoints."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    status: bool | str | None = None
    msg: str | None = None
    message: str | None = None
    movie: Movie | None = None
    episodes: list[MovieServer] = Field(default_factory=list)
    data: dict[str, Any] | None = None
