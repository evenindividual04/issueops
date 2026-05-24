import logging
from typing import Any, Dict, List, Optional

import yaml
from pydantic import TypeAdapter, ValidationError

from app.models.schemas import IssueMetadata, RuleDefinition, RuleResult, TriageAction
from app.services.logic import apply as json_logic_apply

logger = logging.getLogger(__name__)

_LOW_CONFIDENCE_ACTION = TriageAction(
    priority_score=3,
    labels=["triage/low-confidence"],
    reasoning="Extraction confidence below threshold — flagged for manual review.",
)

_DEFAULT_ACTION = TriageAction(
    priority_score=3,
    labels=["triage/needs-review"],
    reasoning="No specific triage rules matched. Defaulting to normal priority.",
)


class TriageService:
    """
    Deterministic Rules Engine.
    Evaluates IssueMetadata against a set of JSON-Logic rules.
    """

    def __init__(self, rules_path: str = "rules.yaml"):
        self.rules_path = rules_path
        self.rules: List[RuleDefinition] = []
        self.load_rules()

    def load_rules(self) -> None:
        def _load_and_validate(path: str) -> List[RuleDefinition]:
            with open(path) as f:
                raw_rules = yaml.safe_load(f)
            return TypeAdapter(List[RuleDefinition]).validate_python(raw_rules)

        try:
            self.rules = _load_and_validate(self.rules_path)
            logger.info(f"Loaded {len(self.rules)} rules from {self.rules_path}")
        except (ValidationError, FileNotFoundError, yaml.YAMLError) as e:
            logger.warning(f"Config error in {self.rules_path}: {e}")
            if self.rules_path != "rules.yaml":
                logger.info("Falling back to default rules.yaml...")
                try:
                    self.rules = _load_and_validate("rules.yaml")
                except Exception as e_default:
                    logger.error(f"Default rules.yaml is broken: {e_default}")
                    self.rules = []
            else:
                self.rules = []

    def evaluate(
        self,
        metadata: IssueMetadata,
        context: Optional[Dict[str, Any]] = None,
        min_confidence: float = 0.75,
    ) -> TriageAction:
        """
        Evaluate metadata against loaded rules.
        Returns the action of the first matching rule.

        If extraction_confidence < min_confidence, returns a low-confidence
        action instead of applying labels automatically — preventing incorrect
        labels from uncertain AI extractions.
        """
        if metadata.extraction_confidence < min_confidence:
            logger.warning(
                f"Low confidence ({metadata.extraction_confidence:.2f} < {min_confidence:.2f})"
                " — skipping auto-labeling."
            )
            return _LOW_CONFIDENCE_ACTION

        data = metadata.model_dump()
        if context:
            data.update(context)

        for rule in self.rules:
            try:
                if json_logic_apply(rule.condition, data):
                    logger.info(f"Rule matched: {rule.name}")
                    return rule.action
            except Exception as e:
                logger.error(f"Error evaluating rule '{rule.name}': {e}")

        return _DEFAULT_ACTION

    def trace(
        self,
        metadata: IssueMetadata,
        context: Optional[Dict[str, Any]] = None,
        min_confidence: float = 0.75,
    ) -> List[RuleResult]:
        """
        Evaluate ALL rules and return a full decision trace.
        Unlike evaluate(), does not stop at the first match.
        """
        if metadata.extraction_confidence < min_confidence:
            return [RuleResult(
                rule_name="confidence-gate",
                matched=True,
                action=_LOW_CONFIDENCE_ACTION,
            )]

        data = metadata.model_dump()
        if context:
            data.update(context)

        results = []
        for rule in self.rules:
            matched = False
            try:
                matched = bool(json_logic_apply(rule.condition, data))
            except Exception as e:
                logger.error(f"Error checking rule '{rule.name}': {e}")

            results.append(RuleResult(
                rule_name=rule.name,
                matched=matched,
                action=rule.action if matched else None,
            ))

        return results
