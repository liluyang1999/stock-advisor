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
    "test_ids",
    "evidence_ids",
    "status",
    "owner",
    "last_verified_at",
    "notes",
}


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def check(release: bool = False) -> list[str]:
    errors: list[str] = []
    requirements_text = (LOOP_ROOT / "product/REQUIREMENTS.md").read_text(encoding="utf-8")
    requirement_ids = set(re.findall(r"\bREQ-\d{3}\b", requirements_text))
    work_ids = {row["id"] for row in load_json("planning/work-items.json")["work_items"]}
    test_ids = {row["id"] for row in load_json("quality/test-catalog.json")["tests"]}
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
        for field in ("priority", "statement", "design_refs", "work_item_ids", "test_ids", "status", "owner"):
            if not row[field].strip():
                errors.append(f"{req_id} missing {field}")
        for work_id in _split(row["work_item_ids"]):
            if work_id not in work_ids:
                errors.append(f"{req_id} references unknown work item {work_id}")
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

    check.stats = {"requirements": len(requirement_ids), "rows": len(rows)}
    return errors


check.stats = {}  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check requirement traceability.")
    parser.add_argument("--release", action="store_true", help="Require every row to be verified with evidence.")
    args = parser.parse_args(argv)
    errors = check(release=args.release)
    if errors:
        for error in errors:
            print(f"TRACEABILITY_ERROR {error}", file=sys.stderr)
        return 1
    print(f"TRACEABILITY_OK {check.stats['rows']}/{check.stats['requirements']}")  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

