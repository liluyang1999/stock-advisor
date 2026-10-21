# 历史迁移起点（2026-07-10）

> 以下保留迁移前实测事实，不是当前产品状态。当前技术栈为 PySide6，参见 `../STATUS.md`、`../state/current.json` 和 `../quality/RELEASE_READINESS.md`；原始 test-baseline.json 同样仅描述 2026-07-10。

## 技术栈

- Python 3.12+；本次基线环境为 CPython 3.14.4 / Windows 11 AMD64。
- GUI：Tkinter/ttk。
- 网络：标准库 `urllib`，同步请求由后台线程调用。
- 测试：标准库 `unittest`。
- 打包：PyInstaller 6.21.0 已安装；仓库只声明 `>=6.15`。
- PySide6：未安装。
- 项目元数据：无 `pyproject.toml`，无锁文件，无 CI。

## 产品功能

1. 最多 30 只股票的个股批量分析。
2. 六个全市场筛选预设和可调参数。
3. Measurement 与五档 Decision 分离，切档不联网。
4. 因子解释、K 线、强度光谱、仓位计划和可信度回测。
5. 自选、持仓、浮动盈亏、横向对比。
6. 边沿触发条件预警。
7. 独立按需资金流。
8. 配置持久化、CSV/剪贴板、HTML 说明。
9. 离线 `--self-test`。

## 架构优点

- 核心计算、筛选、预警、回测、比较和图表几何可独立测试。
- `workflow.py` 通过 Protocol 接收 provider。
- `data_provider.py` 集中网络，`parse_*` 可纯测试。
- `store.py` 使用临时文件 + `os.replace`，测试可用环境变量隔离。
- 资金流和核心分析分离；接口失败不伪造数据。

## 已知问题

- `app.py` 体积大且承担过多协调职责。
- 内容区仍有品牌标题，与“标题栏仅出现一次身份”目标冲突。
- 当前字体包含 Microsoft YaHei UI、Consolas 和 HTML fallback，不满足全部 Microsoft YaHei。
- Tk 专属 GUI 测试不能证明 PySide6 目标完成。
- 全市场分页后续页失败可能静默返回部分数据，完整度缺少统一元数据。
- 无结构化日志、统一错误分类、deadline、熔断和请求新鲜度模型。
- 构建依赖未精确锁定，构建前不跑完整门禁。
- 历史 `dist/` 产物未证明对应当前源码。

## 实测基线

| 证据 | 结果 |
|---|---|
| `python -m unittest discover -s tests` | 449 tests / 45.052s / OK |
| `python main.py --self-test` | exit 0 / `SELF_TEST_OK` |
| `python -m compileall -q main.py build_exe.py src\stock_advisor` | exit 0 |

结果只证明当前 Tk/核心基线，不证明 PySide6 已实现。

