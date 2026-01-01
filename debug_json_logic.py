from json_logic import jsonLogic
import yaml

rule_yaml = """
and:
  - "==": [{ "var": "has_reproduction_steps" }, true]
  - ">=": [{ "var": "extraction_confidence" }, 0.8]
"""
rule = yaml.safe_load(rule_yaml)

data = {
    "has_reproduction_steps": True,
    "extraction_confidence": 0.9
}

print(f"Rule: {rule}")
print(f"Data: {data}")

try:
    result = jsonLogic(rule, data)
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")
