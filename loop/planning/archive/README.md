# planning/archive/ — 已执行完毕的设计规格与实施计划

这里存放**过程性记录**：把 `loop/` 控制面建成今天这个样子的那批设计规格（`specs/`）与分步实施计划
（`plans/`），全部标注日期，全部已执行完毕。

它们回答的是「**当初为什么这么做**」，不回答「**现在是什么**」。任何与 `loop/` 其余部分冲突之处，
**以 `loop/` 现行文档为准**——需求看 `product/REQUIREMENTS.md`，架构决策看 `decisions/`，
质量门禁看 `quality/quality-gates.json`，当前状态看 `STATUS.md`。

之所以留着而不删：这批文件记录的推理过程（尤其是被否决的方案与否决理由）在 ADR 里只留下结论，
删掉就再也答不出「为什么当时不选另一条路」。它们原先在仓库根的 `docs/superpowers/`，
现随「Loop Engineering 的指导性内容与过程性记录统一收拢到 `loop/`」一并迁入本目录。

| 文件 | 一句话说明 |
|---|---|
| `specs/2026-07-11-loop-hardening-and-tooling-design.md` | 总设计规格：加固 `loop/` 控制面并落地现代开发工具链，为 Tkinter→PySide6 迁移铺路。 |
| `plans/2026-07-11-01-foundation-hardening.md` | 计划 1/6：让 `loop/` 的校验器真正自检那些此前只写在散文里的不变量，并关闭 13 项有据可查的控制面缺陷。 |
| `plans/2026-07-12-02-src-package-restructure.md` | 计划 2/6：把扁平的 `src/stock_advisor/` 按层重组为 `domain`/`data`/`services`/`ui` 子包（行为保持）。 |
| `plans/2026-07-12-03-plans-requirements-testgoals.md` | 计划 3/6：补齐可度量的测试预期目标、缺失的非功能需求与 REQ↔AC 关联，细化每个工作项的规划。 |
| `plans/2026-07-13-04-architecture-governance.md` | 计划 4/6：量化架构与计算规格，把全部 ADR 拉齐到模板，补缺失 ADR，铺好治理地基。 |
| `plans/2026-07-13-05-doc-reconciliation.md` | 计划 5/6：把遗留文档里仍有价值的内容抽进 `loop/`，建立文档卫生政策，再删除遗留文档。 |
| `plans/2026-07-13-06-dev-toolchain-and-ci.md` | 计划 6/6：统一 `pyproject.toml`、本地门禁运行器、pre-commit 与 GitHub Actions CI。 |

> 注：这些文件里的路径引用（如 `src/stock_advisor/`、根 `CHANGELOG.md`）保留**当时**的写法。
> 后续 ADR-0015 扫平了 `src/` 包根、变更日志迁入 `loop/`——历史记录照原样保留才诚实，
> 改写它去迎合今天的布局等于伪造当时的现场。
