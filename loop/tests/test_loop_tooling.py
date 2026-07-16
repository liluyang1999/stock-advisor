from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

LOOP_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = LOOP_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_core_boundaries  # noqa: E402
import check_coverage  # noqa: E402
import check_traceability  # noqa: E402
import render_backlog  # noqa: E402
import render_status  # noqa: E402
import run_gates  # noqa: E402
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
        self.assertEqual(
            check_traceability.check(release=False), [], check_traceability.check(release=False)
        )

    def test_every_acceptance_criterion_is_traced(self) -> None:
        self.assertEqual(
            check_traceability.check(release=False), [], check_traceability.check(release=False)
        )
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
        ids = [
            row["id"]
            for row in validate_loop.parse_jsonl(LOOP_ROOT / "registers" / "decisions.jsonl")
        ]
        self.assertTrue(
            validate_loop._duplicates(ids),
            "fixture assumption: decisions.jsonl has status-history duplicates",
        )
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
        closed = [
            "state",
            "loop",
            "config",
            "work-items",
            "quality-gates",
            "risk",
            "evidence",
            "metrics",
            "backlog",
            "milestones",
        ]
        root = LOOP_ROOT / "schemas"
        for name in closed:
            schema = json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8"))
            self.assertIs(schema.get("additionalProperties"), False, name)
            sv = schema.get("properties", {}).get("schema_version", {})
            self.assertTrue("const" in sv or "pattern" in sv, name)

    def test_every_catalog_test_has_measurable_goal(self) -> None:
        import json as _json

        cat = _json.loads((LOOP_ROOT / "quality/test-catalog.json").read_text(encoding="utf-8"))
        work_ids = {
            w["id"]
            for w in _json.loads(
                (LOOP_ROOT / "planning/work-items.json").read_text(encoding="utf-8")
            )["work_items"]
        }
        for t in cat["tests"]:
            self.assertTrue(t.get("expected_goal"), t["id"])
            self.assertIn(
                t.get("evidence_level"),
                {
                    "V0_assumption",
                    "V1_static",
                    "V2_unit",
                    "V3_integration",
                    "V4_system",
                    "V5_release",
                },
                t["id"],
            )
            self.assertRegex(t.get("owning_work_item", ""), r"^WI-\d{3}$", t["id"])
            self.assertIn(t["owning_work_item"], work_ids, t["id"])
            self.assertTrue(t.get("expected_artifact"), t["id"])
        self.assertEqual(validate_loop.validate(), [])

    def test_every_work_item_has_a_size(self) -> None:
        work_items = json.loads(
            (LOOP_ROOT / "planning/work-items.json").read_text(encoding="utf-8")
        )["work_items"]
        self.assertEqual(len(work_items), 29)
        for wi in work_items:
            self.assertIn(wi.get("size"), {"S", "M", "L", "XL"}, wi["id"])
            self.assertTrue(wi.get("definition_of_done"), wi["id"])
        self.assertEqual(validate_loop.validate(), [])

    def test_every_gate_has_owning_work_item(self) -> None:
        gates = json.loads((LOOP_ROOT / "quality/quality-gates.json").read_text(encoding="utf-8"))[
            "gates"
        ]
        work_ids = {
            w["id"]
            for w in json.loads(
                (LOOP_ROOT / "planning/work-items.json").read_text(encoding="utf-8")
            )["work_items"]
        }
        for gate in gates:
            self.assertRegex(gate.get("owning_work_item", ""), r"^WI-\d{3}$", gate["id"])
            # owning_work_item need not be the gate's *real* future owner (dev-tool gates
            # placeholder to WI-000 until WS-8 exists), but it must always resolve to some
            # work item that exists today -- never a dangling id.
            self.assertIn(gate["owning_work_item"], work_ids, gate["id"])
        self.assertEqual(validate_loop.validate(), [])

    def test_gate_ownership_invariant_requires_enabled_or_owning_work_item(self) -> None:
        gates = json.loads((LOOP_ROOT / "quality/quality-gates.json").read_text(encoding="utf-8"))[
            "gates"
        ]

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

    def test_coverage_gate_asserts_its_pass_condition_per_dimension(self) -> None:
        # G-COVERAGE used to run `coverage report --fail-under=85`, which floors coverage.py's
        # *combined* statement+branch total -- one blended number that asserts none of the four
        # thresholds the gate's pass_condition promises. It is now wired to check_coverage.py,
        # which asserts each dimension separately, so the gate certifies what it claims.
        gates = {
            g["id"]: g
            for g in json.loads(
                (LOOP_ROOT / "quality/quality-gates.json").read_text(encoding="utf-8")
            )["gates"]
        }
        coverage = gates["G-COVERAGE"]
        self.assertTrue(coverage["required_for_release"])
        self.assertEqual(coverage["owning_work_item"], "WI-000")
        self.assertTrue(coverage.get("note"))
        # coverage runs via the authoritative unittest runner, not pytest (Tk-GUI pytest flakiness,
        # see TOOLCHAIN_BASELINE.md); commands are `python -m ...` for PATH-independence (WS-8 wiring).
        self.assertEqual(
            coverage["commands"],
            [
                ["python", "-m", "coverage", "run", "-m", "unittest", "discover", "-s", "tests"],
                ["python", "-m", "coverage", "json", "-q", "-o", "build/coverage.json"],
                ["python", "loop/scripts/check_coverage.py", "build/coverage.json"],
            ],
        )
        # The blended --fail-under floor must not come back as the gate's evidence.
        self.assertNotIn("--fail-under", json.dumps(coverage["commands"]))
        # An enabled gate must be one the checker can actually keep green; a disabled one must
        # still be owned. Either way the gate may never claim a dimension it does not assert.
        self.assertIsInstance(coverage["enabled"], bool)
        for gate_id in ("G-FORMAT", "G-LINT", "G-TYPE"):
            self.assertEqual(gates[gate_id]["owning_work_item"], "WI-000", gate_id)
            self.assertTrue(gates[gate_id].get("note"), gate_id)

    def test_every_declared_coverage_threshold_is_asserted_or_explicitly_skipped(self) -> None:
        # The hole this closes: convergence.json documents six coverage floors, the checker
        # measures four, and the two qt_controller_* ones are unmeasurable until ADR-0001's
        # PySide6 migration lands. Nothing structural stopped a declared threshold from being
        # quietly ignored -- exactly how --fail-under came to certify four floors it never read.
        # Any threshold added to (or renamed in) convergence.json must now be either asserted by
        # check_coverage.py or listed as an explicit, reported SKIP.
        section = json.loads((LOOP_ROOT / "quality/convergence.json").read_text(encoding="utf-8"))[
            "coverage"
        ]
        declared = {key.removesuffix("_min") for key in section if key.endswith("_min")}
        handled = set(check_coverage.THRESHOLD_KEYS) | set(check_coverage.UNMEASURABLE)
        self.assertEqual(
            declared,
            handled,
            "a coverage threshold in convergence.json is neither asserted nor explicitly skipped",
        )

    def test_run_gates_default_excludes_release_phase_gates(self) -> None:
        gates = json.loads((LOOP_ROOT / "quality/quality-gates.json").read_text(encoding="utf-8"))[
            "gates"
        ]
        default_ids = [
            g["id"]
            for g in run_gates.select_gates(
                gates, only=[], include_disabled=False, report_only=False, release=False
            )
        ]
        self.assertIn("G-LOOP", default_ids)
        self.assertIn("G-CORE", default_ids)
        # G-TRACE runs release traceability (intentionally red pre-release); excluded by default.
        self.assertNotIn("G-TRACE", default_ids)
        self.assertNotIn("G-RELEASE", default_ids)
        release_ids = [
            g["id"]
            for g in run_gates.select_gates(
                gates, only=[], include_disabled=False, report_only=False, release=True
            )
        ]
        self.assertIn("G-TRACE", release_ids)

    def test_run_gates_classifies_and_degrades_on_missing_tool(self) -> None:
        self.assertEqual(
            run_gates.required_tool(["python", "-m", "ruff", "check"]), ("module", "ruff")
        )
        self.assertEqual(run_gates.required_tool(["mypy", "src"]), ("exe", "mypy"))
        self.assertIsNone(run_gates.required_tool(["python", "main.py"]))
        # a command needing a module that cannot exist degrades to SKIP, not a crash
        status, _ = run_gates.run_gate({"commands": [["python", "-m", "no_such_module_xyz"]]})
        self.assertEqual(status, "SKIP")

    def test_run_gates_reports_pass_and_fail(self) -> None:
        ok, _ = run_gates.run_gate({"commands": [["python", "-c", "pass"]]})
        self.assertEqual(ok, "PASS")
        bad, detail = run_gates.run_gate(
            {"commands": [["python", "-c", "import sys; sys.exit(3)"]]}
        )
        self.assertEqual(bad, "FAIL")
        self.assertIn("exit 3", detail)

    def test_performance_and_reliability_targets_are_measurable(self) -> None:
        test_ids = {
            t["id"]
            for t in json.loads(
                (LOOP_ROOT / "quality/test-catalog.json").read_text(encoding="utf-8")
            )["tests"]
        }
        budgets = json.loads(
            (LOOP_ROOT / "quality/performance-budgets.json").read_text(encoding="utf-8")
        )["budgets"]
        for budget in budgets:
            self.assertTrue(budget.get("method"), budget["metric"])
            self.assertTrue(budget.get("scenario"), budget["metric"])
            self.assertIn(budget.get("owning_test"), test_ids, budget["metric"])

        targets = json.loads(
            (LOOP_ROOT / "quality/reliability-targets.json").read_text(encoding="utf-8")
        )["targets"]
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
        bad_rows = [
            {
                "contract_id": "TKC-001",
                "area": "gui_layout",
                "disposition": "qt_replaced",
                "replacement_test_id": "",
                "notes": "",
            }
        ]
        errors = check_traceability._tk_contract_mapping_errors(
            check_traceability.TK_CONTRACT_COLUMNS, bad_rows
        )
        self.assertTrue(any("replacement_test_id" in error for error in errors), errors)

        # an unrecognized disposition value is rejected
        pending_rows = [
            {
                "contract_id": "TKC-002",
                "area": "ui_polish",
                "disposition": "pending",
                "replacement_test_id": "",
                "notes": "",
            }
        ]
        errors = check_traceability._tk_contract_mapping_errors(
            check_traceability.TK_CONTRACT_COLUMNS, pending_rows
        )
        self.assertTrue(any("invalid disposition" in error for error in errors), errors)

        # a fully valid row of each disposition passes
        good_rows = [
            {
                "contract_id": "TKC-003",
                "area": "gui_layout",
                "disposition": "pure_preserved",
                "replacement_test_id": "",
                "notes": "",
            },
            {
                "contract_id": "TKC-004",
                "area": "gui_layout",
                "disposition": "qt_replaced",
                "replacement_test_id": "TEST-QT-001",
                "notes": "",
            },
            {
                "contract_id": "TKC-005",
                "area": "ui_polish",
                "disposition": "approved_retired",
                "replacement_test_id": "",
                "notes": "",
            },
        ]
        self.assertEqual(
            check_traceability._tk_contract_mapping_errors(
                check_traceability.TK_CONTRACT_COLUMNS, good_rows
            ),
            [],
        )

    def test_waiver_schema_requires_owner_and_expiry(self) -> None:
        # governance/ENGINEERING_RULES.md's approved-skip exception and
        # governance/DEFINITION_OF_DONE.md's "0 未批准 skip" both resolve to the same
        # mechanism: a skip only counts as approved if registers/waivers.jsonl carries a
        # matching row with an owner and an expiry. This test pins the schema as the
        # mechanical guarantee behind that prose promise, and keeps the pre-existing
        # templates/waiver-record.json scaffold in lockstep with the closed schema.
        schema = json.loads((LOOP_ROOT / "schemas/waiver.schema.json").read_text(encoding="utf-8"))
        self.assertIs(schema.get("additionalProperties"), False)
        self.assertIn("owner", schema.get("required", []))
        self.assertIn("expires_at", schema.get("required", []))

        template = json.loads(
            (LOOP_ROOT / "templates/waiver-record.json").read_text(encoding="utf-8")
        )
        # the template documents the exact allowed shape: every key it uses must be a
        # declared schema property (else the closed schema would reject its own docs).
        self.assertEqual(set(template.keys()), set(schema["properties"].keys()))

        filled = dict(
            template,
            **{
                "id": "WVR-001",
                "gate_or_requirement": "TEST-EXAMPLE-001",
                "reason": "example",
                "risk": "example",
                "owner": "example-owner",
                "approved_by": "human",
                "expires_at": "2026-08-01",
                "status": "active",
            },
        )
        self.assertEqual(validate_against_schema(filled, schema), [])

        missing_owner = dict(filled)
        missing_owner.pop("owner")
        errors = validate_against_schema(missing_owner, schema)
        self.assertTrue(any("owner" in issue for issue in errors), errors)

        missing_expiry = dict(filled)
        missing_expiry.pop("expires_at")
        errors = validate_against_schema(missing_expiry, schema)
        self.assertTrue(any("expires_at" in issue for issue in errors), errors)

    def test_waivers_register_is_empty_pending_a_real_approved_skip(self) -> None:
        # No test under tests/ or loop/tests/ currently carries a skip decorator, so
        # there is truthfully no active approved skip to record; inventing an
        # illustrative row would fabricate a waiver for a skip that does not exist.
        # governance/ENGINEERING_RULES.md documents the flow so a real skip can be
        # recorded later without ambiguity. This pins the current, honest state.
        self.assertEqual(validate_loop.parse_jsonl(LOOP_ROOT / "registers" / "waivers.jsonl"), [])


class CoverageCheckerTests(unittest.TestCase):
    """check_coverage.py must fail loudly on the dimension that is actually below its floor.

    Testing only the green path would reproduce the defect this checker exists to fix: a gate
    that passes is worthless as evidence unless it is proven to fail when it should. Every
    dimension therefore gets its own red case, driven through main() so the exit code and the
    operator-visible message are what is pinned -- not just an internal helper's return value.

    The fixtures are synthetic reports, never the real build/coverage.json: the tests must not
    depend on the repository's current coverage, and must not touch build/ or the control plane.
    """

    # Baseline fixture: every dimension comfortably clear. Each red case perturbs exactly one
    # counter, so a failure names the dimension under test and nothing else.
    CORE = "src\\stock_advisor\\domain\\engine.py"  # backslashes as coverage.py emits on Windows
    OTHER = "src\\stock_advisor\\ui\\app.py"

    def _report(
        self,
        *,
        core_missing_lines: int = 10,
        core_missing_branches: int = 20,
        other_missing_lines: int = 60,
        other_missing_branches: int = 100,
    ) -> dict:
        def entry(missing_lines: int, missing_branches: int) -> dict:
            return {
                "summary": {
                    "num_statements": 1000,
                    "missing_lines": missing_lines,
                    "num_branches": 1000,
                    "missing_branches": missing_branches,
                }
            }

        return {
            "meta": {"branch_coverage": True},
            "files": {
                self.CORE: entry(core_missing_lines, core_missing_branches),
                self.OTHER: entry(other_missing_lines, other_missing_branches),
            },
        }

    @staticmethod
    def _write(directory: str, payload: object, name: str = "coverage.json") -> Path:
        path = Path(directory) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    @staticmethod
    def _run(path: Path) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check_coverage.main([str(path)])
        return code, out.getvalue(), err.getvalue()

    def test_report_meeting_every_threshold_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, self._report())
            code, out, err = self._run(path)
        self.assertEqual(code, 0, err)
        self.assertTrue(out.rstrip().splitlines()[-1].startswith("COVERAGE_OK"), out)
        self.assertEqual(err, "")
        # every measured dimension is reported, one line each, with its verdict
        for name in check_coverage.THRESHOLD_KEYS:
            self.assertIn(name, out)
        self.assertEqual(out.count("PASS"), len(check_coverage.THRESHOLD_KEYS))

    def _assert_only_dimension_fails(self, report: dict, dimension: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, report)
            code, out, err = self._run(path)
        self.assertEqual(code, 1, f"{dimension} should fail the gate\n{out}{err}")
        self.assertIn("COVERAGE_ERROR", err)
        # the error names the offending dimension...
        self.assertIn(dimension, err)
        # ...and only it: a red elsewhere would mean the fixture, not the checker, is doing the work
        failed = [
            other
            for other in check_coverage.THRESHOLD_KEYS
            if other != dimension and f"COVERAGE_ERROR {other} " in err
        ]
        self.assertEqual(failed, [], f"{dimension} fixture also tripped {failed}\n{err}")
        self.assertNotIn("COVERAGE_OK", out)

    def test_overall_statement_below_floor_fails(self) -> None:
        # 79.5% overall statements; core stays at 99%, branches stay green.
        self._assert_only_dimension_fails(
            self._report(other_missing_lines=400), "overall_statement"
        )

    def test_overall_branch_below_floor_fails(self) -> None:
        # 74% overall branches; core stays at 98%, statements stay green.
        self._assert_only_dimension_fails(
            self._report(other_missing_branches=500), "overall_branch"
        )

    def test_core_statement_below_floor_fails_even_though_overall_passes(self) -> None:
        # The exact blend the old --fail-under wiring hid: core statements at 90.0% (floor 95%)
        # while overall statements are 92.0% -- above their own 90% floor. A combined or
        # overall-only check calls this green; the core floor must still fail it.
        self._assert_only_dimension_fails(self._report(core_missing_lines=100), "core_statement")

    def test_core_branch_below_floor_fails_even_though_overall_passes(self) -> None:
        # Same masking, on branches: core at 85.0% (floor 90%) while overall is 87.5% (floor 85%).
        self._assert_only_dimension_fails(self._report(core_missing_branches=150), "core_branch")

    def test_thresholds_come_from_convergence_json_and_are_not_hardcoded(self) -> None:
        # convergence.json is the single source of truth for the coverage policy. If the checker
        # carried its own copy of the numbers, the two could drift and the gate would silently
        # enforce something the documented policy never said.
        document = json.loads((LOOP_ROOT / "quality/convergence.json").read_text(encoding="utf-8"))
        section = document["coverage"]
        live = check_coverage.load_thresholds()
        self.assertEqual(
            live,
            {name: section[key] for name, key in check_coverage.THRESHOLD_KEYS.items()},
            "check_coverage thresholds drifted from quality/convergence.json",
        )

        report = self._report()
        files = report["files"]
        self.assertTrue(all(d.passed for d in check_coverage.evaluate(files, live)))

        # Tamper a *copy* only -- the real control-plane file is never written here. Raising the
        # floors must flip the same report red; dropping them must flip a red report green.
        with tempfile.TemporaryDirectory() as directory:
            strict = Path(directory) / "convergence.json"
            strict.write_text(
                json.dumps(
                    {"coverage": {key: 0.999 for key in check_coverage.THRESHOLD_KEYS.values()}}
                ),
                encoding="utf-8",
            )
            raised = check_coverage.load_thresholds(strict)
            self.assertEqual(set(raised.values()), {0.999})
            self.assertTrue(
                all(not d.passed for d in check_coverage.evaluate(files, raised)),
                "the checker ignored the thresholds it was given",
            )

            lax = Path(directory) / "lax.json"
            lax.write_text(
                json.dumps(
                    {"coverage": {key: 0.0 for key in check_coverage.THRESHOLD_KEYS.values()}}
                ),
                encoding="utf-8",
            )
            bad = self._report(core_missing_lines=900, other_missing_branches=900)["files"]
            self.assertTrue(
                all(
                    d.passed
                    for d in check_coverage.evaluate(bad, check_coverage.load_thresholds(lax))
                )
            )

    def test_unusable_thresholds_are_rejected_rather_than_defaulted(self) -> None:
        # A malformed policy must stop the gate, never fall back to a built-in number.
        with tempfile.TemporaryDirectory() as directory:
            for payload in ({}, {"coverage": {}}, {"coverage": {"overall_statement_min": "90%"}}):
                path = Path(directory) / "convergence.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(check_coverage.CoverageError):
                    check_coverage.load_thresholds(path)

    def test_measured_ratio_is_compared_exactly_not_by_rounded_display(self) -> None:
        # 89.96% renders as "90.0%" at coverage.py's precision=1. If the checker compared the
        # displayed value it would certify a floor the code misses.
        dimension = check_coverage.Dimension("overall_statement", 0.8996, 0.90, 8996, 10000)
        self.assertFalse(dimension.passed)
        self.assertTrue(check_coverage.Dimension("x", 0.90, 0.90, 9000, 10000).passed)

    def test_core_is_matched_by_path_component_not_substring(self) -> None:
        files = {
            "src\\stock_advisor\\domain\\money.py": {},
            "src\\stock_advisor\\services\\domain_rules.py": {},  # not core: name only
            "src\\stock_advisor\\ui\\domain": {},  # not core: it is the file, not a directory
        }
        self.assertEqual(check_coverage.core_files(files), ["src\\stock_advisor\\domain\\money.py"])

    def test_report_without_core_files_cannot_certify_the_policy(self) -> None:
        # Silently measuring "core" as an empty set would divide by zero or, worse, report a
        # vacuous pass. A report that cannot see the core is an error, not a green.
        report = self._report()
        report["files"].pop(self.CORE)
        with tempfile.TemporaryDirectory() as directory:
            code, out, err = self._run(self._write(directory, report))
        self.assertEqual(code, 2)
        self.assertIn("COVERAGE_ERROR", err)
        self.assertIn("domain", err)
        self.assertNotIn("COVERAGE_OK", out)

    def test_report_without_branch_data_is_an_error_not_a_pass(self) -> None:
        # `coverage json` without branch=true reports zero branches; the branch floors would be
        # unmeasurable. That must not read as success.
        report = self._report()
        for entry in report["files"].values():
            entry["summary"]["num_branches"] = 0
            entry["summary"]["missing_branches"] = 0
        with tempfile.TemporaryDirectory() as directory:
            code, _, err = self._run(self._write(directory, report))
        self.assertEqual(code, 2)
        self.assertIn("branch", err)

    def test_missing_or_corrupt_report_reports_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.json"
            code, _, err = self._run(missing)
            self.assertEqual(code, 2)
            self.assertIn("COVERAGE_ERROR", err)
            self.assertIn("not found", err)

            corrupt = Path(directory) / "corrupt.json"
            corrupt.write_text("{not json", encoding="utf-8")
            code, _, err = self._run(corrupt)
            self.assertEqual(code, 2)
            self.assertIn("not valid JSON", err)

            # a well-formed JSON document that is not a coverage report
            wrong = self._write(directory, {"totals": {"percent_covered": 99.0}}, "wrong.json")
            code, _, err = self._run(wrong)
            self.assertEqual(code, 2)
            self.assertIn("files", err)

    def test_malformed_file_entry_is_reported_with_its_name(self) -> None:
        report = self._report()
        report["files"][self.OTHER]["summary"]["missing_lines"] = -5
        with tempfile.TemporaryDirectory() as directory:
            code, _, err = self._run(self._write(directory, report))
        self.assertEqual(code, 2)
        self.assertIn("missing_lines", err)


if __name__ == "__main__":
    unittest.main()
