"""Regression tests for the diagnosis gate in the span-first pipeline."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType


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


if __name__ == "__main__":
    unittest.main()
