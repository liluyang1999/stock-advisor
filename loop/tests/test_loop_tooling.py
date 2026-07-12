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
        self.assertEqual(check_traceability.check.stats["requirements"], 34)

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
        self.assertIn("Loop schemas: `22`", rendered)
        self.assertIn("Traceability: `34/34`", rendered)

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

    def test_every_adr_has_an_associations_section(self) -> None:
        # Every decisions/NNNN-*.md must cite the REQ/AC/WI/RISK/EVD ids it rests
        # on via a "## 关联" section (loop/templates/ADR.md, decisions/README.md).
        self.assertEqual(validate_loop._adr_association_errors(), [])
        self.assertFalse(validate_loop._has_associations_section("# ADR-9999\n\n## 决策\n\nx\n"))
        self.assertTrue(validate_loop._has_associations_section("## 关联\n\nREQ-001。\n"))

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

    def test_every_catalog_test_has_measurable_goal(self) -> None:
        import json as _json
        cat = _json.loads((LOOP_ROOT / "quality/test-catalog.json").read_text(encoding="utf-8"))
        work_ids = {w["id"] for w in _json.loads((LOOP_ROOT / "planning/work-items.json").read_text(encoding="utf-8"))["work_items"]}
        for t in cat["tests"]:
            self.assertTrue(t.get("expected_goal"), t["id"])
            self.assertIn(t.get("evidence_level"), {"V0_assumption","V1_static","V2_unit","V3_integration","V4_system","V5_release"}, t["id"])
            self.assertRegex(t.get("owning_work_item",""), r"^WI-\d{3}$", t["id"])
            self.assertIn(t["owning_work_item"], work_ids, t["id"])
            self.assertTrue(t.get("expected_artifact"), t["id"])
        self.assertEqual(validate_loop.validate(), [])

    def test_every_work_item_has_a_size(self) -> None:
        work_items = json.loads((LOOP_ROOT / "planning/work-items.json").read_text(encoding="utf-8"))["work_items"]
        self.assertEqual(len(work_items), 26)
        for wi in work_items:
            self.assertIn(wi.get("size"), {"S", "M", "L", "XL"}, wi["id"])
            self.assertTrue(wi.get("definition_of_done"), wi["id"])
        self.assertEqual(validate_loop.validate(), [])

    def test_every_gate_has_owning_work_item(self) -> None:
        gates = json.loads((LOOP_ROOT / "quality/quality-gates.json").read_text(encoding="utf-8"))["gates"]
        work_ids = {w["id"] for w in json.loads((LOOP_ROOT / "planning/work-items.json").read_text(encoding="utf-8"))["work_items"]}
        for gate in gates:
            self.assertRegex(gate.get("owning_work_item", ""), r"^WI-\d{3}$", gate["id"])
            # owning_work_item need not be the gate's *real* future owner (dev-tool gates
            # placeholder to WI-000 until WS-8 exists), but it must always resolve to some
            # work item that exists today -- never a dangling id.
            self.assertIn(gate["owning_work_item"], work_ids, gate["id"])
        self.assertEqual(validate_loop.validate(), [])

    def test_gate_ownership_invariant_requires_enabled_or_owning_work_item(self) -> None:
        gates = json.loads((LOOP_ROOT / "quality/quality-gates.json").read_text(encoding="utf-8"))["gates"]

        # the real gate list satisfies the invariant right now
        self.assertEqual(validate_loop._gate_ownership_errors(gates), [])

        # in-memory mutation only, nothing written back to quality-gates.json: a
        # required_for_release gate that is neither enabled nor owned must be rejected.
        broken = [dict(gate) for gate in gates]
        broken[0]["required_for_release"] = True
        broken[0]["enabled"] = False
        broken[0]["owning_work_item"] = ""
        errors = validate_loop._gate_ownership_errors(broken)
        self.assertTrue(any(broken[0]["id"] in error for error in errors), errors)

        # a disabled, required_for_release gate WITH an owner is fine (this is exactly
        # the dev-tool gate shape: G-FORMAT/G-LINT/G-TYPE/G-COVERAGE).
        owned_but_disabled = [dict(gate) for gate in gates]
        owned_but_disabled[0]["required_for_release"] = True
        owned_but_disabled[0]["enabled"] = False
        owned_but_disabled[0]["owning_work_item"] = "WI-000"
        self.assertEqual(validate_loop._gate_ownership_errors(owned_but_disabled), [])

    def test_coverage_gate_is_present_and_disabled_with_placeholder_owner(self) -> None:
        gates = {g["id"]: g for g in json.loads((LOOP_ROOT / "quality/quality-gates.json").read_text(encoding="utf-8"))["gates"]}
        coverage = gates["G-COVERAGE"]
        self.assertFalse(coverage["enabled"])
        self.assertTrue(coverage["required_for_release"])
        self.assertEqual(coverage["owning_work_item"], "WI-000")
        self.assertTrue(coverage.get("note"))
        commands = coverage["commands"]
        self.assertIn(["coverage", "report", "--fail-under=85"], commands)
        for gate_id in ("G-FORMAT", "G-LINT", "G-TYPE"):
            self.assertEqual(gates[gate_id]["owning_work_item"], "WI-000", gate_id)
            self.assertTrue(gates[gate_id].get("note"), gate_id)

    def test_performance_and_reliability_targets_are_measurable(self) -> None:
        test_ids = {t["id"] for t in json.loads((LOOP_ROOT / "quality/test-catalog.json").read_text(encoding="utf-8"))["tests"]}
        budgets = json.loads((LOOP_ROOT / "quality/performance-budgets.json").read_text(encoding="utf-8"))["budgets"]
        for budget in budgets:
            self.assertTrue(budget.get("method"), budget["metric"])
            self.assertTrue(budget.get("scenario"), budget["metric"])
            self.assertIn(budget.get("owning_test"), test_ids, budget["metric"])

        targets = json.loads((LOOP_ROOT / "quality/reliability-targets.json").read_text(encoding="utf-8"))["targets"]
        for target in targets:
            self.assertTrue(target.get("method"), target["id"])
            self.assertTrue(target.get("scenario"), target["id"])
            self.assertIn(target.get("owning_test"), test_ids, target["id"])
        rel009 = next(t for t in targets if t["id"] == "REL-009")
        self.assertIsInstance(rel009.get("deadline_ms"), int)
        self.assertGreater(rel009["deadline_ms"], 0)

    def test_tk_contract_mapping_has_header_and_disposition_contract(self) -> None:
        self.assertEqual(check_traceability.check_tk_contract_mapping(), [])
        self.assertEqual(check_traceability.TK_CONTRACT_EXPECTED_ROW_COUNT, 187)

        # wrong header is rejected
        errors = check_traceability._tk_contract_mapping_errors(("wrong", "header"), [])
        self.assertTrue(any("header must be" in error for error in errors), errors)

        # qt_replaced without a replacement_test_id is rejected
        bad_rows = [{
            "contract_id": "TKC-001", "area": "gui_layout", "disposition": "qt_replaced",
            "replacement_test_id": "", "notes": "",
        }]
        errors = check_traceability._tk_contract_mapping_errors(check_traceability.TK_CONTRACT_COLUMNS, bad_rows)
        self.assertTrue(any("replacement_test_id" in error for error in errors), errors)

        # an unrecognized disposition value is rejected
        pending_rows = [{
            "contract_id": "TKC-002", "area": "ui_polish", "disposition": "pending",
            "replacement_test_id": "", "notes": "",
        }]
        errors = check_traceability._tk_contract_mapping_errors(check_traceability.TK_CONTRACT_COLUMNS, pending_rows)
        self.assertTrue(any("invalid disposition" in error for error in errors), errors)

        # a fully valid row of each disposition passes
        good_rows = [
            {"contract_id": "TKC-003", "area": "gui_layout", "disposition": "pure_preserved", "replacement_test_id": "", "notes": ""},
            {"contract_id": "TKC-004", "area": "gui_layout", "disposition": "qt_replaced", "replacement_test_id": "TEST-QT-001", "notes": ""},
            {"contract_id": "TKC-005", "area": "ui_polish", "disposition": "approved_retired", "replacement_test_id": "", "notes": ""},
        ]
        self.assertEqual(
            check_traceability._tk_contract_mapping_errors(check_traceability.TK_CONTRACT_COLUMNS, good_rows), []
        )


if __name__ == "__main__":
    unittest.main()
