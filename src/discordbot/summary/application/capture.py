"""Single-event-loop history owner: snowflake ordering, first observation wins."""

from datetime import timedelta

from discordbot.platform.clock import Clock
from discordbot.platform.errors import DataIntegrityError
from discordbot.summary.domain.models import Message, Scope, SummaryConfig
from discordbot.summary.ports.io import History


class Capture:
    def __init__(self, config: SummaryConfig, clock: Clock) -> None:
        self.config, self.clock = config, clock
        self._messages: dict[Scope, dict[int, Message]] = {s: {} for s in config.sources}
        self._loading: set[Scope] = set()
        self._reconciled: set[Scope] = set()
        self._ready: set[Scope] = set()

    def ready(self, scope: Scope) -> bool:
        return scope in self._ready

    def invalidate(self) -> None:
        self._ready.clear()

    def add(self, message: Message) -> None:
        if not self.config.enabled or message.scope not in self._messages or message.bot or not message.content:
            return
        # Discord bounds individual messages; fail closed for malformed adapters.
        if (message.id <= 0 or message.created_at.tzinfo is None or len(message.content) > 4000
                or len(message.author) > 100):
            return
        self._messages[message.scope].setdefault(message.id, message)
        self.prune()

    def prune(self) -> None:
        threshold = self.clock.now() - timedelta(hours=self.config.retention_hours)
        for rows in self._messages.values():
            for key in tuple(rows):
                if rows[key].created_at < threshold:
                    del rows[key]
            for key in sorted(rows)[:-self.config.max_messages]:
                del rows[key]

    def read(self, scope: Scope) -> tuple[Message, ...]:
        self.prune()
        rows = self._messages.get(scope, {})
        return tuple(rows[key] for key in sorted(rows))

    async def preload(self, scope: Scope, history: History) -> None:
        if not self.config.enabled or scope not in self._messages or scope in self._loading:
            return
        self._loading.add(scope)
        self._ready.discard(scope)
        try:
            # Always walk newest -> oldest to the retention/count boundary. A live
            # high ID must never advance an incomplete preload cursor past a gap.
            # Reconnect repeats this bounded reconciliation; duplicate IDs are free.
            hours = self.config.retention_hours if scope in self._reconciled else self.config.preload_hours
            after = self.clock.now() - timedelta(hours=hours)
            before = None
            fetched = 0
            while fetched < self.config.max_messages:
                limit = min(self.config.page_size, self.config.max_messages - fetched)
                page = await history.page(scope, before=before, after=after, limit=limit)
                if len(page) > limit or any(m.scope != scope or (before is not None and m.id >= before) for m in page):
                    raise DataIntegrityError("invalid history page")
                if not page:
                    break
                for message in page:
                    self.add(message)
                fetched += len(page)
                before = min(m.id for m in page)
                if len(page) < limit:
                    break
            self._reconciled.add(scope)
            self._ready.add(scope)
        finally:
            self._loading.discard(scope)

    def clear(self) -> None:
        self._ready.clear()
        for rows in self._messages.values():
            rows.clear()
