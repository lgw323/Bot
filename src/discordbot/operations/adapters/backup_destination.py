"""Reviewed backup recipients; configuration cannot grant recipient approval."""

from dataclasses import dataclass
import re

from discordbot.platform.errors import ConfigurationError


REMOTE = "git@github.com:lgw323/Bot-Data.git"
REF = "refs/heads/db-backup"
# An exact private staging repository requires owner approval and source review.
# No staging recipient is approved yet. Tests replace this set only in-process.
ISOLATED_REPOSITORIES: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class BackupDestination:
    environment: str
    target: str
    repository: str
    ref: str = REF


PRODUCTION = BackupDestination("production", "production", REMOTE)


def validate(destination: BackupDestination) -> BackupDestination:
    """Revalidate typed settings before adapter admission; never echo input."""
    if not isinstance(destination, BackupDestination):
        raise ConfigurationError("unapproved remote backup configuration")
    if destination == PRODUCTION:
        return destination
    if (destination.environment == "staging" and destination.target == "isolated"
            and destination.ref == REF and isinstance(destination.repository, str)
            and re.fullmatch(r"git@github\.com:lgw323/[A-Za-z0-9][A-Za-z0-9_-]{0,95}\.git",
                             destination.repository)
            and destination.repository.casefold() not in {
                REMOTE.casefold(), "git@github.com:lgw323/bot.git",
                "git@github.com:lgw323/discordbot.git"}
            and destination.repository in ISOLATED_REPOSITORIES):
        return destination
    raise ConfigurationError("unapproved remote backup configuration")


def parse(value: object, environment: str) -> BackupDestination | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigurationError("unapproved remote backup configuration")
    fields = {"kind", "repository", "ref"}
    if set(value) == fields and value.get("kind") == "git-ssh":
        return validate(BackupDestination(environment, "production", value["repository"], value["ref"]))
    if (set(value) == fields | {"target"} and value.get("kind") == "git-ssh"
            and value.get("target") == "isolated"):
        return validate(BackupDestination(environment, "isolated", value["repository"], value["ref"]))
    raise ConfigurationError("unapproved remote backup configuration")
