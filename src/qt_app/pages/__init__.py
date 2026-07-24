"""Qt 功能页：只做视图与信号连接，业务经 controller 走（ADR-0002/ADR-0003）。

页面绝不自己碰线程或阻塞调用，也不含分析逻辑——它 connect controller 的信号更新 QWidget，
把用户动作转成 controller 调用。所有 QWidget 更新都在 GUI 主线程（REQ-013）。
"""
