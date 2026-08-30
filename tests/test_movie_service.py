"""Tests for movie search service and cache integration."""
from __future__ import annotations

import pytest
from aioresponses import aioresponses

from app.providers.kkphim.models import CategoryItem, CountryItem, Movie, MovieServer
from app.services.movie_service import MovieService


@pytest.mark.asyncio
async def test_search_uses_cache_on_second_call(movie_service: MovieService) -> None:
    query = "Avengers"
    with aioresponses() as mocked:
        mocked.get(
            "https://test.kkphim.io/v1/api/tim-kiem?keyword=avengers&limit=10&page=1",
            payload={
                "status": "success",
                "data": {
                    "items": [
                        {
                            "_id": "65ab123",
                            "slug": "avengers-endgame",
                            "name": "Avengers: Endgame",
                            "year": 2019,
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
            repeat=True,
        )

        result1 = await movie_service.search(query)
        assert len(result1.items) == 1
        assert result1.items[0].slug == "avengers-endgame"

        # Second call should hit cache and not trigger another HTTP request.
        result2 = await movie_service.search(query)
        assert result2.items[0].slug == "avengers-endgame"


@pytest.mark.asyncio
async def test_get_detail_normalizes_movie(movie_service: MovieService) -> None:
    with aioresponses() as mocked:
        mocked.get(
            "https://test.kkphim.io/phim/inception",
            payload={
                "status": True,
                "msg": "",
                "movie": {
                    "_id": "inc123",
                    "slug": "inception",
                    "name": "Inception",
                    "year": 2010,
                    "content": "<p>A thief who steals corporate secrets...</p>",
                    "thumb_url": "https://phimimg.com/upload/vod/20240101/inception.jpg",
                    "poster_url": "https://phimimg.com/upload/vod/20240101/inception-poster.jpg",
                    "category": [{"id": "1", "name": "Khoa Học", "slug": "khoa-hoc"}],
                    "country": [{"id": "2", "name": "Âu Mỹ", "slug": "au-my"}],
                },
                "episodes": [
                    {
                        "server_name": "Vietsub #1",
                        "server_data": [
                            {
                                "name": "Full",
                                "slug": "full",
                                "filename": "Inception Full Vietsub",
                                "link_embed": "https://player.phimapi.com/player/?url=https://example.com/inception.m3u8",
                                "link_m3u8": "https://example.com/inception.m3u8",
                            }
                        ],
                    }
                ],
            },
            status=200,
        )

        movie = await movie_service.get_detail("inception")
        assert isinstance(movie, Movie)
        assert movie.slug == "inception"
        assert len(movie.servers) == 1
        assert isinstance(movie.servers[0], MovieServer)
        assert movie.servers[0].name == "Vietsub #1"
        assert len(movie.servers[0].episodes) == 1
        assert movie.servers[0].episodes[0].link_m3u8 == "https://example.com/inception.m3u8"
        assert "Khoa Học" in movie.genres
        assert "Âu Mỹ" in movie.countries


@pytest.mark.asyncio
async def test_get_genres_and_countries_caching(movie_service: MovieService) -> None:
    with aioresponses() as mocked:
        mocked.get(
            "https://test.kkphim.io/the-loai",
            payload={
                "status": "success",
                "data": {
                    "items": [
                        {"_id": "1", "name": "Hành Động", "slug": "hanh-dong"},
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
                    ]
                },
            },
            status=200,
        )

        genres = await movie_service.get_genres()
        assert len(genres) == 1
        assert isinstance(genres[0], CategoryItem)

        # Second call should use cache
        genres_cached = await movie_service.get_genres()
        assert len(genres_cached) == 1

        countries = await movie_service.get_countries()
        assert len(countries) == 1
        assert isinstance(countries[0], CountryItem)
