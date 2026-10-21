"""发布元数据生成器：SBOM、第三方许可通知、产物哈希清单（WI-025 / REQ-029 / REQ-030 / AC-010）。

`build_exe.py` 产出交付物本身，本脚本产出"证明交付物是什么"的那一层，即 RELEASE_PLAN.md 要求的
SHA-256、SBOM 与依赖许可清单、构建元数据。两者分开是因为职责不同：构建可以重跑，而清单必须描述
磁盘上此刻这一份产物——本脚本读取应用目录、生成配套元数据，从不触发构建。

许可证是硬门禁而不是提示：产品以 LGPL-3.0 选项分发 Qt，第 4 条要求随附许可证正文并让用户能用自己
的 Qt 重新链接。缺正文就是不合规，因此正文缺失时本脚本照常写出其余产物（便于审阅），但以非零码退出
并在清单里把 `license_compliance.complete` 记成 false——不给"看起来绿了"的机会。

用法：
    python scripts/build_exe.py            # 先构建
    python scripts/make_release_manifest.py
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # scripts/ 的上一级才是仓库根
DIST_DIR = PROJECT_ROOT / "dist"
APP_DIR = DIST_DIR / "股市锦囊"
LICENSES_SRC = PROJECT_ROOT / "licenses"
LICENSES_OUT = DIST_DIR / "licenses"
MANIFEST_PATH = DIST_DIR / "RELEASE_MANIFEST.json"
SBOM_PATH = DIST_DIR / "SBOM.json"
NOTICES_PATH = DIST_DIR / "THIRD_PARTY_NOTICES.md"

# 随产品分发的运行期第三方组件。开发期工具（ruff/pyright/pytest/PyInstaller）不进 SBOM 的
# 交付集合。PyInstaller 的 bootloader 和 Python 运行时另记在 RUNTIME_INVENTORY.json；
# 构建工具链记在 build_metadata 中。这里只列 Python 发行包，不冒充静态库的完整 SBOM。
SHIPPED_DISTRIBUTIONS = ("PySide6-Essentials", "shiboken6")

# 选定的许可证选项（PySide6 是三选一：LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only）。
# LGPL-3.0 正文本身声明它并入 GPL-3.0 的条款，所以两份正文都必须随附。
CHOSEN_LICENSE = "LGPL-3.0-only"
REQUIRED_LICENSE_TEXTS = {
    "LGPL-3.0.txt": "https://www.gnu.org/licenses/lgpl-3.0.txt",
    "GPL-3.0.txt": "https://www.gnu.org/licenses/gpl-3.0.txt",
}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not APP_DIR.is_dir():
        print(f"未找到交付目录 {APP_DIR}；请先运行 python scripts/build_exe.py", file=sys.stderr)
        return 2
    if "--verify" in args:
        return _verify()

    components = _collect_components()
    licenses, missing = _stage_license_texts()

    SBOM_PATH.write_text(
        json.dumps(_build_sbom(components), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    NOTICES_PATH.write_text(_build_notices(components, licenses, missing), encoding="utf-8")
    artifacts = _hash_artifacts()

    manifest: dict[str, Any] = {
        "schema_version": "1.1",
        "product": "股市锦囊",
        "version": _app_version(),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": _source_metadata(),
        "build_metadata": _build_metadata(),
        "license_compliance": {
            "chosen_license": CHOSEN_LICENSE,
            "complete": not missing,
            "texts_present": sorted(licenses),
            "texts_missing": sorted(missing),
            "relink_note": (
                "Qt 以独立 DLL 形式放在应用目录（ADR-0004 onedir），用户可用自建 Qt 替换后重新"
                "链接，以此满足 LGPL-3.0 第 4(d) 条"
            ),
        },
        "components": components,
        "artifacts": artifacts,
        "rollback": {
            "policy": "loop/planning/ROLLBACK_PLAN.md 第 4 级：回退到上一个带哈希与 self-test 证据的交付物",
            "restore": "保留本文件与对应的 dist/ 压缩包；回滚即用上一版清单里的哈希校验后替换应用目录",
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    total = sum(a["bytes"] for a in artifacts["files"])
    print(f"SBOM:      {SBOM_PATH}  ({len(components)} 个随产品分发的组件)")
    print(f"通知:      {NOTICES_PATH}")
    print(f"许可正文:  {LICENSES_OUT}  ({len(licenses)} 份)")
    print(
        f"清单:      {MANIFEST_PATH}  ({len(artifacts['files'])} 个文件, {total / 1048576:.1f} MiB)"
    )
    print(f"应用目录 SHA-256(合并): {artifacts['tree_sha256']}")
    source = manifest["source"]
    blocked = False
    if missing:
        print(
            "RELEASE_MANIFEST_INCOMPLETE 缺少许可证正文: "
            + ", ".join(f"{n} <- {REQUIRED_LICENSE_TEXTS[n]}" for n in sorted(missing)),
            file=sys.stderr,
        )
        blocked = True
    if not source["build_matches_repo"]:
        print(
            "RELEASE_MANIFEST_STALE 产物构建自 "
            f"{source['build_commit'] or '未知提交（缺 BUILD_INFO.json）'}，"
            f"仓库现在在 {source['repo_commit']}；请重新构建后再出清单",
            file=sys.stderr,
        )
        blocked = True
    if any(not component.get("installed") for component in components):
        print("RELEASE_MANIFEST_INCOMPLETE 无法确认运行期组件版本", file=sys.stderr)
        blocked = True
    if blocked:
        return 1
    if _verify() != 0:
        return 1
    print(f"RELEASE_MANIFEST_OK commit={source['commit']}")
    return 0


def _verify(dist_dir: Path | None = None) -> int:
    """把磁盘上的 dist/ 重新哈希一遍，和清单比对——回滚演练与到货校验都用这条路径。

    ROLLBACK_PLAN 第 4 级是"回退到上一个有哈希和 self-test 证据的 EXE"。光有哈希不够，还得有一条
    能把哈希用起来的命令，否则回滚永远停留在纸面。三类偏差分别报告：内容变了、少了文件、多了文件——
    多出来的文件同样是偏差，因为交付目录必须只含批准产物。
    """
    root = DIST_DIR if dist_dir is None else dist_dir
    app_dir = root / APP_DIR.name
    manifest_path = root / MANIFEST_PATH.name
    if not manifest_path.is_file():
        print(f"未找到 {manifest_path}；无可比对的基准", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("清单必须是 JSON 对象")
        if manifest.get("schema_version") != "1.1":
            raise ValueError("不支持该清单版本；请核对来源后生成完整交付清单 1.1")
        entries = manifest["artifacts"]["files"]
        expected = {f["path"]: f["sha256"] for f in entries}
        if len(expected) != len(entries) or not all(
            isinstance(path, str)
            and isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest)
            for path, digest in expected.items()
        ):
            raise ValueError("文件条目重复或摘要无效")
        required = {
            f"{app_dir.name}/股市锦囊.exe",
            f"{app_dir.name}/BUILD_INFO.json",
            *[p.relative_to(DIST_DIR).as_posix() for p in _supporting_artifacts()],
        }
        components = manifest["components"]
        names = [_normalize(c["name"]) for c in components]
        source = manifest["source"]
        build_info = json.loads((app_dir / "BUILD_INFO.json").read_text(encoding="utf-8"))
        commit = build_info["commit"]
        if (
            not required <= expected.keys()
            or manifest["license_compliance"]["complete"] is not True
            or manifest["source"]["build_matches_repo"] is not True
            or set(names) != {_normalize(name) for name in SHIPPED_DISTRIBUTIONS}
            or len(names) != len(set(names))
            or any(
                c["installed"] is not True
                or not isinstance(c["version"], str)
                or not c["version"].strip()
                or c["version"].lower() == "unknown"
                for c in components
            )
            or not isinstance(commit, str)
            or re.fullmatch(r"[0-9a-f]{40}", commit) is None
            or not source["commit"] == source["build_commit"] == source["repo_commit"] == commit
        ):
            print("RELEASE_VERIFY_INCOMPLETE 缺少完整交付基线；请重新生成清单", file=sys.stderr)
            return 1
        actual = {
            p.relative_to(root).as_posix(): _sha256(p)
            for p in root.rglob("*")
            if p.is_file() and p != manifest_path
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"RELEASE_VERIFY_INVALID {exc}", file=sys.stderr)
        return 1

    changed = sorted(p for p in expected.keys() & actual.keys() if expected[p] != actual[p])
    absent = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    if not (changed or absent or extra):
        tree = hashlib.sha256()
        for path, digest in sorted(actual.items()):
            if path.startswith(app_dir.name + "/"):
                tree.update(f"{path}\n{digest}\n".encode())
        if tree.hexdigest() != manifest["artifacts"].get("tree_sha256"):
            print("RELEASE_VERIFY_INVALID 应用目录合并摘要不一致", file=sys.stderr)
            return 1
        print(f"RELEASE_VERIFY_OK files={len(expected)} version={manifest.get('version')}")
        print(f"  基准提交 {manifest.get('source', {}).get('commit')}")
        return 0

    for path in changed:
        print(f"RELEASE_VERIFY_CHANGED {path}", file=sys.stderr)
    for path in absent:
        print(f"RELEASE_VERIFY_MISSING {path}", file=sys.stderr)
    for path in extra:
        print(f"RELEASE_VERIFY_UNEXPECTED {path}", file=sys.stderr)
    print(
        f"RELEASE_VERIFY_FAILED changed={len(changed)} missing={len(absent)} extra={len(extra)}",
        file=sys.stderr,
    )
    return 1


def _collect_components() -> list[dict[str, Any]]:
    """把随产品分发的第三方组件收成 SBOM 组件条目。

    版本取自实际安装的发行版而非 pyproject 的 pin：清单要描述这次构建真正打进去的东西。
    """
    components: list[dict[str, Any]] = []
    for name in SHIPPED_DISTRIBUTIONS:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            components.append({"name": name, "installed": False, "error": "未安装，无法记录版本"})
            continue
        meta = dist.metadata
        declared = meta.get("License-Expression") or meta.get("License") or "UNKNOWN"
        reported = meta.get("Name") or name
        components.append(
            {
                "name": reported,
                "normalized_name": _normalize(reported),
                "version": dist.version,
                "purl": f"pkg:pypi/{_normalize(reported)}@{dist.version}",
                "declared_license": declared,
                "chosen_license": CHOSEN_LICENSE if "LGPL" in declared else declared,
                "record_sha256": _record_digest(dist),
                "installed": True,
            }
        )
    return components


def _normalize(name: str) -> str:
    """PEP 503 归一化。安装后读到的名字是 `PySide6_Essentials`，而 purl 要求规范名。

    这不是美观问题：purl 是 SBOM 的关联键，写成下划线形式会让下游漏源匹配这个组件。
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _record_digest(dist: metadata.Distribution) -> str | None:
    """哈希发行版的 RECORD 文件——它本身逐文件列出哈希，是一个诚实的完整性锚点。"""
    root = getattr(dist, "_path", None)
    if root is None:
        return None
    record = Path(str(root)) / "RECORD"
    if not record.is_file():
        return None
    return hashlib.sha256(record.read_bytes()).hexdigest()


def _stage_license_texts() -> tuple[list[str], list[str]]:
    """把 licenses/ 下的正文复制进 dist/licenses/，返回（已随附, 缺失）。"""
    LICENSES_OUT.mkdir(parents=True, exist_ok=True)
    present: list[str] = []
    missing: list[str] = []
    for name in REQUIRED_LICENSE_TEXTS:
        src = LICENSES_SRC / name
        if src.is_file():
            (LICENSES_OUT / name).write_bytes(src.read_bytes())
            present.append(name)
        else:
            missing.append(name)
    return present, missing


def _supporting_artifacts() -> list[Path]:
    return [
        DIST_DIR / "使用说明.html",
        SBOM_PATH,
        NOTICES_PATH,
        *[LICENSES_OUT / name for name in REQUIRED_LICENSE_TEXTS],
    ]


def _hash_artifacts() -> dict[str, Any]:
    """逐文件 SHA-256，外加一个覆盖整个应用目录的合并摘要。

    合并摘要按相对路径排序后把 "路径\\n哈希\\n" 依次喂进去，因此它对文件改名和内容改动同样敏感，
    可以单独用来判定"这个应用目录和上次验证过的是不是同一份"。
    """
    files: list[dict[str, Any]] = []
    tree = hashlib.sha256()
    for path in sorted(APP_DIR.rglob("*"), key=lambda p: p.relative_to(DIST_DIR).as_posix()):
        if not path.is_file():
            continue
        digest = _sha256(path)
        rel = path.relative_to(DIST_DIR).as_posix()
        files.append({"path": rel, "bytes": path.stat().st_size, "sha256": digest})
        tree.update(f"{rel}\n{digest}\n".encode())

    for extra in _supporting_artifacts():
        if extra.is_file():
            files.append(
                {
                    "path": extra.relative_to(DIST_DIR).as_posix(),
                    "bytes": extra.stat().st_size,
                    "sha256": _sha256(extra),
                }
            )
    return {
        "root": "dist/",
        "tree_root": APP_DIR.name,
        "tree_sha256": tree.hexdigest(),
        "files": files,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_sbom(components: list[dict[str, Any]]) -> dict[str, Any]:
    """CycloneDX 1.5，只登记随产品分发的组件。"""
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "component": {
                "type": "application",
                "name": "股市锦囊",
                "version": _app_version(),
                "description": "离线规则驱动的 A 股桌面决策辅助工具",
            },
            "tools": [{"name": "make_release_manifest.py", "version": "1.0"}],
            "properties": [
                {
                    "name": "stock-advisor:scope",
                    "value": "Python distributions only; actual native file hashes and Python/bootloader provenance are in 股市锦囊/RUNTIME_INVENTORY.json. Upstream statically linked components are not enumerated.",
                }
            ],
        },
        "components": [
            {
                "type": "library",
                "name": c["name"],
                "version": c.get("version", "unknown"),
                "purl": c.get("purl"),
                "licenses": [{"expression": c.get("declared_license", "UNKNOWN")}],
                "scope": "required",
            }
            for c in components
            if c.get("installed")
        ],
    }


def _build_notices(components: list[dict[str, Any]], present: list[str], missing: list[str]) -> str:
    lines = [
        "# 第三方组件与许可声明",
        "",
        f"产品：股市锦囊 {_app_version()}",
        "",
        "本产品的领域逻辑与数据访问只使用 Python 标准库。图形界面使用 Qt for Python（PySide6）。",
        "",
        "## 组件",
        "",
        "| 组件 | 版本 | 声明的许可 | 本产品选用 |",
        "| --- | --- | --- | --- |",
    ]
    for c in components:
        if not c.get("installed"):
            lines.append(f"| {c['name']} | （未安装） | — | — |")
            continue
        lines.append(
            f"| {c['name']} | {c['version']} | {c['declared_license']} | {c['chosen_license']} |"
        )
    lines += [
        "",
        "## Python 与启动器",
        "",
        "应用附带 Python 运行时和 PyInstaller bootloader，版本与原生二进制清单见 `股市锦囊/RUNTIME_INVENTORY.json`。",
        "许可文本见 `股市锦囊/_internal/licenses/Python-LICENSE.txt` 与 `PyInstaller-COPYING.txt`（含 bootloader 分发例外）。",
        "SBOM 的 Python 包清单与原生文件清单不等于完整静态链接第三方组件清单；正式发布仍需上游组件审查。",
        "",
        "## Qt / PySide6：以 LGPL-3.0 分发",
        "",
        "本产品在 `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` 三个选项中选用 **LGPL-3.0-only**。",
        "据此我们承担并履行以下义务：",
        "",
        "1. **随附许可证正文**：见本目录下的 `licenses/`。",
        "2. **声明使用了 Qt**：即本文件。本产品未修改 Qt/PySide6 源码，使用的是 PyPI 上的官方发行版。",
        "3. **允许重新链接**（LGPL-3.0 第 4(d) 条）：Qt 的动态库以独立文件形式随应用目录分发"
        "（`股市锦囊/_internal/PySide6/`）。用户可以用自行构建或自行修改的同版本 Qt 库替换这些文件，"
        "应用会加载替换后的库——这正是本产品采用 onedir 而非单文件打包的原因之一（ADR-0004）。",
        "",
        "Qt 源码可从 https://download.qt.io/ 获取；PySide6 源码可从 https://pypi.org/project/PySide6-Essentials/ 获取。",
        "",
        "## 许可证正文",
        "",
    ]
    for name in sorted(present):
        lines.append(f"- `licenses/{name}`")
    for name in sorted(missing):
        lines.append(f"- **缺失**：`licenses/{name}`（应取自 {REQUIRED_LICENSE_TEXTS[name]}）")
    lines.append("")
    return "\n".join(lines)


def _app_version() -> str:
    """读唯一权威字段 `version.__version__`（src/version.py；pyproject 以 PEP 621 dynamic 引用它）。

    直接 import 而不是正则抠文本：包的 `__init__` 不 import 任何东西，代价只有一次模块加载，换来
    的是"清单里写的就是运行期真正在用的那个值"。正则版本还漏过一次——把行尾注释一起抠进了 SBOM
    （拿到的是 `1.0"  # 两段式…`）。
    """
    src = PROJECT_ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    import version

    return version.__version__


def _build_metadata() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "pyinstaller": _dist_version("pyinstaller"),
        "packaging_mode": "onedir (ADR-0004)",
        "build_script": "scripts/build_exe.py",
    }


def _source_metadata() -> dict[str, Any]:
    """产物是哪个提交构建的，仓库现在停在哪个提交，两者是否一致。

    `build_commit` 由 build_exe.py 写进应用目录；`repo_commit` 是生成清单时的 HEAD。清单是事后扫
    dist/ 生成的，只记 HEAD 就等于假设"当前代码 = 构建这份二进制的代码"——中间只要有一次提交，
    这个假设就不成立，而错误的来源标记会被盖章发布出去。
    """
    build_commit = None
    build_info = APP_DIR / "BUILD_INFO.json"
    if build_info.is_file():
        try:
            build_commit = json.loads(build_info.read_text(encoding="utf-8")).get("commit")
        except OSError, json.JSONDecodeError:
            build_commit = None
    repo_commit = _git("rev-parse", "HEAD")
    return {
        "commit": build_commit or repo_commit,
        "build_commit": build_commit,
        "repo_commit": repo_commit,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "build_matches_repo": bool(build_commit) and build_commit == repo_commit,
    }


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _dist_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
