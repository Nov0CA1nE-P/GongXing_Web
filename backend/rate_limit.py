import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class RateRule:
    name: str
    identity: str
    limit: int
    window_seconds: int

    @property
    def key(self) -> tuple[str, str, int, int]:
        return (
            self.name,
            self.identity,
            self.limit,
            self.window_seconds,
        )


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int = 0
    reason: str = ""


@dataclass
class _Bucket:
    window_seconds: int
    timestamps: deque[float]


class SlidingWindowRateLimiter:
    """单进程线程安全滑动窗口限流器。"""

    def __init__(
        self,
        max_buckets: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        cleanup_interval_seconds: int = 60,
    ) -> None:
        if not 1000 <= max_buckets <= 100000:
            raise ValueError("max_buckets 必须介于 1000 和 100000 之间")
        self.max_buckets = max_buckets
        self._clock = clock
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._buckets: dict[tuple[str, str, int, int], _Bucket] = {}
        self._last_cleanup = clock()
        self._lock = threading.RLock()

    @staticmethod
    def _prune_bucket(bucket: _Bucket, now: float) -> None:
        cutoff = now - bucket.window_seconds
        while bucket.timestamps and bucket.timestamps[0] <= cutoff:
            bucket.timestamps.popleft()

    def _cleanup_all_locked(self, now: float) -> None:
        empty_keys = []
        for key, bucket in self._buckets.items():
            self._prune_bucket(bucket, now)
            if not bucket.timestamps:
                empty_keys.append(key)
        for key in empty_keys:
            del self._buckets[key]
        self._last_cleanup = now

    @staticmethod
    def _deduplicate(rules: Iterable[RateRule]) -> tuple[RateRule, ...]:
        unique: dict[tuple[str, str, int, int], RateRule] = {}
        for rule in rules:
            if rule.limit <= 0 or rule.window_seconds <= 0:
                raise ValueError("限流规则必须使用正数额度和窗口")
            unique[rule.key] = rule
        return tuple(unique.values())

    def _check_rules_locked(
        self,
        rules: tuple[RateRule, ...],
        now: float,
    ) -> RateLimitResult:
        waits: list[float] = []
        for rule in rules:
            bucket = self._buckets.get(rule.key)
            if bucket is None:
                continue
            self._prune_bucket(bucket, now)
            if len(bucket.timestamps) >= rule.limit:
                waits.append(
                    bucket.timestamps[0] + rule.window_seconds - now
                )
        if waits:
            return RateLimitResult(
                allowed=False,
                retry_after=max(1, math.ceil(max(waits))),
                reason="quota",
            )
        return RateLimitResult(allowed=True)

    def check_many(self, rules: Iterable[RateRule]) -> RateLimitResult:
        unique_rules = self._deduplicate(rules)
        now = self._clock()
        with self._lock:
            if now - self._last_cleanup >= self._cleanup_interval_seconds:
                self._cleanup_all_locked(now)
            return self._check_rules_locked(unique_rules, now)

    def _capacity_wait_locked(
        self,
        missing_count: int,
        now: float,
    ) -> int:
        free_slots = self.max_buckets - len(self._buckets)
        slots_needed = missing_count - free_slots
        if slots_needed <= 0:
            return 0

        releases = sorted(
            bucket.timestamps[-1] + bucket.window_seconds - now
            for bucket in self._buckets.values()
            if bucket.timestamps
        )
        return max(1, math.ceil(releases[slots_needed - 1]))

    def consume_many(self, rules: Iterable[RateRule]) -> RateLimitResult:
        unique_rules = self._deduplicate(rules)
        now = self._clock()
        with self._lock:
            if now - self._last_cleanup >= self._cleanup_interval_seconds:
                self._cleanup_all_locked(now)

            result = self._check_rules_locked(unique_rules, now)
            if not result.allowed:
                return result

            missing_keys = {
                rule.key
                for rule in unique_rules
                if rule.key not in self._buckets
            }
            if len(self._buckets) + len(missing_keys) > self.max_buckets:
                self._cleanup_all_locked(now)
                missing_keys = {
                    rule.key
                    for rule in unique_rules
                    if rule.key not in self._buckets
                }
                if len(self._buckets) + len(missing_keys) > self.max_buckets:
                    return RateLimitResult(
                        allowed=False,
                        retry_after=self._capacity_wait_locked(
                            len(missing_keys),
                            now,
                        ),
                        reason="capacity",
                    )

            for rule in unique_rules:
                bucket = self._buckets.get(rule.key)
                if bucket is None:
                    bucket = _Bucket(
                        window_seconds=rule.window_seconds,
                        timestamps=deque(),
                    )
                    self._buckets[rule.key] = bucket
                bucket.timestamps.append(now)
            return RateLimitResult(allowed=True)

    def clear(self, *, names: set[str], identity: str) -> None:
        now = self._clock()
        with self._lock:
            self._cleanup_all_locked(now)
            keys = [
                key
                for key in self._buckets
                if key[0] in names and key[1] == identity
            ]
            for key in keys:
                del self._buckets[key]

    def bucket_count(self) -> int:
        now = self._clock()
        with self._lock:
            self._cleanup_all_locked(now)
            return len(self._buckets)
