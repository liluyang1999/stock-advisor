# 提交历史改写记录

本文件记录对本仓库 git 历史的改写事件。改写会让所有既有 SHA 失效，是不可逆于引用层面的操作，
因此每一次都必须在此登记，并附新旧 SHA 的完整映射表，使任何历史引用仍可解析。

---

## 2026-07-21：移除 `Co-Authored-By` trailer

### 做了什么

把全部 158 条提交信息里的 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` 整行删除，
并清理删除后遗留的尾部空行。全部 158 条提交因此获得新 SHA。

- 改写前 HEAD：`413a23dd99a959aaf31ffea6c74dd4d5124103f3`
- 改写后 HEAD：`4bd895467d6b7f22f362568a9582ab15d67c4dbf`
- 受影响提交：158 条全部；其中 140 条原先带有该 trailer
- 映射表：`history-rewrite-2026-07-21-sha-map.tsv`（158 行，`old_sha` / `new_sha` / `subject`）

### 为什么

GitHub 的 contributor 归属同时采纳提交的作者字段**与** `Co-Authored-By` trailer。作者字段本就只有
`Luyang Li`，但那 140 条 trailer 会使 Claude 被列为项目贡献者。本项目的贡献者归属应当只有 Luyang，
故整体移除。

### 保证了什么（逐条核验，非推断）

改写只触碰提交信息中的 trailer 行，**代码与元数据零变化**。核验方式是把新旧两条历史各 158 条提交的
「树 SHA \| 作者名 \| 作者邮箱 \| 作者时间戳 \| 主题行」导出后逐行 diff，结果完全一致：

- 树 SHA 一致 → 任一提交所对应的文件内容一个字节都没有改变
- 作者/时间戳一致 → 归属与时间线未被篡改
- 主题行一致 → 提交信息正文除 trailer 外未被改动
- 改写后全量产品测试 847 通过、`--self-test` 通过、G-CORE 边界门禁通过

### 引用修复范围

改写使仓库内 111 处 SHA 引用失效，分两类处理：

- **活文档（13 个文件，100 处）已就地更新为新 SHA**，保持原有缩写长度（7 位仍是 7 位，40 位仍是
  40 位）。涉及 `state/progress.jsonl`、`state/evidence-index.json`、`quality/quality-gates.json`、
  `quality/convergence.json`、`quality/RELEASE_READINESS.md`、`baseline/module-map.json`、
  `governance/VERSION_AND_CHANGE_CONTROL.md`、`governance/DOCUMENTATION_HYGIENE.md`、
  `CHANGELOG.md`、`README.md`，以及当时 `docs/` 下的 3 个文件（该目录其后已解散，内容分别迁入 `loop/planning/archive/` 与 `../../docs/`）。
- **已封存的证据留档（`evidence/baselines/` 下 8 个文件，11 处）一律不改**。它们在
  `state/evidence-index.json` 中登记了 `sha256`，由 `validate_loop.py` 校验，是按防篡改设计的
  时点快照；改写它们再重新盖章，等于让防篡改机制形同虚设。这些留档中的旧 SHA 通过本文附带的
  映射表保持可查。

替换前已验证映射无歧义：57 个不同的被引用 SHA 中，没有任何一个是多于一个旧 SHA 的前缀，
也没有任何一个同时是某个新 SHA 的前缀。

### 已结案：`881099806…` 是首次审计的前置副本 commit（对象已丢失，按历史原貌保留）

`881099806deca77a7bf7e784d6786f9bccdf0ce6` 出现在 `STATUS.md`、`state/current.json` 的
`baseline_commit`、`baseline/REPOSITORY_INVENTORY.md`、`baseline/test-baseline.json` 以及
`EVD-BASE-001/002/003`、`EVD-LOOP-001/002/003` 六条证据记录、`state/progress.jsonl` 与
`state/checkpoints.jsonl` 的首批日志中。该 SHA 在**本次 trailer 改写之前就已不存在**于历史中——
改写前历史（`refs/backup/pre-trailer-strip`）与更早的仓库备份里均无此对象，故不在本次映射表内。

**2026-07-22 查明并结案：** 它是 loop 控制平面**首次审计**（`run_id=RUN-20260710-001`，时间戳
`2026-07-10T22:07:31+09:00`）时被审计工作副本对应的 commit。而当前正式 git 历史的根提交是
`61b3cde1a06de121db1b0edab0c36352a52d6c61`「chore: initial baseline snapshot」，创建于
**2026-07-11 20:47**——比首次审计晚一天。也就是说 `881099806…` 属于一套**早于当前正式历史、
用于首次审计的前置副本**，那套历史被 2026-07-11 建立的正式历史取代后，其 commit 对象随之丢失。

**处置（不是缺陷，是已解释的历史断点）：**

- **保留原值，不改写为可解析 SHA。** 所有出现处（证据 `.txt`、`test-baseline.json`、
  `REPOSITORY_INVENTORY.md`、`current.json.baseline_commit`、追加型日志）记录的都是"首次审计发生在
  该 commit 上"这一**历史事实**。把它替换成 `61b3cde` 会谎称审计发生在另一个提交上，污染
  证据完整性——证据文件更带有 `sha256` 防篡改校验，本就不应改。`baseline_commit` 自项目诞生起
  从未随任何 re-baseline 更新（EVD-LOOP-004/005/007 只更新控制平面 digest，不动它），可见它是
  **诞生锚点（一次性事实）而非当前基线活指针**，保留原值才是正确状态。
- **当前基线以 `61b3cde` 为准。** 需要"当前历史的最早提交/基线"时用它——`git rev-list --max-parents=0 HEAD`
  即得，语义由其提交标题「initial baseline snapshot」自证。
- 结论：此引用不可、也不应机械修复为可 `git show` 的 SHA；它现在是**有据可查的已知历史断点**，
  读到它的人凭本节即可理解其来历，不必再重新调查。这就是它的"正确状态"。

### 回滚

改写前的完整历史保留在本地引用 `refs/backup/pre-trailer-strip`（指向 `413a23dd`）。
回滚：`git update-ref refs/heads/main refs/backup/pre-trailer-strip`，随后需 force-push 覆盖远端。
若回滚，本次的 100 处引用更新也需一并回退。
