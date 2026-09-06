"""Exact MASTER_USER_ID semantics; Discord roles never silently grant permission."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class MasterAuthorization:
    master_user_id: int = field(repr=False)

    def is_master(self, user_id: int) -> bool:
        return user_id == self.master_user_id
