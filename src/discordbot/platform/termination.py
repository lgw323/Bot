"""One executable timing policy; no environment/CLI override of production bounds."""

from dataclasses import dataclass
import math

from discordbot.composition.config import RuntimePolicy


@dataclass(frozen=True, slots=True)
class TerminationPolicy:
    startup: float = 60.0
    grace: float = 20.0
    reap: float = 90.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) and v > 0 for v in (self.startup, self.grace, self.reap)):
            raise ValueError("termination bounds must be finite and positive")
        if not 3 * self.grace < self.reap:
            raise ValueError("termination requires 0 < 3G < H")

    @property
    def loop(self) -> float:
        return 2 * self.grace

    @property
    def kill(self) -> float:
        return self.reap - self.grace

    def runtime(self) -> RuntimePolicy:
        return RuntimePolicy(self.startup, self.grace)
