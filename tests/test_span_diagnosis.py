"""Regression tests for the diagnosis gate in the span-first pipeline."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server_work"))

# The diagnosis helpers are deterministic and do not call the legacy vLLM
# adapter.  Stub that adapter's heavyweight optional imports so this unit test
# remains runnable in a minimal local Python environment.
endpoint_stub = ModuleType("endpoint")
endpoint_stub.model_endpoint_dict = {}
utils_stub = ModuleType("utils")
utils_stub.generate_vllm = lambda **_: ("", None, None, None, None)
sys.modules.setdefault("endpoint", endpoint_stub)
sys.modules.setdefault("utils", utils_stub)

import run_qae_localized as qae  # noqa: E402


def _record() -> dict:
    return {
        "idx": 1,
        "question": "Which statement about the tested mechanism is supported?\nA. First\nB. Second",
        "initial_answers": {"0": "A", "1": "B"},
        "qae_hard": {},
        "qae_plan": [{"evidence_id": "stale", "answers": {}}],
        "swarm_conflict": {},
        "swarm_spans": {
            "status": "DONE",
            "spans": [
                {"span_id": "M0-S1", "model": "M0", "text": "The receptor is active when ligand binds."},
                {"span_id": "M1-S1", "model": "M1", "text": "The receptor is inactive when ligand binds."},
            ],
        },
        "swarm_span_candidates": {
            "status": "DONE",
            "candidate_pairs": [{"span_refs": ["M0-S1", "M1-S1"]}],
        },
    }


def _context_record() -> dict:
    """One D0 pair whose entity definition is adjacent to its calculation."""
    spans = [
        {
            "span_id": "M0-S1", "model": "M0", "start": 0, "end": 58,
            "text": "For Star_1, the measured silicon abundance is discussed here.",
        },
        {
            "span_id": "M0-S2", "model": "M0", "start": 59, "end": 95,
            "text": "The calculation is 7.5 + 0.3 = 7.8.",
        },
        {
            "span_id": "M1-S1", "model": "M1", "start": 0, "end": 58,
            "text": "For Star_1, the measured silicon abundance is discussed here.",
        },
        {
            "span_id": "M1-S2", "model": "M1", "start": 59, "end": 105,
            "text": r"The calculation is 10^{0.3} \approx 2.0.",
        },
    ]
    return {
        "idx": 17,
        "question": "What numerical silicon abundance follows for Star_1?\nA. First\nB. Second",
        "initial_answers": {"0": "A", "1": "B"},
        "qae_hard": {},
        "qae_plan": [],
        "swarm_conflict": {},
        "swarm_diagnosis": {
            "status": "ELIGIBLE", "diagnosis_id": "D0",
            "problem_type": "numeric_calculation", "diagnosis_type": "formula_or_calculation_error",
            "claim_category": "quantitative_relation", "span_refs": ["M0-S2", "M1-S2"],
        },
        "swarm_spans": {"status": "DONE", "spans": spans},
        "swarm_span_candidates": {
            "status": "DONE",
            "candidate_pairs": [{"span_refs": ["M0-S2", "M1-S2"], "retrieval_basis": "test"}],
        },
    }


def _numeric_multispan_response(cross_packet_entity: bool = False) -> dict:
    return {
        "status": "CONFLICT", "span_refs": ["M0-S2", "M1-S2"],
        "same_entity": True, "same_conditions": True,
        "entity": "Star_1", "attribute": "silicon abundance", "conditions": "none",
        "left_entity_ref": "M1-S1" if cross_packet_entity else "M0-S1",
        "right_entity_ref": "M1-S1",
        "left_entity_span": "Star_1", "right_entity_span": "Star_1",
        "left_attribute_ref": "M0-S1", "right_attribute_ref": "M1-S1",
        "left_attribute_span": "silicon abundance", "right_attribute_span": "silicon abundance",
        "left_condition_ref": "none", "right_condition_ref": "none",
        "left_condition_span": "none", "right_condition_span": "none",
        "left_result_ref": "M0-S2", "right_result_ref": "M1-S2",
        "left_result_span": "7.5 + 0.3 = 7.8", "right_result_span": r"10^{0.3} \approx 2.0",
        "left_direction": "unchanged", "right_direction": "unchanged",
        "conflict_type": "calculation",
        "description": "The calculations produce incompatible terminal values.",
        "why_decisive": "The competing values change the asserted abundance.",
        "target_question": "Which calculation gives the silicon abundance for Star_1?",
        "verification_route": "numeric",
    }


class DiagnosisStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = _record()
        self.pairs = self.record["swarm_span_candidates"]["candidate_pairs"]

    def test_eligible_diagnosis_requires_a_program_owned_cross_model_pair(self) -> None:
        state = qae._diagnosis_state(
            self.record,
            self.pairs,
            {
                "problem_type": "causal_mechanism|conditional_logic",
                "diagnosis_type": "fact_or_concept_error|entity_confusion",
                "verification_eligible": True,
                "span_refs": ["M0-S1", "M1-S1"],
                "claim_category": "causal_mechanism|entity_relation",
                "new_claim_label": "none",
                "reason": "The two spans assert opposite receptor activity under ligand binding.",
            },
            "raw",
        )
        self.assertEqual(state["status"], "ELIGIBLE")
        self.assertEqual(state["route"], "span_first_verify")
        self.assertEqual(state["problem_type"], "causal_mechanism")
        self.assertEqual(state["diagnosis_type"], "fact_or_concept_error")
        self.assertEqual(state["source_models"], ["M0", "M1"])

    def test_unretrieved_pair_is_explicitly_retained_in_a_pool(self) -> None:
        state = qae._diagnosis_state(
            self.record,
            self.pairs,
            {
                "problem_type": "fact_entity_relation",
                "diagnosis_type": "entity_confusion",
                "verification_eligible": True,
                "span_refs": ["M0-S1", "M2-S9"],
                "claim_category": "entity_relation",
                "reason": "A pair outside the retrieval ledger was proposed.",
            },
            "raw",
        )
        self.assertEqual(state["status"], "RETAIN_A_POOL")
        self.assertEqual(state["rejection_reason"], "diagnosis_pair_not_program_retrieved")

    def test_diagnosis_gate_clears_stale_evidence_plan(self) -> None:
        self.record["swarm_diagnosis"] = {
            "status": "RETAIN_A_POOL",
            "rejection_reason": "diagnosis_not_verifiable",
        }
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                diagnosis_gate=True,
                coreference_gate=True,
                out=str(Path(directory) / "state.json"),
            )
            qae.run_span_localize(args, [self.record])
        self.assertEqual(self.record["swarm_conflict"]["status"], "SKIPPED_DIAGNOSIS")
        self.assertEqual(self.record["qae_plan"], [])

    def test_grounded_numeric_terminal_values_can_be_incompatible(self) -> None:
        self.assertTrue(
            qae._numeric_anchor_results_incompatible(
                "7.5 + 0.3 = 7.8", r"10^{0.3} \approx 2.0",
            )
        )
        self.assertFalse(qae._numeric_anchor_results_incompatible("2.0 = 2.0", "2 = 2"))

    def test_no_evidence_route_skips_resolves_and_retains_a_pool(self) -> None:
        record = _record()
        record.update({
            "stored_goa_answer": "A",
            "qae_plan": [],
            "qae_ledger": {},
            "qae_clean": {},
            "qae_rebuttal": {},
            "qae_pooler": {},
            "qae_final_answer": None,
        })
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(diagnosis_gate=True, out=str(Path(directory) / "state.json"))
            self.assertFalse(qae.run_verify_needed([record]))
            qae.run_solve(args, [record], "qae_clean", False)
            qae.run_pool(args, [record])
        self.assertEqual(record["qae_clean"]["reason"], "skipped_no_valid_ledger_evidence")
        self.assertEqual(record["qae_final_answer"], "A")
        self.assertEqual(record["qae_final_reason"], "retain_A_pool_no_valid_ledger_evidence")

    def test_context_packet_is_same_model_and_bounded(self) -> None:
        record = _context_record()
        spans = {span["span_id"]: span for span in record["swarm_spans"]["spans"]}
        packet = qae._span_context_packet(spans, "M0-S2", 1)
        self.assertEqual(packet["span_refs"], ["M0-S1", "M0-S2"])
        self.assertEqual(packet["model"], "M0")
        self.assertEqual(qae._span_context_packet(spans, "M0-S2", 99)["radius"], 2)

    def test_multispan_numeric_claim_keeps_individual_absolute_offsets(self) -> None:
        record = _context_record()
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                diagnosis_gate=True, coreference_gate=True, span_context_radius=1, model="qwen",
                out=str(Path(directory) / "state.json"),
            )
            with patch.object(qae, "_call_json", return_value=("raw", _numeric_multispan_response())):
                qae.run_span_localize(args, [record])
        conflict = record["swarm_conflict"]
        self.assertEqual(conflict["status"], "CONFLICT")
        self.assertEqual(conflict["span_refs"], ["M0-S2", "M1-S2"])
        self.assertEqual(conflict["claim_refs"], ["M0-S1", "M0-S2", "M1-S1", "M1-S2"])
        left = conflict["structured_claims"][0]
        self.assertEqual(left["support"]["entity"]["span_ref"], "M0-S1")
        self.assertEqual(left["support"]["result"]["span_ref"], "M0-S2")
        self.assertEqual(left["support"]["result"]["anchor_start"], 78)
        self.assertEqual(left["support"]["result"]["anchor_end"], 93)

    def test_multispan_claim_rejects_cross_packet_field_reference(self) -> None:
        record = _context_record()
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                diagnosis_gate=True, coreference_gate=True, span_context_radius=1, model="qwen",
                out=str(Path(directory) / "state.json"),
            )
            with patch.object(qae, "_call_json", return_value=("raw", _numeric_multispan_response(True))):
                qae.run_span_localize(args, [record])
        self.assertEqual(record["swarm_conflict"]["status"], "NO_VALID_SPAN_CONFLICT")


if __name__ == "__main__":
    unittest.main()
