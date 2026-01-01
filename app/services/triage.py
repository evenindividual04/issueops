import yaml
from app.services.logic import apply as json_logic_apply
import logging
from typing import List, Dict, Any
from pydantic import TypeAdapter, ValidationError

from app.models.schemas import IssueMetadata, TriageAction, RuleDefinition

logger = logging.getLogger(__name__)

class TriageService:
    """
    Deterministic Rules Engine.
    Evaluates IssueMetadata against a set of json-logic rules to decide priority and labels.
    """

    def __init__(self, rules_path: str = "rules.yaml"):
        self.rules_path = rules_path
        self.rules: List[RuleDefinition] = []
        self.load_rules()

    def load_rules(self):
        """Load and validate rules from YAML with fallback."""
        
        def _load_and_validate(path: str) -> List[RuleDefinition]:
            with open(path, "r") as f:
                raw_rules = yaml.safe_load(f)
            
            # Validate strict schema
            adapter = TypeAdapter(List[RuleDefinition])
            return adapter.validate_python(raw_rules)

        try:
            self.rules = _load_and_validate(self.rules_path)
            logger.info(f"Loaded {len(self.rules)} triage rules from {self.rules_path}")
            
        except (ValidationError, FileNotFoundError, yaml.YAMLError) as e:
            logger.warning(f"Configuration Error in {self.rules_path}: {e}")
            
            # Fallback Strategy: If user config fails, try default
            if self.rules_path != "rules.yaml":
                logger.info("Falling back to default 'rules.yaml'...")
                try:
                    self.rules = _load_and_validate("rules.yaml")
                    logger.info("Loaded default rules successfully.")
                except Exception as e_default:
                    logger.error(f"CRITICAL: Default rules.yaml is broken! {e_default}")
                    self.rules = []
            else:
                self.rules = []

    def evaluate(self, metadata: IssueMetadata) -> TriageAction:
        """
        Evaluate metadata against loaded rules.
        Returns the action of the FIRST matching rule.
        Default action if no rules match: Priority 3 (Normal).
        """
        # Convert Pydantic model to dict for json-logic
        data = metadata.model_dump()

        for rule in self.rules:
            try:
                if json_logic_apply(rule.condition, data):
                    logger.info(f"Rule Matched: {rule.name}")
                    return rule.action
            except Exception as e:
                logger.error(f"Error evaluating rule '{rule.name}': {e}")
                continue
        
        # Default Fallback
        return TriageAction(
            priority_score=3,
            labels=["triage/needs-review"],
            reasoning="No specific triage rules matched. Defaulting to normal priority."
        )
