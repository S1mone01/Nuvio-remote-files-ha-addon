"""
TMDB metadata lookup helpers.

This module provides thin wrappers around the TMDB API for resolving
movies and TV series into normalized metadata used by the application.
"""

import os
import requests
import logging

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"

# Fail fast if TMDB access is not configured
if not TMDB_API_KEY:
    raise RuntimeError("TMDB_API_KEY is not set")


def _tmdb_get(path, params=None):
    """
    Perform a GET request against the TMDB API and return parsed JSON.
    """
    if params is None:
        params = {}

    params["api_key"] = TMDB_API_KEY
    params["language"] = "it-IT"  # Force Italian titles

    try:
        resp = requests.get(
            f"{TMDB_BASE}{path}",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"TMDB request failed: {e}")
        return None


def lookup_movie(title: str, year: int | None = None):
    """
    Lookup a movie by title (and optional year).

    Returns a dict containing IMDb ID, title, year, genres, and poster URL,
    or None if no suitable match is found.
    """

    # 1) Search movie
    search_params = {"query": title}
    if year:
        search_params["year"] = year

    search = _tmdb_get("/search/movie", search_params)

    if not search["results"]:
        return None

    movie = search["results"][0]
    tmdb_id = movie["id"]

    # 2) Fetch details and external IDs
    details = _tmdb_get(f"/movie/{tmdb_id}")
    externals = _tmdb_get(f"/movie/{tmdb_id}/external_ids")

    imdb_id = externals.get("imdb_id")
    if not imdb_id:
        return None

    genres = [g["name"] for g in details.get("genres", [])]

    poster_url = (
        f"https://images.metahub.space/poster/medium/{imdb_id}/img"
        if imdb_id
        else None
    )

    return {
        "imdb_id": imdb_id,
        "title": details.get("title"),
        "year": details.get("release_date", "")[:4],
        "genres": genres,
        "poster_url": poster_url,
    }


def lookup_series(title: str):
    """
    Lookup a TV series by title.

    Returns a dict containing IMDb ID, title, genres, and poster URL,
    or None if no suitable match is found.
    """

    # 1) Search TV series
    search = _tmdb_get("/search/tv", {"query": title})

    if not search["results"]:
        return None

    series = search["results"][0]
    tmdb_id = series["id"]

    # 2) Fetch details and external IDs
    details = _tmdb_get(f"/tv/{tmdb_id}")
    externals = _tmdb_get(f"/tv/{tmdb_id}/external_ids")

    imdb_id = externals.get("imdb_id")
    if not imdb_id:
        return None

    genres = [g["name"] for g in details.get("genres", [])]

    poster_url = (
        f"https://images.metahub.space/poster/medium/{imdb_id}/img"
        if imdb_id
        else None
    )

    return {
        "tmdb_id": tmdb_id,
        "imdb_id": imdb_id,
        "title": details.get("name"),
        "genres": genres,
        "poster_url": poster_url,
    }


def lookup_episode(series_tmdb_id: int, season: int, episode: int):
    """
    Fetch details for a specific episode.
    """
    path = f"/tv/{series_tmdb_id}/season/{season}/episode/{episode}"
    details = _tmdb_get(path)
    if not details:
        return None
    
    return {
        "title": details.get("name"),
        "overview": details.get("overview")
    }
