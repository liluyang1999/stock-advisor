from __future__ import annotations

import argparse
import csv
import re
import sys

from _common import LOOP_ROOT, load_json

REQUIRED_COLUMNS = {
    "requirement_id",
    "priority",
    "statement",
    "design_refs",
    "adr_refs",
    "work_item_ids",
    "acceptance_criteria",
    "test_ids",
    "evidence_ids",
    "status",
    "owner",
    "last_verified_at",
    "notes",
}

TK_CONTRACT_COLUMNS = ("contract_id", "area", "disposition", "replacement_test_id", "notes")
TK_CONTRACT_DISPOSITIONS = {"pure_preserved", "qt_replaced", "approved_retired"}
# Documented target, not enforced here: WI-002 ("映射 187 个 Tk 行为合同") will populate
# tk-contract-mapping.csv with exactly 187 rows (116 legacy loop/test_gui_layout.py rows
# + 71 legacy loop/test_ui_polish.py rows, per the pre-mapping inventory this file used to
# carry as two aggregate placeholder rows). Until WI-002 runs, the file intentionally
# stays a header-only stub -- zero data rows -- because every disposition value is a
# terminal classification (pure_preserved/qt_replaced/approved_retired) and no row should
# claim one before the real classification work happens.
TK_CONTRACT_EXPECTED_ROW_COUNT = 187


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def _tk_contract_mapping_errors(
    fieldnames: tuple[str, ...], rows: list[dict[str, str]]
) -> list[str]:
    if tuple(fieldnames) != TK_CONTRACT_COLUMNS:
        got = ",".join(fieldnames)
        return [
            f"tk-contract-mapping.csv header must be {','.join(TK_CONTRACT_COLUMNS)}, got {got}"
        ]
    errors: list[str] = []
    for index, row in enumerate(rows):
        label = (row.get("contract_id") or "").strip() or f"row {index}"
        disposition = (row.get("disposition") or "").strip()
        if disposition not in TK_CONTRACT_DISPOSITIONS:
            errors.append(
                f"tk-contract-mapping.csv {label} has invalid disposition {disposition!r}"
            )
        if disposition == "qt_replaced" and not (row.get("replacement_test_id") or "").strip():
            errors.append(
                f"tk-contract-mapping.csv {label} is qt_replaced but has no replacement_test_id"
            )
    return errors


def check_tk_contract_mapping() -> list[str]:
    path = LOOP_ROOT / "quality/tk-contract-mapping.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or [])
        rows = list(reader)
    return _tk_contract_mapping_errors(fieldnames, rows)


def check(release: bool = False) -> list[str]:
    errors: list[str] = []
    requirements_text = (LOOP_ROOT / "product/REQUIREMENTS.md").read_text(encoding="utf-8")
    requirement_ids = set(re.findall(r"\bREQ-\d{3}\b", requirements_text))
    work_ids = {row["id"] for row in load_json("planning/work-items.json")["work_items"]}
    test_ids = {row["id"] for row in load_json("quality/test-catalog.json")["tests"]}
    work_rows = load_json("planning/work-items.json")["work_items"]
    wi_requirements = {row["id"]: set(row.get("requirements", [])) for row in work_rows}
    evidence_ids = {row["id"] for row in load_json("state/evidence-index.json")["evidence"]}

    path = LOOP_ROOT / "quality/traceability.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        if missing := REQUIRED_COLUMNS - columns:
            return [f"traceability.csv missing columns: {sorted(missing)}"]
        rows = list(reader)

    row_ids = [row["requirement_id"].strip() for row in rows]
    if len(row_ids) != len(set(row_ids)):
        errors.append("traceability.csv contains duplicate requirement rows")
    missing_rows = requirement_ids - set(row_ids)
    extra_rows = set(row_ids) - requirement_ids
    if missing_rows:
        errors.append(f"requirements missing trace rows: {sorted(missing_rows)}")
    if extra_rows:
        errors.append(f"unknown requirement rows: {sorted(extra_rows)}")

    for row in rows:
        req_id = row["requirement_id"].strip()
        for field in (
            "priority",
            "statement",
            "design_refs",
            "work_item_ids",
            "test_ids",
            "status",
            "owner",
        ):
            if not row[field].strip():
                errors.append(f"{req_id} missing {field}")
        for work_id in _split(row["work_item_ids"]):
            if work_id not in work_ids:
                errors.append(f"{req_id} references unknown work item {work_id}")
        for work_id in _split(row["work_item_ids"]):
            if work_id in wi_requirements and req_id not in wi_requirements[work_id]:
                errors.append(
                    f"{req_id} trace row names {work_id} but that work item does not list {req_id}"
                )
        for test_id in _split(row["test_ids"]):
            if test_id not in test_ids:
                errors.append(f"{req_id} references unknown test {test_id}")
        for evidence_id in _split(row["evidence_ids"]):
            if evidence_id not in evidence_ids:
                errors.append(f"{req_id} references unknown evidence {evidence_id}")
        status = row["status"].strip()
        if status in {"verified", "accepted"} and not _split(row["evidence_ids"]):
            errors.append(f"{req_id} is {status} without evidence")
        if release and status not in {"verified", "accepted"}:
            errors.append(f"{req_id} is not release-verified: {status}")
        if release and not _split(row["evidence_ids"]):
            errors.append(f"{req_id} has no release evidence")

    row_by_req = {r["requirement_id"].strip(): r for r in rows}
    for work_id, reqs in wi_requirements.items():
        for req in reqs:
            trace_row = row_by_req.get(req)
            if trace_row and work_id not in _split(trace_row["work_item_ids"]):
                errors.append(
                    f"{req} is owned by {work_id} in work-items.json but its trace row omits {work_id}"
                )

    acceptance_text = (LOOP_ROOT / "product/ACCEPTANCE_CRITERIA.md").read_text(encoding="utf-8")
    acceptance_ids = set(re.findall(r"\bAC-\d{3}\b", acceptance_text))
    traced_acceptance = {ac for row in rows for ac in _split(row.get("acceptance_criteria", ""))}
    if missing := acceptance_ids - traced_acceptance:
        errors.append(f"acceptance criteria not traced: {sorted(missing)}")
    for row in rows:
        for ac in _split(row.get("acceptance_criteria", "")):
            if ac not in acceptance_ids:
                errors.append(f"{row['requirement_id'].strip()} references unknown acceptance {ac}")

    check.stats = {"requirements": len(requirement_ids), "rows": len(rows)}
    return errors


check.stats = {}  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check requirement traceability.")
    parser.add_argument(
        "--release", action="store_true", help="Require every row to be verified with evidence."
    )
    args = parser.parse_args(argv)
    errors = check(release=args.release) + check_tk_contract_mapping()
    if errors:
        for error in errors:
            print(f"TRACEABILITY_ERROR {error}", file=sys.stderr)
        return 1
    print(f"TRACEABILITY_OK {check.stats['rows']}/{check.stats['requirements']}")  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
