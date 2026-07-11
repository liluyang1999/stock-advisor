from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from _common import LOOP_ROOT, control_plane_digest, load_json, parse_jsonl, validate_against_schema


REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "LOOP_PROTOCOL.md",
    "STATUS.md",
    "loop.json",
    "config.json",
    "governance/CHARTER.md",
    "governance/DEFINITION_OF_DONE.md",
    "baseline/CURRENT_STATE.md",
    "baseline/test-baseline.json",
    "product/REQUIREMENTS.md",
    "product/ACCEPTANCE_CRITERIA.md",
    "product/UI_DESIGN_SYSTEM.md",
    "architecture/TARGET_ARCHITECTURE.md",
    "architecture/core-module-manifest.json",
    "architecture/COMPUTATION_SPECIFICATION.md",
    "architecture/NETWORK_RESILIENCE.md",
    "architecture/PYSIDE6_UI_ARCHITECTURE.md",
    "planning/milestones.json",
    "planning/work-items.json",
    "quality/QUALITY_GATES.md",
    "quality/quality-gates.json",
    "quality/traceability.csv",
    "quality/tk-contract-mapping.csv",
    "state/current.json",
    "state/backlog.json",
    "state/metrics.json",
    "state/gate-runs.jsonl",
    "state/progress.jsonl",
    "state/evidence-index.json",
    "registers/risks.json",
    "registers/decisions.jsonl",
)

REQUIRED_JSON_KEYS: dict[str, tuple[str, ...]] = {
    "loop.json": ("schema_version", "id", "status", "trigger", "goal", "cycle", "memory", "terminal_states", "stop_rules"),
    "config.json": ("schema_version", "project", "target_stack", "ui_tokens", "network_policy", "commands", "quality_policy", "paths"),
    "state/current.json": ("schema_version", "run_id", "objective_id", "phase", "status", "active_milestone_id", "iteration", "baseline_commit", "last_updated"),
    "planning/work-items.json": ("schema_version", "work_items"),
    "planning/milestones.json": ("schema_version", "milestones"),
    "quality/quality-gates.json": ("schema_version", "gates"),
    "state/evidence-index.json": ("schema_version", "evidence"),
    "registers/risks.json": ("schema_version", "risks"),
    "architecture/core-module-manifest.json": ("schema_version", "source_root", "forbidden_import_roots", "modules"),
    "state/backlog.json": ("schema_version", "source", "summary", "ordered_ids", "next_ready"),
    "state/metrics.json": ("schema_version", "engineering", "control_plane", "tests", "coverage", "tooling", "release"),
}


def _ids_from_markdown(relative: str, prefix: str) -> set[str]:
    text = (LOOP_ROOT / relative).read_text(encoding="utf-8")
    return set(re.findall(rf"\b{re.escape(prefix)}-\d{{3}}\b", text))


def _duplicates(values: list[str]) -> set[str]:
    return {value for value in values if values.count(value) > 1}


def _check_acyclic(items: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item_id: str, chain: list[str]) -> None:
        if item_id in visited:
            return
        if item_id in visiting:
            errors.append("work-item cycle: " + " -> ".join(chain + [item_id]))
            return
        visiting.add(item_id)
        for dependency in items[item_id].get("depends_on", []):
            if dependency in items:
                visit(dependency, chain + [item_id])
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in items:
        visit(item_id, [])
    return errors


def _adr_statuses() -> tuple[dict[str, str], list[str]]:
    statuses: dict[str, str] = {}
    errors: list[str] = []
    pattern = re.compile(r"^- 状态：([a-z_]+)$", re.MULTILINE)
    for path in sorted((LOOP_ROOT / "decisions").glob("[0-9][0-9][0-9][0-9]-*.md")):
        adr_id = f"ADR-{path.name[:4]}"
        match = pattern.search(path.read_text(encoding="utf-8"))
        if match is None:
            errors.append(f"{path.relative_to(LOOP_ROOT)} lacks a machine-readable ADR status")
            continue
        statuses[adr_id] = match.group(1)
    return statuses, errors


def _expected_backlog(work_rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_order = ("in_progress", "verifying", "ready", "proposed", "accepted", "blocked", "deferred", "cancelled")
    counts = {status: 0 for status in status_order}
    for row in work_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    summary = {
        status: count
        for status, count in counts.items()
        if count or status in {"verifying", "ready", "proposed", "accepted", "blocked"}
    }
    return {
        "$schema": "../schemas/backlog.schema.json",
        "schema_version": "1.0.0",
        "source": "../planning/work-items.json",
        "summary": summary,
        "ordered_ids": [row["id"] for row in work_rows],
        "next_ready": next((row["id"] for row in work_rows if row["status"] == "ready"), None),
        "note": "planning/work-items.json is authoritative; this file is a queue projection",
    }


def validate() -> list[str]:
    errors: list[str] = []

    for relative in REQUIRED_FILES:
        if not (LOOP_ROOT / relative).exists():
            errors.append(f"missing required file: {relative}")

    json_count = 0
    schema_document_count = 0
    for path in sorted(LOOP_ROOT.rglob("*.json")):
        json_count += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON {path.relative_to(LOOP_ROOT)}: {exc}")
            continue
        relative_path = path.relative_to(LOOP_ROOT)
        schema_reference = payload.get("$schema") if isinstance(payload, dict) else None
        operational = relative_path.parts[0] not in {"schemas", "templates"}
        if operational and (not isinstance(schema_reference, str) or not schema_reference.startswith(("./", "../"))):
            errors.append(f"operational JSON lacks a local schema: {relative_path}")
            continue
        if not isinstance(schema_reference, str) or not schema_reference.startswith(("./", "../")):
            continue
        schema_path = (path.parent / schema_reference).resolve()
        if LOOP_ROOT.resolve() not in schema_path.parents:
            errors.append(f"schema path escapes loop root: {path.relative_to(LOOP_ROOT)} -> {schema_reference}")
            continue
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot load schema for {path.relative_to(LOOP_ROOT)}: {exc}")
            continue
        if not isinstance(schema, dict):
            errors.append(f"schema must be an object: {schema_path.relative_to(LOOP_ROOT)}")
            continue
        schema_document_count += 1
        for issue in validate_against_schema(payload, schema):
            errors.append(f"schema {path.relative_to(LOOP_ROOT)}: {issue}")

    for relative, keys in REQUIRED_JSON_KEYS.items():
        path = LOOP_ROOT / relative
        if not path.exists():
            continue
        try:
            payload = load_json(relative)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            errors.append(f"{relative} must contain an object")
            continue
        for key in keys:
            if key not in payload:
                errors.append(f"{relative} missing key: {key}")

    jsonl_entries = 0
    for path in sorted(LOOP_ROOT.rglob("*.jsonl")):
        try:
            jsonl_entries += len(parse_jsonl(path))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"invalid JSONL {path.relative_to(LOOP_ROOT)}: {exc}")

    requirements = _ids_from_markdown("product/REQUIREMENTS.md", "REQ")
    acceptance = _ids_from_markdown("product/ACCEPTANCE_CRITERIA.md", "AC")
    tests_payload = load_json("quality/test-catalog.json")
    test_rows = tests_payload.get("tests", [])
    test_id_list = [row.get("id", "") for row in test_rows]
    if duplicate_ids := _duplicates(test_id_list):
        errors.append(f"duplicate test ids: {sorted(duplicate_ids)}")
    test_ids = {row["id"] for row in test_rows if row.get("id")}

    work_payload = load_json("planning/work-items.json")
    work_rows = work_payload.get("work_items", [])
    work_ids_list = [row.get("id", "") for row in work_rows]
    if duplicate_ids := _duplicates(work_ids_list):
        errors.append(f"duplicate work-item ids: {sorted(duplicate_ids)}")
    work_items = {row["id"]: row for row in work_rows if row.get("id")}
    for item_id, row in work_items.items():
        for dependency in row.get("depends_on", []):
            if dependency not in work_items:
                errors.append(f"{item_id} references unknown dependency {dependency}")
        for requirement in row.get("requirements", []):
            if requirement not in requirements:
                errors.append(f"{item_id} references unknown requirement {requirement}")
        for criterion in row.get("acceptance", []):
            if criterion not in acceptance:
                errors.append(f"{item_id} references unknown acceptance criterion {criterion}")
        for test_id in row.get("tests", []):
            if test_id not in test_ids:
                errors.append(f"{item_id} references unknown test {test_id}")
    errors.extend(_check_acyclic(work_items))
    covered_acceptance = {
        criterion for row in work_items.values() for criterion in row.get("acceptance", [])
    }
    if missing_acceptance := acceptance - covered_acceptance:
        errors.append(f"acceptance criteria not mapped to work items: {sorted(missing_acceptance)}")

    milestones_payload = load_json("planning/milestones.json")
    milestone_rows = milestones_payload.get("milestones", [])
    milestone_ids = {row["id"] for row in milestone_rows}
    for row in milestone_rows:
        for work_id in row.get("work_items", []):
            if work_id not in work_items:
                errors.append(f"{row['id']} references unknown work item {work_id}")
        for dependency in row.get("depends_on", []):
            if dependency not in milestone_ids:
                errors.append(f"{row['id']} references unknown milestone {dependency}")
    for item_id, row in work_items.items():
        if row.get("milestone") not in milestone_ids:
            errors.append(f"{item_id} references unknown milestone {row.get('milestone')}")

    graph_edges = {
        tuple(edge) for edge in load_json("planning/dependency-graph.json").get("edges", [])
    }
    expected_edges = {
        (dependency, item_id)
        for item_id, row in work_items.items()
        for dependency in row.get("depends_on", [])
    }
    if graph_edges != expected_edges:
        errors.append("planning/dependency-graph.json differs from work-item dependencies")

    backlog = load_json("state/backlog.json")
    if backlog != _expected_backlog(work_rows):
        errors.append("state/backlog.json differs from the authoritative work-item projection")

    current = load_json("state/current.json")
    active_work_item_id = current.get("active_work_item_id")
    if active_work_item_id not in work_items:
        errors.append("state/current.json active_work_item_id is unknown")
    elif work_items[active_work_item_id].get("status") not in {"ready", "in_progress", "verifying"}:
        errors.append("active work item must be ready, in_progress or verifying")
    active_milestone_id = current.get("active_milestone_id")
    if active_milestone_id not in milestone_ids:
        errors.append("state/current.json active_milestone_id is unknown")
    else:
        active_milestone = next(row for row in milestone_rows if row["id"] == active_milestone_id)
        if active_milestone.get("status") not in {"in_progress", "verifying"}:
            errors.append("active milestone must be in_progress or verifying")
    actual_in_progress = sorted(
        item_id for item_id, row in work_items.items() if row.get("status") in {"in_progress", "verifying"}
    )
    if sorted(current.get("in_progress_ids", [])) != actual_in_progress:
        errors.append("state/current.json in_progress_ids differs from work-item statuses")
    accepted_work_ids = sorted(item_id for item_id, row in work_items.items() if row.get("status") == "accepted")
    if sorted(current.get("completed_ids", [])) != accepted_work_ids:
        errors.append("state/current.json completed_ids differs from accepted work items")

    loop_contract = load_json("loop.json")
    if accepted_work_ids and loop_contract.get("status") == "initialized":
        errors.append("loop contract cannot remain initialized after accepted work items exist")
    terminal_state = current.get("terminal_state")
    terminal_states = set(loop_contract.get("terminal_states", []))
    if terminal_state is not None and terminal_state not in terminal_states:
        errors.append("state/current.json terminal_state is not defined by loop.json")
    status = current.get("status")
    if status in {"initialized", "active", "verifying"} and terminal_state is not None:
        errors.append("non-terminal run status requires terminal_state=null")
    if status == "complete" and terminal_state != "success":
        errors.append("complete run status requires terminal_state=success")

    adr_statuses, adr_errors = _adr_statuses()
    errors.extend(adr_errors)
    decision_records = parse_jsonl(LOOP_ROOT / "registers" / "decisions.jsonl")
    registered_statuses: dict[str, str] = {}
    for record in decision_records:
        if record.get("id"):
            registered_statuses[record["id"]] = record.get("status", "")
    if adr_statuses != registered_statuses:
        errors.append("ADR Markdown statuses differ from the latest decision register entries")
    proposed_adrs = sorted(adr_id for adr_id, adr_status in adr_statuses.items() if adr_status == "proposed")
    if sorted(current.get("pending_decision_ids", [])) != proposed_adrs:
        errors.append("state/current.json pending_decision_ids differs from proposed ADRs")

    risks_payload = load_json("registers/risks.json")
    for risk in risks_payload.get("risks", []):
        expected = risk.get("probability", 0) * risk.get("impact", 0)
        if risk.get("score") != expected:
            errors.append(f"{risk.get('id')} score must equal probability * impact")

    evidence_payload = load_json("state/evidence-index.json")
    evidence_ids = [row.get("id", "") for row in evidence_payload.get("evidence", [])]
    evidence_by_id = {row["id"]: row for row in evidence_payload.get("evidence", []) if row.get("id")}
    if duplicate_ids := _duplicates(evidence_ids):
        errors.append(f"duplicate evidence ids: {sorted(duplicate_ids)}")
    for record in evidence_payload.get("evidence", []):
        artifact = LOOP_ROOT / record.get("artifact_path", "")
        if not artifact.is_file():
            errors.append(f"{record.get('id')} artifact missing: {record.get('artifact_path')}")
        elif record.get("sha256"):
            actual_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if actual_hash.lower() != str(record["sha256"]).lower():
                errors.append(f"{record.get('id')} artifact hash mismatch")
        if record.get("work_item_id") not in work_items:
            errors.append(f"{record.get('id')} references unknown work item")
        for requirement in record.get("requirement_ids", []):
            if requirement not in requirements:
                errors.append(f"{record.get('id')} references unknown requirement {requirement}")
        if record.get("record_version") == "2.0.0":
            required_v2 = {
                "command",
                "cwd",
                "dirty_worktree",
                "started_at",
                "finished_at",
                "implemented_by",
                "verified_by",
                "control_plane_sha256",
            }
            missing = sorted(key for key in required_v2 if record.get(key) in {None, ""})
            if missing:
                errors.append(f"{record.get('id')} v2 evidence missing fields: {missing}")
            if record.get("implemented_by") == record.get("verified_by"):
                errors.append(f"{record.get('id')} v2 evidence requires an independent verifier")
            if record.get("control_plane_sha256") != control_plane_digest():
                errors.append(f"{record.get('id')} control-plane digest differs from the current tree")

    for item_id, row in work_items.items():
        if row.get("status") != "accepted":
            continue
        evidence_for_item = row.get("evidence_ids", [])
        if not evidence_for_item:
            errors.append(f"accepted work item {item_id} has no evidence")
        for evidence_id in evidence_for_item:
            if evidence_id not in evidence_by_id:
                errors.append(f"accepted work item {item_id} references unknown evidence {evidence_id}")
        if "AC-000" in row.get("acceptance", []):
            independent = any(
                evidence_by_id.get(evidence_id, {}).get("implemented_by")
                and evidence_by_id.get(evidence_id, {}).get("verified_by")
                and evidence_by_id[evidence_id]["implemented_by"] != evidence_by_id[evidence_id]["verified_by"]
                for evidence_id in evidence_for_item
            )
            if not independent:
                errors.append(f"accepted control-plane work item {item_id} lacks independent verification evidence")

    gate_runs = parse_jsonl(LOOP_ROOT / "state" / "gate-runs.jsonl")
    gate_ids = [record.get("id", "") for record in gate_runs]
    if duplicate_ids := _duplicates(gate_ids):
        errors.append(f"duplicate gate-run ids: {sorted(duplicate_ids)}")
    gate_by_id = {record["id"]: record for record in gate_runs if record.get("id")}
    latest_gate_run_id = current.get("latest_gate_run_id")
    if latest_gate_run_id not in gate_by_id:
        errors.append("state/current.json latest_gate_run_id is absent from state/gate-runs.jsonl")
    else:
        latest_gate = gate_by_id[latest_gate_run_id]
        if latest_gate.get("evidence_id") not in evidence_by_id:
            errors.append("latest gate run references unknown evidence")

    metrics = load_json("state/metrics.json")
    engineering = metrics.get("engineering", {})
    expected_engineering = {
        "requirements_total": len(requirements),
        "acceptance_total": len(acceptance),
        "work_items_total": len(work_items),
        "work_items_accepted": len(accepted_work_ids),
    }
    for key, expected in expected_engineering.items():
        if engineering.get(key) != expected:
            errors.append(f"state/metrics.json engineering.{key} must equal {expected}")
    quality_summary = current.get("quality_summary", {})
    test_metrics = metrics.get("tests", {})
    if quality_summary.get("tests_total") != test_metrics.get("methods"):
        errors.append("current quality_summary.tests_total differs from metrics tests.methods")
    if quality_summary.get("tests_passed") != test_metrics.get("passed"):
        errors.append("current quality_summary.tests_passed differs from metrics tests.passed")
    if quality_summary.get("release_ready") != metrics.get("release", {}).get("ready"):
        errors.append("current release readiness differs from metrics")

    config = load_json("config.json")
    if config.get("target_stack", {}).get("gui") != "PySide6":
        errors.append("config target GUI must be PySide6")
    if config.get("target_stack", {}).get("runtime_font") != "Microsoft YaHei":
        errors.append("config runtime font must be Microsoft YaHei")
    if config.get("network_policy", {}).get("fabricated_fallbacks_allowed") is not False:
        errors.append("fabricated fallbacks must be disabled")
    if not str(config.get("network_policy", {}).get("target_transport", "")).startswith("QNetworkAccessManager"):
        errors.append("target network transport must be an explicit QNetworkAccessManager contract")

    loop_gate = next(
        (gate for gate in load_json("quality/quality-gates.json").get("gates", []) if gate.get("id") == "G-LOOP"),
        None,
    )
    expected_loop_commands = {
        ("python", "loop/scripts/validate_loop.py"),
        ("python", "loop/scripts/check_traceability.py"),
        ("python", "loop/scripts/render_status.py", "--check"),
        ("python", "loop/scripts/render_backlog.py", "--check"),
        ("python", "loop/scripts/check_core_boundaries.py"),
        ("python", "-m", "unittest", "discover", "-s", "loop/tests"),
    }
    if loop_gate is None or {tuple(command) for command in loop_gate.get("commands", [])} != expected_loop_commands:
        errors.append("G-LOOP commands differ from the mandatory control-plane gate")

    control_metrics = metrics.get("control_plane", {})
    if control_metrics.get("schema_documents_validated") != schema_document_count:
        errors.append("metrics schema_documents_validated differs from validator coverage")
    if control_metrics.get("requirements_traced") != len(requirements):
        errors.append("metrics requirements_traced differs from requirement count")

    validate.stats = {
        "json": json_count,
        "schema_documents": schema_document_count,
        "jsonl_entries": jsonl_entries,
        "requirements": len(requirements),
        "acceptance": len(acceptance),
        "work_items": len(work_items),
    }
    return errors


validate.stats = {}  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the loop engineering control plane.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    errors = validate()
    if errors:
        for error in errors:
            print(f"LOOP_VALIDATION_ERROR {error}", file=sys.stderr)
        return 1
    if not args.quiet:
        stats = validate.stats  # type: ignore[attr-defined]
        print(
            "LOOP_VALIDATION_OK "
            f"json={stats['json']} schema_documents={stats['schema_documents']} "
            f"jsonl_entries={stats['jsonl_entries']} "
            f"requirements={stats['requirements']} acceptance={stats['acceptance']} "
            f"work_items={stats['work_items']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
