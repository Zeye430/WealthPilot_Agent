"""模型熔断器：模型服务连续失败时暂停调用，直接给客户明确提示，而不是让每个请求都等到超时。

状态：
    CLOSED（正常）──连续失败达到阈值──▶ OPEN（暂停调用，持续 cooldown 秒）
    OPEN ──冷却结束──▶ HALF_OPEN（只放行一个探测请求）
    HALF_OPEN ──探测成功──▶ CLOSED；探测失败 ──▶ OPEN（重新计时）

只统计模型服务本身的失败（超时、连接错误、限流、服务端错误），工具或业务代码的异常不触发熔断。
单进程内存状态；多实例部署时各实例独立熔断（对上游故障足够，且不引入共享存储的新故障点）。
"""

import threading
import time
from collections.abc import Callable

from app.core.config import get_settings
from app.core.observability import METRICS

CLOSED, HALF_OPEN, OPEN = "CLOSED", "HALF_OPEN", "OPEN"
STATE_VALUE = {CLOSED: 0, HALF_OPEN: 1, OPEN: 2}


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._state = CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._probe_in_flight = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._current_state()

    def _current_state(self) -> str:
        if self._state == OPEN and self._clock() - self._opened_at >= self.cooldown_seconds:
            self._state = HALF_OPEN
            self._probe_in_flight = False
            self._publish()
        return self._state

    def allow(self) -> bool:
        """是否放行本次请求。半开状态只放行一个探测请求，其余继续快速失败。"""
        with self._lock:
            state = self._current_state()
            if state == CLOSED:
                return True
            if state == HALF_OPEN and not self._probe_in_flight:
                self._probe_in_flight = True
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._probe_in_flight = False
            if self._state != CLOSED:
                self._state = CLOSED
                self._publish()

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._probe_in_flight = False
            if self._state == HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = OPEN
                self._opened_at = self._clock()
                self._publish()

    def retry_after(self) -> int:
        with self._lock:
            remaining = self.cooldown_seconds - (self._clock() - self._opened_at)
            return max(1, round(remaining))

    def _publish(self) -> None:
        METRICS.set("wealthpilot_llm_circuit_state", STATE_VALUE[self._state])


_breaker: CircuitBreaker | None = None


def get_breaker() -> CircuitBreaker:
    global _breaker
    if _breaker is None:
        s = get_settings()
        _breaker = CircuitBreaker(s.llm_breaker_failures, s.llm_breaker_cooldown_seconds)
    return _breaker


def reset_breaker() -> None:
    """测试用：恢复初始状态。"""
    global _breaker
    _breaker = None
    METRICS.set("wealthpilot_llm_circuit_state", 0)
