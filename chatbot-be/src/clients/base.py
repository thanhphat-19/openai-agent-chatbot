from collections.abc import AsyncGenerator

import httpx


class BaseAPIClient:
    def __init__(self, base_url: str, timeout: int = 300):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def stream_post(
        self, path: str, payload: dict
    ) -> AsyncGenerator[str, None]:
        """POST to path and yield raw SSE lines from the response stream."""
        url = f"{self._base_url}{path}"
        client = self._get_client()
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                yield line
