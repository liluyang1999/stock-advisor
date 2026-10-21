"""Build and verify the Windows delivery in a hash-locked, disposable environment."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import build_exe
import make_release_manifest

ROOT = Path(__file__).resolve().parents[1]


def checked_directory(path: Path, root: Path) -> Path:
    """Validate every existing component before creating or removing build state."""
    root = root.resolve()
    absolute = Path(os.path.abspath(path))
    if not absolute.is_relative_to(root) or absolute == root:
        raise RuntimeError(f"Unmanaged directory: {path}")
    for parent in (absolute, *absolute.parents):
        if parent == root:
            break
        if parent.is_symlink() or parent.is_junction():
            raise RuntimeError(f"Linked directory refused: {parent}")
    return absolute


@contextlib.contextmanager
def delivery_transaction(dist: Path, build: Path) -> Iterator[None]:
    """Keep the last working bundle even if rollback itself fails."""
    checked_directory(dist, build.parent)
    checked_directory(build, build.parent)
    directory = Path(tempfile.mkdtemp(prefix="previous-delivery-", dir=build))
    previous = directory / "dist"
    try:
        if dist.exists():
            dist.rename(previous)
    except BaseException:
        directory.rmdir()
        raise
    try:
        yield
    except BaseException:
        try:
            checked_directory(dist, build.parent)
            if dist.exists():
                shutil.rmtree(dist)
            if previous.exists():
                previous.rename(dist)
        except OSError as recovery_error:
            raise RuntimeError(
                f"Recovery blocked; previous delivery preserved at {previous}"
            ) from recovery_error
        directory.rmdir()
        raise
    else:
        shutil.rmtree(directory)


def smoke_environment(directory: Path) -> dict[str, str]:
    env = {
        k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "QT_", "QML"))
    }
    system = env.get("SystemRoot", env.get("SYSTEMROOT", r"C:\Windows"))
    env.update(
        PATH=os.pathsep.join((str(Path(system) / "System32"), system)),
        STOCK_ADVISOR_CONFIG=str(directory / "config.json"),
        TEMP=str(directory),
        TMP=str(directory),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
    )
    return env


def verify_portable(dist: Path, scratch: Path) -> dict:
    """Run the copied executable with no developer Python/Qt on PATH."""
    relocated = scratch / "独立运行 空格路径"
    shutil.copytree(dist, relocated)
    if make_release_manifest._verify(relocated) != 0:
        raise RuntimeError("Relocated delivery failed integrity verification")
    profile = scratch / "isolated-profile"
    profile.mkdir()
    env = smoke_environment(profile)
    executable = relocated / "股市锦囊" / "股市锦囊.exe"
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    results = {}
    for flag in ("--self-test", "--smoke-test", "--smoke-test"):
        result = subprocess.run(
            [str(executable), flag],
            cwd=profile,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            startupinfo=startup,
        )
        marker = "SELF_TEST_OK" if flag == "--self-test" else "GUI_SMOKE_OK"
        if result.returncode or marker not in result.stdout or result.stderr.strip():
            raise RuntimeError(
                f"{flag} failed: exit={result.returncode}\n{result.stdout}\n{result.stderr}"
            )
        results.setdefault(flag, []).append(result.stdout.strip())
    if make_release_manifest._verify(relocated) != 0:
        raise RuntimeError("Application modified its delivery directory")
    return {"relocated": True, "developer_path_removed": True, "checks": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheelhouse",
        type=Path,
        help="Use a pre-downloaded, hash-verified wheel directory offline",
    )
    args = parser.parse_args(argv)
    if (
        sys.platform != "win32"
        or platform.machine().lower() not in {"amd64", "x86_64"}
        or sys.version_info[:2] != (3, 14)
    ):
        print("PACKAGE_REFUSED requires Windows x64 and Python 3.14", file=sys.stderr)
        return 2
    if not build_exe._source_is_clean():
        print("PACKAGE_REFUSED commit source changes before building", file=sys.stderr)
        return 2
    dist, build = ROOT / "dist", ROOT / "build"
    if dist.exists() and make_release_manifest._verify() != 0:
        print(
            "PACKAGE_REFUSED existing dist is not verified; preserve and inspect it first",
            file=sys.stderr,
        )
        return 2
    try:
        checked_directory(build, ROOT)
        checked_directory(dist, ROOT)
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="package-env-", dir=build) as directory:
            scratch = Path(directory)
            env_root = scratch / "venv"
            env = dict(
                os.environ,
                PYTHONDONTWRITEBYTECODE="1",
                PYTHONUTF8="1",
                TEMP=str(scratch),
                TMP=str(scratch),
                PYINSTALLER_CONFIG_DIR=str(scratch / "pyinstaller-cache"),
            )
            for name in ("PYTHONPATH", "PYTHONHOME"):
                env.pop(name, None)
            subprocess.run(
                [sys.executable, "-I", "-m", "venv", str(env_root)],
                cwd=ROOT,
                env=env,
                check=True,
                timeout=180,
            )
            python = env_root / "Scripts" / "python.exe"
            install = [
                str(python),
                "-I",
                "-m",
                "pip",
                "--isolated",
                "--disable-pip-version-check",
                "install",
                "--no-cache-dir",
                "--require-hashes",
                "--only-binary=:all:",
                "--retries",
                "2",
                "--timeout",
                "30",
                "-r",
                str(ROOT / "requirements" / "build-windows.lock"),
            ]
            if args.wheelhouse:
                install += ["--no-index", "--find-links", str(args.wheelhouse.resolve())]
            else:
                install += ["--index-url", "https://pypi.org/simple"]
            subprocess.run(install, cwd=ROOT, env=env, check=True, timeout=900)
            subprocess.run(
                [str(python), "-I", "-m", "pip", "check"], cwd=ROOT, env=env, check=True, timeout=60
            )
            with delivery_transaction(dist, build):
                for script in ("build_exe.py", "make_release_manifest.py"):
                    subprocess.run(
                        [str(python), "-B", str(ROOT / "scripts" / script)],
                        cwd=ROOT,
                        env=env,
                        check=True,
                        timeout=600,
                    )
                result = verify_portable(dist, scratch)
                result["commit"] = build_exe._git_commit()
                (build / "package-verification.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
        print(
            "PACKAGE_OK isolated build, hashes, offline self-test and relocated native GUI passed"
        )
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"PACKAGE_FAILED {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
