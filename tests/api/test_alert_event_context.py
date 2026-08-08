# -*- coding: utf-8 -*-
from __future__ import annotations
import json, unittest
from api.v1.services.alert_event_context import enrich_trigger_items_with_event_contexts, extract_event_display_contexts, parse_diagnostics_object

class AlertEventContextExtractionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_diagnostics_object({"a": 1}), {"a": 1})
        self.assertIsNone(parse_diagnostics_object("x"))
    def test_extract_and_enrich(self):
        d = {"impact_context": {"why_it_matters": "why", "event_category": "earnings"}, "event_context": {"matched_count": 2}}
        c = extract_event_display_contexts(json.dumps(d))
        self.assertEqual(c["impact_context"]["why_it_matters"], "why")
        out = enrich_trigger_items_with_event_contexts([{"id": 1}, {"id": 2}], raw_diagnostics_by_id={1: json.dumps(d)})
        self.assertEqual(out[0]["impact_context"]["why_it_matters"], "why")
        self.assertNotIn("impact_context", out[1])

if __name__ == "__main__":
    unittest.main()
