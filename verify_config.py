from app.services.triage import TriageService
import logging

# Configure logging to see our warnings
logging.basicConfig(level=logging.INFO)

print("--- Test 1: Broken Rules (Should Fallback) ---")
service = TriageService("broken_rules.yaml")
print(f"Rules loaded: {len(service.rules)}")
if len(service.rules) > 0:
    print("✅ SUCCESS: Fell back to default rules.")
else:
    print("❌ FAILURE: Rules are empty.")

print("\n--- Test 2: Missing File (Should Fallback) ---")
service = TriageService("non_existent.yaml")
print(f"Rules loaded: {len(service.rules)}")
if len(service.rules) > 0:
    print("✅ SUCCESS: Fell back to default rules.")
else:
    print("❌ FAILURE: Rules are empty.")
