from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

DEFAULT_TIMEOUT = httpx.Timeout(10.0)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4))
async def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()
