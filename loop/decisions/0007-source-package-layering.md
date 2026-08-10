# ADR-0007：src 包按层拆分子包

- 状态：accepted
- 日期：2026-07-12

## 背景

`src/stock_advisor/` 此前是 22 个模块的扁平包，全部直接位于 `stock_advisor/` 下，纯核心（domain）与非纯层（网络、编排、界面）之间只靠命名习惯和 `AGENTS.md`/`core-module-manifest.json` 的文字与逐模块清单来约定边界，没有物理目录边界：`import` 层面并不能阻止某个未来新增的纯逻辑模块误 `import` 网络或界面模块，`check_core_boundaries.py` 的把关能力完全取决于清单是否被人工同步维护到最新。随着 PySide6 迁移临近（REQ-011；`TARGET_ARCHITECTURE.md` 中的 `qt_app/` 目标子包)，继续在一个扁平包里叠加界面/编排代码，会让"哪些模块必须保持纯、哪些可以被替换"越来越难只凭清单人工把关。

`loop/planning/archive/plans/2026-07-12-02-src-package-restructure.md`（Plan 2）先以行为保持的方式（Task 1）把 22 个模块按职责搬进 4 个功能子包（`git mv`，449 个产品测试与 `--self-test` 作为行为不变的 oracle）；本 ADR 记录这一分层决策本身及其权衡。Task 2 把 loop 控制面（`core-module-manifest.json`、边界文档、基线清单、`README.md` 目录结构）同步到新路径，本 ADR 与该同步一并提交。

## 决策

将 `src/stock_advisor/` 下的 22 个模块按层重组为 4 个子包，模块**文件名不变**，只搬迁目录并按需重写相对导入：

- `domain/`（12，纯核心，自包含，无对外相对导入需要改写）：`models`、`symbols`、`engine`、`policy`、`backtest`、`screener`、`presets`、`compare`、`alerts`、`chart`、`input_validate`、`formatting`。
- `data/`（2）：`data_provider`、`sample_data`。
- `services/`（2）：`workflow`、`store`。
- `ui/`（6）：`app`、`layout`、`theme`、`view_text`、`view_format`、`manual`。

`loop/architecture/core-module-manifest.json` 的 `forbidden_internal_modules` 从旧的扁平非纯模块名清单（`app`/`data_provider`/`manual`/`store`/`theme`/`workflow`/`qt_app`）改为非纯**子包**名清单（`data`/`services`/`ui`/`qt_app`）：`domain/` 模块的相对导入一旦跨出本包，其目标路径的第一级分量必然是这四者之一（例如 `from ..data.data_provider import x` 的内部导入目标是 `data`），`check_core_boundaries.py` 借此静态识别越界，不再需要逐个列举当前或未来任何一个非纯模块的文件名。

## 替代方案

1. **维持扁平包，仅靠文档/清单约束（现状，拒绝）**：零迁移成本，但纯核心边界完全依赖人工遵守 `AGENTS.md` 的文字描述和 `core-module-manifest.json` 的逐模块列举；新增非纯模块时清单容易遗漏或滞后，边界检查也只能枚举"禁止的模块名"而非"禁止的层"，每新增一个非纯模块都要记得同步清单，本任务开始时 `check_core_boundaries.py` 报 12 个 "protected module missing" 正是清单与代码漂移的直接后果（虽然这次是路径搬迁触发，而非新增遗漏，但暴露的是同一类脆弱性）。
2. **按未来 Qt 目标特性纵向拆分（feature-based，如 analysis/screener/watchlist/alerts 各自一个包，每个包内部再分自己的纯逻辑与界面代码，拒绝）**：更贴近垂直切片风格，理论上便于按功能增量迁移 PySide6；但当前 22 个模块最需要被工具强制的边界是"纯计算 vs 网络 vs 编排 vs 界面"这一横向层次，纵向切分会把同一层的代码（例如所有纯策略逻辑）散落到多个包里，`check_core_boundaries.py` 式的单一非纯层清单不再成立，需要为每个 feature 包各自维护边界规则，复杂度更高，且当前没有实际的按功能拆分交付计划支撑这个复杂度。
3. **（采用）按架构层拆分为 `domain/data/services/ui` 四个子包**：与 `module-map.json`/`TARGET_ARCHITECTURE.md` 已经在用的分层心智模型一致，直接对应 `check_core_boundaries.py` 需要静态区分的"纯 / 非纯"边界；子包数量少（4 个）、边界规则简单（一份非纯子包名单），且与 PySide6 迁移目标的 `qt_app/` 是并列关系而非交叉关系（`ui/` 是 Tkinter 现状，未来 `qt_app/` 接管界面职责时两者可以共存过渡，不必再次触及 `domain/`）。

## 后果

正面：

- 纯核心边界从"文字约定"变成"目录事实"：`check_core_boundaries.py` 用非纯子包名单即可穷举拒绝，新增任意数量的非纯模块都不再需要触碰禁止名单。
- 为 PySide6 迁移预留清晰的替换/并列点：迁移 `ui/` 或新增 `qt_app/` 都不影响 `domain/`、`data/`、`services/`。
- 模块文件名不变、`git mv` 保留历史；行为零变化，449 个产品测试与 `--self-test` 是行为保持的 oracle。

负面 / 成本：

- 所有跨层相对导入，以及外部绝对导入（`tests/*.py`、`main.py`、`build_exe.py`）需要一次性重写，属于一次性迁移成本（Task 1 已完成并以测试为oracle 验证）。
- `loop/` 控制面（清单、边界文档、基线清单、`README.md` 目录结构）必须与产品目录同步更新，否则 `check_core_boundaries.py` 会先于代码评审发现路径漂移——本任务开始时的 12 个 "protected module missing" 就是这一风险的实例；本 ADR 对应的 Task 2 完成了这次同步，但任何后续再次移动模块都必须同时更新两侧。
- `module-map.json` 中更细的目标架构层标签（`domain_geometry`、`presentation_pure`、`infrastructure` 等）与这里的 4 个子包不是一一对应（例如 `chart.py` 目标层标签是 `domain_geometry` 但物理上已在 `domain/` 里，`layout.py` 同为 `domain_geometry` 却物理上在 `ui/` 里）。两套分类回答的是不同问题——"最终 Qt 架构里这是什么角色" vs "今天这段代码允不允许 import 非纯代码"——不是冲突，但后续读者需要知道这是两条不同的坐标轴，`module-map.json` 保留两个字段以避免信息丢失。

## 回滚

如果分层被证明是错误方向，回滚手段是 `git revert` Task 1 的搬迁提交（`refactor: reorganize src/stock_advisor into domain/data/services/ui subpackages (behavior-preserving)`）与 Task 2 的控制面同步提交，退回到扁平包 + 旧清单。由于搬迁本身不改变任何逻辑（只搬文件、改 import），`git revert` 不会丢失中间的行为变更；停止条件是：若 revert 后 449 个产品测试与 `--self-test` 不能立即恢复绿色，则说明期间有其他改动耦合了新路径，需要先分离耦合的改动再回滚，不得强行回滚导致测试失败。

## 重访触发

- PySide6 迁移引入 `qt_app/` 后，若 `ui/`（现 Tkinter）与 `qt_app/` 长期并存导致边界规则复杂化（例如两者都需要各自的禁止名单细化），需要重新评估是否要把 `ui/` 降级为迁移期过渡包并另立 ADR。
- 若某个子包内部又长出明显可独立复用、无副作用的纯逻辑子集（例如 `services/` 中出现自包含子模块），可能需要进一步拆分，并重新评估当前 4 分法是否仍然足够。

## 关联

REQ-011、REQ-027、REQ-028、ADR-0002、WI-000、EVD-LOOP-004。
