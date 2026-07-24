# ADR-0015：移除 `stock_advisor/` 包根，架构层直接作为 `src/` 下的顶级包

- 状态：accepted
- 日期：2026-07-22

## 背景

ADR-0007 把 22 个模块按层拆进 `src/stock_advisor/{domain,data,services,ui}`（后增 `observability`、
`qt_app`），并让 `check_core_boundaries.py` 借相对导入的第一级分量静态判定核心越界。此后仓库根目录
定型为 `src/`（主程序）+ `tests/`（测试）+ `scripts/`（工具脚本）。此时 `src/` 下只有 `stock_advisor/`
一个条目：对一个从不 pip 安装、不作为库被第三方导入的桌面应用，这层包根只剩"到达代码多点一层"的成本，
仓库维护者两次明确要求移除它。

## 决策

`src/stock_advisor/` 的内容整体上移一层（`git mv`，历史保留）：

- 六个层包成为顶级包：`src/{domain,data,services,observability,ui,qt_app}`；
- `stock_advisor/ports.py` → `src/ports.py`；
- `stock_advisor/__init__.py`（版本单一真源）→ `src/version.py`，消费方
  （`ui/manual.py`、`scripts/make_release_manifest.py`、版本单源测试）改读 `version.__version__`；
- 导入从 `stock_advisor.domain.engine` 变为 `domain.engine`；跨层相对导入（如
  `from ..domain.models import DailyBar`）不再可能越出顶级包，一律改写为绝对形式（145 处）；
  层内相对导入（`from .models import …`）保持不变；
- `mock.patch("stock_advisor.…")` 等字符串目标同步改写（tests 共 239 行涉及）。

`check_core_boundaries.py` 的**代码零改动**，仅数据适配（`core-module-manifest.json`）：
`source_root` 改为 `../src`；`data/services/ui/qt_app` 四个层名加入 `forbidden_import_roots`
（禁入根从 6 个变 10 个）。扫平后核心模块的越层导入必然是绝对形式，第一级分量即层名，正好落在
禁入根检查上；`package_name`/`forbidden_internal_modules` 保留，继续兜住历史形态的
`stock_advisor.*` 绝对导入与（如今不可能出现的）相对逃逸。适配后做了变异验证：向核心模块注入
`from data.sample_data import …`，门禁立即报 `imports forbidden roots: ['data']`，还原后复绿。

## 代价与已知风险

- `domain`/`data`/`services`/`ui`/`qt_app`/`observability`/`ports`/`version` 成为本项目占用的
  **顶级模块名**。决策时逐一实测 `importlib.util.find_spec`：当前环境（含 PySide6-Essentials、
  pytest、coverage、pyinstaller 等全部已装依赖）中无一被占用。本应用离线运行、运行期第三方依赖
  唯一且钉版，`src/` 位于 sys.path 首位（本地包稳定遮蔽同名三方包），风险有界但**不为零**：
  今后新增任何运行期依赖，须先确认其不携带这些顶级名（写入 AGENTS.md/README 的依赖新增须知）。
- 导入不再自报产品名（`from domain.engine import …` 不含 `stock_advisor` 字样）。产品身份保留在
  日志命名空间（`observability/log.py` 的 `_ROOT_NAME = "stock_advisor"`）与应用文案中，
  日志行为因此完全不变。
- 一次性改写量：src 21 行绝对导入 + 145 行跨层相对导入、tests 239 行、`main.py`/`scripts/` 若干、
  `loop/` 活文档与机器配置约 60 处路径。历史文档（ADR、CHANGELOG、progress.jsonl、封存证据、
  基线快照、docs/superpowers）一律不改写，行文所述为当时事实。

## 替代方案

1. **维持 `src/stock_advisor/`（拒绝）**：零成本零风险，但双层嵌套的导航成本持续存在，且维护者
   已两次要求移除。
2. **去掉 `src/`、`stock_advisor/` 提到仓库根（flat layout，拒绝）**：同样消除双层嵌套且导入与
   门禁零改动，但与维护者选定的根目录形态（`src/` + `tests/` + `scripts/`）冲突。
3. **（采用）扫平进 `src/`**：见"决策"。

## 回滚

`git revert` 本次搬迁与改写提交即可恢复 ADR-0007 形态；`core-module-manifest.json` 的两处数据改动
随 revert 一并回退。判定信号：若某新增运行期依赖确需占用上述顶级名且无法改名规避，应回滚本决策
（或恢复包根）而不是给依赖打补丁。

## 关联

ADR-0007（其四分层与门禁思想完全保留）、REQ-027、REQ-028、WI-000、EVD-LOOP-007（本次扫平的再基线）。
