from collections.abc import AsyncGenerator

import httpx


class BaseAPIClient:
    def __init__(self, base_url: str, timeout: int = 300):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def stream_post(
        self, path: str, payload: dict
    ) -> AsyncGenerator[str, None]:
        """POST to path and yield raw SSE lines from the response stream."""
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    yield line
