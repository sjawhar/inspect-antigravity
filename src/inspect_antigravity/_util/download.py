import httpx


async def download_file(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.content
