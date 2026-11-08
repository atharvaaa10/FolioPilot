"""Thin async HTTP client for AMFI NAVAll.txt data."""

import asyncio

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("clients.amfi")

DEFAULT_USER_AGENT = "FolioPilot/1.0 (+https://github.com/atharvaaa10/FolioPilot)"
MAX_NAVALL_BYTES = 25 * 1024 * 1024  # 25 MB cap (real file is ~1.5 MB)


class AmfiFetchError(Exception):
    """Raised when AMFI NAVAll fetch fails or returns invalid content."""


class AmfiClient:
    """Async client to download AMFI NAVAll data with retries, timeout, and size limits."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.url = base_url or settings.AMFI_NAV_URL
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self.max_retries = max_retries or settings.HTTP_MAX_RETRIES
        self._external_client = client

    async def fetch_navall(self) -> str:
        """Download NAVAll.txt with retries and content validation."""
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/plain, */*",
        }

        async def _do_fetch(http_client: httpx.AsyncClient) -> str:
            last_exception: Exception | None = None
            delay = 0.5

            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await http_client.get(
                        self.url,
                        headers=headers,
                        follow_redirects=True,
                    )
                    # Retry on 5xx server errors
                    if response.status_code >= 500:
                        logger.warning(
                            "AMFI server returned 5xx",
                            status_code=response.status_code,
                            attempt=attempt,
                        )
                        if attempt < self.max_retries:
                            await asyncio.sleep(delay)
                            delay *= 2
                            continue
                        response.raise_for_status()

                    response.raise_for_status()

                    # Enforce size limit
                    content_bytes = response.content
                    if len(content_bytes) > MAX_NAVALL_BYTES:
                        raise AmfiFetchError(
                            f"AMFI response exceeded size limit: {len(content_bytes)} bytes "
                            f"> {MAX_NAVALL_BYTES} bytes"
                        )

                    text = response.text

                    # Content validation
                    stripped = text.strip()
                    lower_snippet = stripped[:300].lower()
                    if "<html" in lower_snippet or "<!doctype html" in lower_snippet:
                        raise AmfiFetchError(
                            "AMFI response appears to be HTML rather than text/plain"
                        )

                    if "scheme code;isin" not in lower_snippet:
                        raise AmfiFetchError(
                            "AMFI response is missing expected header 'Scheme Code;ISIN'"
                        )

                    return text

                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    last_exception = exc
                    logger.warning(
                        "AMFI fetch attempt failed",
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(delay)
                        delay *= 2
                    else:
                        break

            raise AmfiFetchError(
                f"Failed to fetch AMFI NAVAll after {self.max_retries} attempts: {last_exception}"
            )

        if self._external_client is not None:
            return await _do_fetch(self._external_client)

        async with httpx.AsyncClient(timeout=self.timeout) as http_client:
            return await _do_fetch(http_client)
