import asyncio
import httpx
from app.services.github_service import GitHubService
from app.core.config import settings

async def main():
    print(f"Token: {settings.GITHUB_TOKEN[:4]}... (Len: {len(settings.GITHUB_TOKEN)})")
    gh = GitHubService(github_token=settings.GITHUB_TOKEN)
    url = "https://api.github.com/repos/fastapi/fastapi/issues"
    
    print(f"Fetching from {url}...")
    headers = gh._build_headers()
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params={"state": "open", "per_page": 5})
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Items: {len(data)}")
            for item in data:
                print(f"- {item.get('title')} (PR: {'pull_request' in item})")
        else:
            print(resp.text)

if __name__ == "__main__":
    asyncio.run(main())
