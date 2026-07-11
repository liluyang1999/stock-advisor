# 当前态到目标态差距

| 领域 | 当前态 | 目标态 | 关闭证据 |
|---|---|---|---|
| GUI 框架 | Tkinter | PySide6 Widgets | Qt 源码、无 Tk 生产导入、Qt 测试、真机截图 |
| 应用外壳 | 单体 app.py | QMainWindow + pages/controllers/models/workers | 架构检查 + 行为测试 |
| 字体 | 多字体混用 | 全部 Microsoft YaHei | QFontInfo + 视觉矩阵 |
| 表格 | Treeview | QTableView/model/proxy | model tester、排序/过滤/增量测试 |
| 并发 | thread + Queue + after | typed signals + worker/thread pool + generation | 取消/迟到/销毁回归测试 |
| 网络 | 每请求 timeout/重试 | 操作 deadline、错误分类、抖动、完整度 | 故障注入与契约测试 |
| 数据元信息 | 各模块零散 | source/fetched_at/stale/complete/quality | 模型与 UI 测试 |
| 科学验证 | 单元和历史复盘 | 黄金向量、性质、walk-forward、敏感性 | 研究报告和固定数据哈希 |
| 工具链 | unittest + py_compile | pyproject、锁定、format/lint/type/coverage/CI | CI 运行证据 |
| 打包 | Tk onefile | Qt onefile 或批准替代 | clean build、插件、EXE self-test |
| 发布合规 | 未记录 Qt 义务 | 许可证、SBOM、NOTICE、漏洞门禁 | 人工签署与产物 |

## 迁移原则

1. 先冻结领域合同，再建立 Qt 外壳。
2. 新旧 UI 可短期并存，但业务状态只保留一个权威模型。
3. 每个 Tk 行为测试必须映射到 Qt 行为、纯逻辑或批准废止。
4. 不在 GUI 迁移期间顺手改变评分公式；模型升级另开版本化工作项。
5. 打包、字体和 DPI 在早期做 spike，避免最后才发现不可交付。

## 尚未验证的假设

- 选定 PySide6 版本与 CPython/Windows/PyInstaller 组合兼容。
- onefile 包体、冷启动和内存可接受。
- Microsoft YaHei 在所有目标 Windows 环境可解析且符合许可使用方式。
- 自绘 K 线在 200% DPI 和高数据量下性能满足预算。
- Qt offscreen 测试可稳定运行，但不能替代真机。

