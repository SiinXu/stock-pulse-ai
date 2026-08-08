# -*- coding: utf-8 -*-
import json, unittest
from src.agent.protocols import StrategyOpinion
from src.agent.skills.synthesis import ConflictDetector, StrategySynthesizer
from src.schemas.strategy_evidence_contract import (
    validate_deliberation_payload,
    validate_revision_projection_payload,
)

class TestDeliberationDefaultOffParity(unittest.TestCase):
    def test_default_off_matches_baseline_payload(self):
        opinions = [
            StrategyOpinion(skill_id="bull_trend", signal="strong_buy", confidence=0.82),
            StrategyOpinion(skill_id="hot_theme", signal="strong_sell", confidence=0.78),
        ]
        conflicts = ConflictDetector().detect(opinions, final_signal="hold")
        kwargs = dict(
            opinions=opinions,
            weighted_score=3.0,
            final_signal="hold",
            weighted_confidence=0.8,
            conflicts=conflicts,
        )
        baseline = StrategySynthesizer().synthesize(**kwargs)
        disabled = StrategySynthesizer(deliberation_enabled=False).synthesize(**kwargs)
        enabled = StrategySynthesizer(deliberation_enabled=True).synthesize(**kwargs)
        self.assertEqual(
            json.dumps(baseline, sort_keys=True, default=str),
            json.dumps(disabled, sort_keys=True, default=str),
        )
        self.assertNotIn("deliberation", baseline)
        self.assertIn("deliberation", enabled)
        self.assertLess(enabled["confidence"], baseline["confidence"])
        self.assertIsNotNone(validate_deliberation_payload(enabled["deliberation"]))
        self.assertFalse(
            validate_revision_projection_payload(enabled["revision_projection"])["final_signal_overridden"]
        )

if __name__ == "__main__":
    unittest.main()
