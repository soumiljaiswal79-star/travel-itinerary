import time
import logging
from urllib.parse import urlparse

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)
UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_CACHE_SECONDS = 3600
IMAGE_NEGATIVE_CACHE_SECONDS = 300
IMAGE_CACHE_MAX_ENTRIES = 128
_image_cache: dict[str, tuple[float, tuple[bytes, str] | None]] = {}


async def search_image(settings: Settings, query: str) -> tuple[bytes, str] | None:
    if not settings.unsplash_access_key:
        return None
    cache_key = query.strip().casefold()
    cached = _image_cache.get(cache_key)
    cache_ttl = IMAGE_CACHE_SECONDS if cached and cached[1] is not None else IMAGE_NEGATIVE_CACHE_SECONDS
    if cached and time.monotonic() - cached[0] < cache_ttl:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(
                UNSPLASH_SEARCH_URL,
                params={"query": query, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {settings.unsplash_access_key}"},
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                _cache_image(cache_key, None)
                return None
            image_url = results[0]["urls"]["regular"]
            if urlparse(image_url).hostname != "images.unsplash.com":
                logger.warning("Unsplash returned an unexpected image host")
                _cache_image(cache_key, None)
                return None
            async with client.stream("GET", image_url) as image_response:
                image_response.raise_for_status()
                content_type = image_response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    _cache_image(cache_key, None)
                    return None
                data = bytearray()
                async for chunk in image_response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        logger.warning("Unsplash image exceeded the response size limit")
                        _cache_image(cache_key, None)
                        return None
                result = (bytes(data), content_type.split(";")[0])
                _cache_image(cache_key, result)
                return result
    except (httpx.HTTPError, KeyError, ValueError):
        logger.warning("Unsplash image lookup failed for query %r", query, exc_info=True)
        _cache_image(cache_key, None)
        return None


def _cache_image(query: str, result: tuple[bytes, str] | None) -> None:
    if len(_image_cache) >= IMAGE_CACHE_MAX_ENTRIES:
        _image_cache.pop(next(iter(_image_cache)))
    _image_cache[query] = (time.monotonic(), result)
