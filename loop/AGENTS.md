# `loop/` 协作规则

本目录是工程控制面。任何代理或协作者在推进 PySide6 迁移前必须：

1. 读取 `README.md`、`LOOP_PROTOCOL.md`、`state/current.json` 和活动工作项。
2. 检查工作树，保护用户未提交修改。
3. 从 `REQ/AC` 派生验收，不从实现反推完成定义。
4. 需要重大选择时先写/更新 ADR。
5. 实现后运行相关门禁并保存 `EVD-*`。
6. 由独立验证角色检查需求、差异、失败模式和原始证据。
7. 追加 `progress.jsonl`，更新当前状态、风险、缺陷和证据索引。

## 状态跃迁

`proposed -> ready -> in_progress -> verifying -> accepted`

- 没有验收条件不得进入 ready。
- 没有代码/文档结果不得进入 verifying。
- 没有证据和独立审查不得进入 accepted。
- blocked 必须写明可解除条件，不得用来隐藏困难。

## 不得违反

- 生产 GUI 目标是 PySide6；当前实现仍是 Tkinter，勿混淆状态。
- 所有可见字体目标是 Microsoft YaHei。
- 核心领域不得导入 Qt。
- 网络/长计算不得运行在 GUI 主线程。
- 不伪造行情、收益、测试、覆盖率或完成状态。
- 不自行发布、合并、接受许可风险或删除用户数据。

修改本目录后至少运行：

```powershell
python loop/scripts/validate_loop.py
python loop/scripts/check_traceability.py
python loop/scripts/render_status.py --check
python loop/scripts/render_backlog.py --check
python loop/scripts/check_core_boundaries.py
python -m unittest discover -s loop/tests
```
