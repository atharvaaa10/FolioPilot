"""Thin async HTTP client for mfapi.in historical NAV data."""

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("clients.mfapi")

DEFAULT_USER_AGENT = "FolioPilot/1.0 (+https://github.com/atharvaaa10/FolioPilot)"
MAX_MFAPI_BYTES = 10 * 1024 * 1024  # 10 MB cap


class MfapiFetchError(Exception):
    """Raised when mfapi fetch fails or returns invalid response."""


class MfapiClient:
    """Async client to download fund history from mfapi.in with retries and timeout."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.MFAPI_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self.max_retries = max_retries or settings.HTTP_MAX_RETRIES
        self._external_client = client

    async def fetch_scheme_history(self, scheme_code: int) -> dict[str, Any]:
        """Fetch historical NAV JSON for given scheme_code."""
        url = f"{self.base_url}/mf/{scheme_code}"
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
        }

        async def _do_fetch(http_client: httpx.AsyncClient) -> dict[str, Any]:
            last_exception: Exception | None = None
            delay = 0.5

            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await http_client.get(
                        url,
                        headers=headers,
                        follow_redirects=True,
                    )
                    # Retry on 5xx server errors
                    if response.status_code >= 500:
                        logger.warning(
                            "mfapi server returned 5xx",
                            scheme_code=scheme_code,
                            status_code=response.status_code,
                            attempt=attempt,
                        )
                        if attempt < self.max_retries:
                            await asyncio.sleep(delay)
                            delay *= 2
                            continue
                        response.raise_for_status()

                    response.raise_for_status()

                    content_bytes = response.content
                    if len(content_bytes) > MAX_MFAPI_BYTES:
                        raise MfapiFetchError(
                            f"mfapi response exceeded size limit: {len(content_bytes)} bytes "
                            f"> {MAX_MFAPI_BYTES} bytes"
                        )

                    data = response.json()
                    if not isinstance(data, dict):
                        raise MfapiFetchError("mfapi response is not a valid JSON object")

                    return data

                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    last_exception = exc
                    logger.warning(
                        "mfapi fetch attempt failed",
                        scheme_code=scheme_code,
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(delay)
                        delay *= 2
                    else:
                        break

            raise MfapiFetchError(
                f"Failed to fetch mfapi history for scheme {scheme_code} "
                f"after {self.max_retries} attempts: {last_exception}"
            )

        if self._external_client is not None:
            return await _do_fetch(self._external_client)

        async with httpx.AsyncClient(timeout=self.timeout) as http_client:
            return await _do_fetch(http_client)
