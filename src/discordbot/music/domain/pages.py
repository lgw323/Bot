"""Selections identify songs, never mutable queue indices."""
from dataclasses import dataclass

from discordbot.music.domain.model import Track
from discordbot.platform.errors import AuthorizationError, ConflictError, ValidationError


@dataclass(frozen=True, slots=True, repr=False)
class SongPages:
    guild_id: int
    user_id: int
    expires: float
    songs: tuple[Track, ...]
    revision: int = 0

    @property
    def count(self) -> int:
        return max(1, (len(self.songs) + 24) // 25)

    def page(self, index: int) -> tuple[Track, ...]:
        if not 0 <= index < self.count:
            raise ValidationError("invalid Music page")
        return self.songs[index * 25:(index + 1) * 25]

    def select(self, ids: tuple[str, ...], guild_id: int, user_id: int, now: float) -> tuple[Track, ...]:
        if guild_id != self.guild_id or user_id != self.user_id:
            raise AuthorizationError("Music selection belongs to another guild or user")
        if now >= self.expires:
            raise ConflictError("Music selection expired")
        by_id = {song.item_id: song for song in self.songs}
        if len(set(ids)) != len(ids) or any(identity not in by_id for identity in ids):
            raise ConflictError("invalid Music selection")
        return tuple(by_id[identity] for identity in ids)
