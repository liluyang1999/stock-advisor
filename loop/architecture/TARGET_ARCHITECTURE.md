# 目标架构

## 架构风格

采用“纯领域核心 + 应用编排 + 基础设施适配 + PySide6 表现层”的分层桌面架构。

```text
PySide6 Views / Widgets / Table Models
               │ signals / commands / immutable DTO
               ▼
Controllers / Session State / Task Coordinator
               │
               ▼
Workflow / Domain Services
               │
      ┌────────┼─────────┐
      ▼        ▼         ▼
 Measurement  Policy   Screener/Backtest/Alerts
      │
      ▼
MarketData Port / Store Port / Clock Port
      │
      ▼
QtNetwork Adapter / legacy urllib migration adapter / JSON Store
```

## 目标目录

```text
src/stock_advisor/
  models.py, engine.py, policy.py, screener.py, ...  # 保留纯核心
  app.py                                               # 最终仅兼容启动导出
  qt_app/
    bootstrap.py             # QApplication、字体、资源、顶层异常
    main_window.py           # QMainWindow、主导航、状态栏
    session_state.py         # 与 QWidget 解耦的会话权威状态
    commands.py              # 用户意图/命令 DTO
    controllers/
      analysis_controller.py
      screener_controller.py
      watchlist_controller.py
      alert_controller.py
      evidence_controller.py
    workers/
      signals.py
      analysis_worker.py
      screener_worker.py
      monitor_worker.py
      fund_flow_worker.py
    pages/
      individual_page.py
      screener_page.py
      portfolio_page.py
      alerts_page.py
      evidence_page.py
    table_models/
      result_model.py
      screener_model.py
      watchlist_model.py
      comparison_model.py
      alert_model.py
    widgets/
      strength_selector.py
      factor_view.py
      kline_view.py
      position_plan.py
      empty_state.py
      status_strip.py
    dialogs/
      help_dialog.py
      strategy_dialog.py
    theme/
      tokens.py
      application.qss
    resources/
      resources.qrc
```

## 核心约束

1. `models/engine/policy/backtest/screener/alerts/compare/chart` 不导入 Qt、网络实现或文件系统。
2. UI 不直接调用 URL、解析响应或写配置。
3. Controller 不持有 QWidget 作为业务状态；SessionState 是权威。
4. Worker 只发 typed signal，不更新 QWidget。
5. 每项异步任务有 task_id、generation、deadline、cancel token。
6. 新旧 UI 迁移期共享同一领域合同，不复制算法。
7. 模型公式变更与 GUI 迁移分离，另用模型版本 ADR。
8. 核心模块机器清单以 `core-module-manifest.json` 为权威；静态门禁禁止 Qt、Tk、网络实现和文件系统导入渗入纯核心。

## 会话状态

至少保存：

- 当前 level、capital、preset、页面和选择。
- results/recommendations/measurements/histories 映射。
- watchlist、alerts 和 monitor state。
- 每个通道的 generation、running、progress、error。
- 数据 source、fetched_at、complete、stale、quality。

状态更新使用 reducer/明确方法，确保可测试、可回放；控件值只是投影。跨线程发送前，包含 list/dict 的现有 frozen dataclass 必须防御性复制并冻结为 tuple/只读结构，发射方不得在 signal 后继续修改底层容器。
