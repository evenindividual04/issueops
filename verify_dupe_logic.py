import asyncio
import logging
from app.services.duplicate_service import DuplicateService
from app.services.github_service import GitHubService
from app.services.extractor import ExtractorService

# Configure logging to see the flow
logging.basicConfig(level=logging.INFO)

class MockGitHub(GitHubService):
    """Mocks GitHub Search to return a guaranteed semantic match."""
    async def search_issues(self, owner, repo, keywords, limit=5):
        print(f"\n🔎 [MockGitHub] Searching for keywords: '{keywords}'")
        # Return a candidate that is functionally identical but worded differently
        return [{
            "number": 404,
            "title": "Application crashes immediately on launch",
            "state": "closed",
            "body_snippet": "Steps to reproduce: 1. Run app. 2. Crash. Error: NullPointerException in boot_loader.py"
        }]

async def main():
    print("--- 🧪 Testing Semantic Duplicate Detection ---")
    
    # 1. Setup Services
    gh = MockGitHub(github_token="fake")
    extractor = ExtractorService() # This will use the REAL Gemini API
    service = DuplicateService(gh, extractor)

    # 2. Define "New Issue" (Semantically identical to Mock candidate #404)
    new_title = "Crash on startup: NPE"
    new_body = "I cannot start the Sentinel app. It throws a NullPointerException in boot_loader.py when I run it."
    
    print(f"📝 New Issue: {new_title}")
    
    # 3. Run Check
    result = await service.check_duplicate("owner", "repo", new_title, new_body, current_issue_id=1000)
    
    # 4. output Results
    print("\n--- 📊 Results ---")
    print(f"Duplicate Found ID: {result.duplicate_number}")
    print(f"Confidence Score: {result.confidence}")
    print(f"Reasoning: {result.reasoning}")
    
    if result.confidence > 0.8:
        print("\n✅ PASSED: Semantic match correctly identified!")
    else:
        print("\n❌ FAILED: LLM failed to match duplicates.")

if __name__ == "__main__":
    asyncio.run(main())
