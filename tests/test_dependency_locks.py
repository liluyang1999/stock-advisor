"""Locks cover direct tools, match each other, and require every wheel hash."""

import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_lock(name):
    text = (ROOT / "requirements" / f"{name}-windows.lock").read_text(encoding="utf-8")
    entries = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:([0-9a-f]{64})", line)
        if not match:
            raise AssertionError(f"Unpinned dependency or missing wheel hash: {line}")
        key = re.sub(r"[-_.]+", "-", match[1]).lower()
        if key in entries:
            raise AssertionError(f"Duplicate lock entry: {key}")
        entries[key] = (match[2], match[3])
    return entries


class DependencyLocksTests(unittest.TestCase):
    def test_build_is_consistent_subset_of_development(self):
        build, dev = read_lock("build"), read_lock("dev")
        self.assertTrue(build)
        for name, value in build.items():
            self.assertEqual(dev[name], value)

    def test_all_direct_versions_are_locked(self):
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dev = read_lock("dev")
        requirements = config["project"]["dependencies"] + [
            item for group in config["dependency-groups"].values() for item in group
        ]
        for requirement in requirements:
            name, version = requirement.split("==")
            name = re.sub(r"\[.*\]", "", name)
            name = re.sub(r"[-_.]+", "-", name).lower()
            self.assertEqual(dev[name][0], version)
