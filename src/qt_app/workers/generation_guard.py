"""世代守卫：丢弃被取消/重启/重复启动 supersede 的上一代迟到结果（RISK-005 / REQ-010 / WI-019）。

异步控制器的通病：一轮工作提交到线程池后，用户又取消并重启、或在上一轮完成前再次启动，于是**上
一代**的结果会迟到抵达 GUI 线程，若不加区分就会覆盖新一轮的状态、或发出本不该发的完成信号。

守卫的做法极简：每开一轮 `bump()` 递增世代号并把该号交给这一轮的 worker/闭包；结果回到 GUI 线程
时用 `is_current(gen)` 判断它是否仍属当前世代，过期即丢弃。

**为什么无需加锁**：世代号只在 GUI 线程读写——`bump()` 在 `start()`（GUI 线程）调用，`is_current`
在 queued signal 的槽（GUI 线程）调用；worker 线程只持有开轮那一刻拿到的 `int` 快照，从不写回。
因此这是一段纯逻辑，不含任何 Qt 或线程原语，可脱离事件循环单元测试。
"""

from __future__ import annotations


class GenerationGuard:
    """单调递增的世代计数器。GUI 线程独占读写；worker 只读它开轮时拿到的 int 快照。"""

    def __init__(self) -> None:
        self._generation = 0

    @property
    def current(self) -> int:
        """当前世代号。"""
        return self._generation

    def bump(self) -> int:
        """开新一轮：递增世代并返回新的当前世代号（交给本轮 worker/闭包持有）。"""
        self._generation += 1
        return self._generation

    def is_current(self, generation: int) -> bool:
        """`generation` 是否仍是当前世代。过期（被后续 bump 取代）返回 False，其结果应丢弃。"""
        return generation == self._generation
