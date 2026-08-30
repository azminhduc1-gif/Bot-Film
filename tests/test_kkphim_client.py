"""Tests for KKPhim API client retry, timeout, and error handling."""
from __future__ import annotations

import pytest
from aioresponses import aioresponses

from app.providers.kkphim.client import KKPhimClient
from app.providers.kkphim.exceptions import KKPhimAPIError, KKPhimNotFoundError


@pytest.mark.asyncio
async def test_client_retries_on_server_error(kkphim_client: KKPhimClient) -> None:
    with aioresponses() as mocked:
        mocked.get(
            "https://test.kkphim.io/phim/not-found",
            status=500,
        )
        mocked.get(
            "https://test.kkphim.io/phim/not-found",
            status=500,
        )
        mocked.get(
            "https://test.kkphim.io/phim/not-found",
            payload={"status": True, "movie": {"slug": "not-found", "name": "Not Found"}},
            status=200,
        )

        movie = await kkphim_client.get_movie("not-found")
        assert movie.slug == "not-found"
        assert sum(len(reqs) for reqs in mocked.requests.values()) == 3


@pytest.mark.asyncio
async def test_client_raises_not_found(kkphim_client: KKPhimClient) -> None:
    with aioresponses() as mocked:
        mocked.get(
            "https://test.kkphim.io/phim/missing",
            status=404,
        )

        with pytest.raises(KKPhimNotFoundError):
            await kkphim_client.get_movie("missing")


@pytest.mark.asyncio
async def test_client_raises_api_error_after_retries(kkphim_client: KKPhimClient) -> None:
    with aioresponses() as mocked:
        mocked.get(
            "https://test.kkphim.io/phim/bad",
            status=500,
            repeat=True,
        )

        with pytest.raises(KKPhimAPIError):
            await kkphim_client.get_movie("bad")


@pytest.mark.asyncio
async def test_client_search_movie_v1(kkphim_client: KKPhimClient) -> None:
    with aioresponses() as mocked:
        mocked.get(
            "https://test.kkphim.io/v1/api/tim-kiem?keyword=avengers&limit=10&page=1",
            payload={
                "status": "success",
                "data": {
                    "items": [
                        {
                            "_id": "65ab123",
                            "name": "Avengers: Endgame",
                            "slug": "avengers-endgame",
                            "origin_name": "Avengers: Endgame",
                            "thumb_url": "upload/vod/20240101/avengers.jpg",
                            "poster_url": "upload/vod/20240101/avengers-poster.jpg",
                            "year": 2019,
                            "quality": "HD",
                            "lang": "Vietsub",
                        }
                    ],
                    "params": {
                        "pagination": {
                            "totalItems": 1,
                            "totalItemsPerPage": 10,
                            "currentPage": 1,
                            "totalPages": 1,
                        }
                    },
                },
            },
            status=200,
        )

        res = await kkphim_client.search_movie("avengers", page=1, limit=10)
        assert len(res.items) == 1
        assert res.items[0].slug == "avengers-endgame"
        assert res.items[0].thumb_url == "https://phimimg.com/upload/vod/20240101/avengers.jpg"
        assert res.pagination.total_items == 1


@pytest.mark.asyncio
async def test_client_list_genres_and_countries(kkphim_client: KKPhimClient) -> None:
    with aioresponses() as mocked:
        mocked.get(
            "https://test.kkphim.io/the-loai",
            payload={
                "status": "success",
                "data": {
                    "items": [
                        {"_id": "1", "name": "Hành Động", "slug": "hanh-dong"},
                        {"_id": "2", "name": "Kinh Dị", "slug": "kinh-di"},
                    ]
                },
            },
            status=200,
        )
        mocked.get(
            "https://test.kkphim.io/quoc-gia",
            payload={
                "status": "success",
                "data": {
                    "items": [
                        {"_id": "1", "name": "Việt Nam", "slug": "viet-nam"},
                        {"_id": "2", "name": "Âu Mỹ", "slug": "au-my"},
                    ]
                },
            },
            status=200,
        )

        genres = await kkphim_client.list_genres()
        assert len(genres) == 2
        assert genres[0].name == "Hành Động"
        assert genres[0].slug == "hanh-dong"

        countries = await kkphim_client.list_countries()
        assert len(countries) == 2
        assert countries[0].name == "Việt Nam"
