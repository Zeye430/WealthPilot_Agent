"""Model circuit breaker: when the model service keeps failing, stop calling it and tell customers
clearly instead of letting every request time out.

States:
    CLOSED (normal) ──consecutive failures reach the threshold──▶ OPEN (calls paused for cooldown
    seconds)
    OPEN ──cooldown ends──▶ HALF_OPEN (one probe request allowed)
    HALF_OPEN ──probe succeeds──▶ CLOSED; probe fails ──▶ OPEN (timer restarts)

Only failures of the model service itself count (timeouts, connection errors, rate limits, server
errors); tool or business-code exceptions don't trip it.
In-memory per process; with multiple instances each breaks independently (enough for upstream
outages, without adding shared storage as a new point of failure).
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
        """Whether to let this request through. Half-open lets one probe through; the rest keep
        failing fast."""
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
    """For tests: reset to the initial state."""
    global _breaker
    _breaker = None
    METRICS.set("wealthpilot_llm_circuit_state", 0)
