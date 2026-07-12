from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


LOOP_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = LOOP_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_traceability  # noqa: E402
import check_core_boundaries  # noqa: E402
import render_backlog  # noqa: E402
import render_status  # noqa: E402
import update_state  # noqa: E402
import validate_loop  # noqa: E402
from _common import validate_against_schema  # noqa: E402


class LoopToolingTests(unittest.TestCase):
    def test_loop_structure_is_valid(self) -> None:
        self.assertEqual(validate_loop.validate(), [])
        self.assertGreaterEqual(validate_loop.validate.stats["schema_documents"], 20)

    def test_schema_validator_rejects_invalid_documents(self) -> None:
        schema = {
            "type": "object",
            "required": ["name", "count"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "count": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        }
        issues = validate_against_schema({"name": "", "count": 0, "extra": True}, schema)
        self.assertTrue(any("shorter" in issue for issue in issues))
        self.assertTrue(any("below minimum" in issue for issue in issues))
        self.assertTrue(any("additional property" in issue for issue in issues))

    def test_traceability_covers_every_requirement(self) -> None:
        self.assertEqual(check_traceability.check(release=False), [])
        self.assertEqual(check_traceability.check.stats["requirements"], 30)

    def test_traceability_edges_agree_with_work_items(self) -> None:
        self.assertEqual(check_traceability.check(release=False), [], check_traceability.check(release=False))

    def test_every_acceptance_criterion_is_traced(self) -> None:
        self.assertEqual(check_traceability.check(release=False), [], check_traceability.check(release=False))
        self.assertIn("acceptance_criteria", check_traceability.REQUIRED_COLUMNS)

    def test_backlog_is_exact_projection(self) -> None:
        self.assertEqual(render_backlog.check_backlog(), [])

    def test_protected_core_has_no_forbidden_imports(self) -> None:
        self.assertEqual(check_core_boundaries.check(), [])
        self.assertEqual(check_core_boundaries.check.stats["modules"], 12)

    def test_core_boundary_parser_detects_relative_infrastructure_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.py"
            path.write_text("from .data_provider import EastmoneyProvider\n", encoding="utf-8")
            roots, internal = check_core_boundaries._import_targets(path, "stock_advisor")
            self.assertEqual(roots, set())
            self.assertIn("data_provider", internal)

    def test_release_traceability_is_intentionally_not_green_yet(self) -> None:
        errors = check_traceability.check(release=True)
        self.assertTrue(errors)
        self.assertTrue(any("not release-verified" in error for error in errors))

    def test_status_mentions_authoritative_state(self) -> None:
        self.assertEqual(render_status.check_status(), [])
        rendered = render_status.render()
        actual = (LOOP_ROOT / "STATUS.md").read_text(encoding="utf-8")
        self.assertEqual(actual, rendered)
        self.assertIn("Loop tooling tests:", rendered)
        self.assertIn("Loop schemas: `20`", rendered)
        self.assertIn("Traceability: `30/30`", rendered)

    def test_target_stack_and_font_are_explicit(self) -> None:
        config = json.loads((LOOP_ROOT / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["target_stack"]["gui"], "PySide6")
        self.assertEqual(config["target_stack"]["runtime_font"], "Microsoft YaHei")
        self.assertEqual(config["ui_tokens"]["font_families"], ["Microsoft YaHei"])
        self.assertEqual(config["ui_tokens"]["control_min_height_dip"], 44)
        self.assertEqual(config["ui_tokens"]["primary_control_height_dip"], 48)
        self.assertEqual(config["ui_tokens"]["table_row_height_dip"], 48)

    def test_market_timezone_is_shanghai(self) -> None:
        config = json.loads((LOOP_ROOT / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["project"]["market_timezone"], "Asia/Shanghai")
        self.assertEqual(validate_loop.validate(), [])

    def test_false_success_transition_is_rejected(self) -> None:
        state = json.loads((LOOP_ROOT / "state/current.json").read_text(encoding="utf-8"))
        errors = update_state.validate_transition(state, "complete", "success")
        self.assertTrue(errors)
        self.assertTrue(any("release_candidate" in error for error in errors))

    def test_unknown_terminal_state_is_rejected(self) -> None:
        state = json.loads((LOOP_ROOT / "state/current.json").read_text(encoding="utf-8"))
        errors = update_state.validate_transition(state, "active", "invented")
        self.assertTrue(any("unknown terminal state" in error for error in errors))

    def test_risk_scores_are_deterministic(self) -> None:
        payload = json.loads((LOOP_ROOT / "registers/risks.json").read_text(encoding="utf-8"))
        for risk in payload["risks"]:
            self.assertEqual(risk["score"], risk["probability"] * risk["impact"], risk["id"])

    def test_state_risk_ids_match_register(self) -> None:
        self.assertEqual(validate_loop.validate(), [], validate_loop.validate())

    def test_current_state_does_not_claim_pyside6_is_complete(self) -> None:
        state = json.loads((LOOP_ROOT / "state/current.json").read_text(encoding="utf-8"))
        self.assertFalse(state["release_candidate"])
        self.assertNotEqual(state["status"], "complete")

    def test_superseded_v2_evidence_is_exempt_from_digest(self) -> None:
        record = {
            "id": "EVD-TEST",
            "record_version": "2.0.0",
            "control_plane_sha256": "0" * 64,  # deliberately wrong
            "superseded_by": "EVD-NEXT",
        }
        self.assertTrue(validate_loop._digest_ok(record))
        record_current = dict(record)
        record_current.pop("superseded_by")
        self.assertFalse(validate_loop._digest_ok(record_current))

    def test_live_v2_baseline_is_required_and_supersede_refs_resolve(self) -> None:
        # real state passes
        self.assertEqual(validate_loop.validate(), [], validate_loop.validate())

        real_digest = validate_loop.control_plane_digest()
        records = json.loads(
            (LOOP_ROOT / "state" / "evidence-index.json").read_text(encoding="utf-8")
        )["evidence"]

        # In-process mutation only: copy the loaded dicts, mutate the copies, and call
        # the small validate_loop._evidence_baseline_errors() helper directly. Nothing
        # here is written back to state/evidence-index.json.

        # (a) If every v2 record carries a truthy superseded_by -- even one pointing
        # nowhere -- the live-baseline requirement must fire: no record is left that
        # both matches the digest and is unsuperseded.
        holed = [dict(record) for record in records]
        for record in holed:
            if record.get("record_version") == "2.0.0":
                record["superseded_by"] = "EVD-NONE"
        errors = validate_loop._evidence_baseline_errors(holed, real_digest)
        self.assertIn("no live v2 baseline evidence matches the current control plane", errors)

        # (b) A superseded_by value that names a nonexistent evidence id must be
        # rejected as a dangling reference, independent of the check above.
        dangling = [dict(record) for record in records]
        dangling[0]["superseded_by"] = "EVD-DOES-NOT-EXIST"
        errors = validate_loop._evidence_baseline_errors(dangling, real_digest)
        self.assertTrue(
            any("superseded_by references unknown evidence" in error for error in errors), errors
        )

    def test_registers_reject_duplicate_ids(self) -> None:
        self.assertEqual(validate_loop.validate(), [], validate_loop.validate())
        self.assertTrue(validate_loop._duplicates(["X", "X"]))

    def test_decision_ledger_keeps_status_history_without_tripping_duplicate_check(self) -> None:
        # registers/decisions.jsonl is an append-only ADR status ledger: the same id
        # legitimately reappears whenever its status changes. It must stay excluded
        # from the per-register id-uniqueness check so real audit history is never
        # flagged as a defect the way registers/experiments.jsonl's accidental
        # duplicate id is.
        ids = [row["id"] for row in validate_loop.parse_jsonl(LOOP_ROOT / "registers" / "decisions.jsonl")]
        self.assertTrue(validate_loop._duplicates(ids), "fixture assumption: decisions.jsonl has status-history duplicates")
        self.assertEqual(validate_loop.validate(), [])

    def test_dereferenced_files_are_declared_required(self) -> None:
        for needed in ("quality/test-catalog.json", "planning/dependency-graph.json"):
            self.assertIn(needed, validate_loop.REQUIRED_FILES, needed)

    def test_closed_schemas_reject_unknown_fields_and_pin_version(self) -> None:
        closed = ["state", "loop", "config", "work-items", "quality-gates",
                  "risk", "evidence", "metrics", "backlog", "milestones"]
        root = LOOP_ROOT / "schemas"
        for name in closed:
            schema = json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8"))
            self.assertIs(schema.get("additionalProperties"), False, name)
            sv = schema.get("properties", {}).get("schema_version", {})
            self.assertTrue("const" in sv or "pattern" in sv, name)


if __name__ == "__main__":
    unittest.main()
