import asyncio
import os
from dotenv import load_dotenv
from app.services.extractor import ExtractorService

# Explicitly load .env
load_dotenv()

async def main():
    print("--- Verifying Phase 1: Extractor Service ---")
    
    # Check Key
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ Error: GEMINI_API_KEY not found in env")
        return

    try:
        extractor = ExtractorService()
        
        with open("data/examples/crash_issue.txt", "r") as f:
            text = f.read()
            
        print(f"Input Text Length: {len(text)} chars")
        print("Extracting metadata...")
        
        metadata = await extractor.extract(text)
        
        print("\n✅ Extraction Success!")
        print(metadata.model_dump_json(indent=2))
        
        # Validation Checks for this specific fixture
        assert metadata.is_crash is True, "Failed to detect crash"
        assert metadata.has_logs is True, "Failed to detect logs"
        assert metadata.operating_system == "linux", "Failed to map 'Ubuntu' to 'linux'"
        
        print("\n✅ All Logic Checks Passed")

    except Exception as e:
        print(f"\n❌ FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(main())
