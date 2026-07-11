from __future__ import annotations

import ast
import sys
from pathlib import Path

from _common import LOOP_ROOT, load_json


def _import_targets(path: Path, package_name: str) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    internal: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                roots.add(parts[0])
                if len(parts) > 1 and parts[0] == package_name:
                    internal.add(parts[1])
        elif isinstance(node, ast.ImportFrom):
            parts = node.module.split(".") if node.module else []
            if node.level > 0:
                if parts:
                    internal.add(parts[0])
                else:
                    internal.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif parts:
                roots.add(parts[0])
                if parts[0] == package_name:
                    if len(parts) > 1:
                        internal.add(parts[1])
                    else:
                        internal.update(alias.name.split(".", 1)[0] for alias in node.names)
    return roots, internal


def check() -> list[str]:
    manifest = load_json("architecture/core-module-manifest.json")
    source_root = (LOOP_ROOT / manifest["source_root"]).resolve()
    forbidden = set(manifest["forbidden_import_roots"])
    forbidden_internal = set(manifest["forbidden_internal_modules"])
    package_name = manifest["package_name"]
    errors: list[str] = []
    seen: set[str] = set()
    for row in manifest["modules"]:
        relative = row["path"]
        if relative in seen:
            errors.append(f"duplicate protected module: {relative}")
            continue
        seen.add(relative)
        path = (source_root / relative).resolve()
        if source_root not in path.parents:
            errors.append(f"protected module escapes source root: {relative}")
            continue
        if not path.is_file():
            errors.append(f"protected module missing: {relative}")
            continue
        try:
            import_roots, internal_modules = _import_targets(path, package_name)
            blocked = sorted(import_roots & forbidden)
            blocked_internal = sorted(internal_modules & forbidden_internal)
        except (OSError, SyntaxError) as exc:
            errors.append(f"cannot inspect {relative}: {exc}")
            continue
        if blocked:
            errors.append(f"{relative} imports forbidden roots: {blocked}")
        if blocked_internal:
            errors.append(f"{relative} imports forbidden internal modules: {blocked_internal}")
    check.stats = {
        "modules": len(seen),
        "forbidden_roots": len(forbidden),
        "forbidden_internal": len(forbidden_internal),
    }
    return errors


check.stats: dict[str, int] = {}


def main() -> int:
    errors = check()
    if errors:
        for error in errors:
            print(f"CORE_BOUNDARY_ERROR {error}", file=sys.stderr)
        return 1
    print(
        "CORE_BOUNDARY_OK "
        f"modules={check.stats['modules']} forbidden_roots={check.stats['forbidden_roots']} "
        f"forbidden_internal={check.stats['forbidden_internal']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
