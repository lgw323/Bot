"""Separate bearer capabilities and authenticated loopback request signing."""

import base64
import hashlib
import hmac
import ipaddress
import re
from urllib.parse import urlsplit

from discordbot.platform.errors import AuthorizationError, ConfigurationError, CapacityError, ValidationError
from discordbot.watch.domain.policy import InvalidCapability, positive_id


class Capabilities:
    def __init__(self, secret: str) -> None:
        if not isinstance(secret, str) or len(secret) < 32:
            raise ConfigurationError("Watch capability key must have at least 32 characters")
        self._secret = secret.encode()

    def mint(self, guild: int, user: int, operation: str, issued: int) -> tuple[str, str]:
        positive_id(guild)
        positive_id(user)
        if not isinstance(operation, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", operation):
            raise ValidationError("invalid Watch idempotency key")
        raw = hmac.digest(self._secret, f"watch-capability:{guild}:{user}:{operation}:{issued}".encode(), "sha256")
        token = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        return token, self.digest(token)

    def digest(self, token: str) -> str:
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise InvalidCapability("invalid Watch capability")
        return hashlib.sha256(token.encode()).hexdigest()


def loopback_url(url: str) -> str:
    try:
        value = urlsplit(url)
        if value.scheme != "http" or value.username or value.password or value.query or value.fragment or value.path not in {"", "/"}:
            raise ValueError
        if not ipaddress.ip_address(value.hostname).is_loopback or not value.port:
            raise ValueError
        return url.rstrip("/")
    except (ValueError, TypeError):
        raise ConfigurationError("Watch control URL must be a literal loopback HTTP address with port") from None


def public_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise ValueError
        parsed.port  # Reject malformed/out-of-range ports at configuration time.
        return value.rstrip("/")
    except (ValueError, TypeError, AttributeError):
        raise ConfigurationError("invalid Watch public origin") from None


class LoopbackAuth:
    def __init__(self, secret: str) -> None:
        if not isinstance(secret, str) or len(secret) < 32:
            raise ConfigurationError("Watch loopback key must have at least 32 characters")
        self._key = secret.encode()
        self._seen: dict[str, float] = {}

    def signature(self, path: str, body: bytes, stamp: str, nonce: str) -> str:
        value = b"POST\n" + path.encode() + b"\n" + stamp.encode() + b"\n" + nonce.encode() + b"\n" + body
        return hmac.new(self._key, value, hashlib.sha256).hexdigest()

    def verify(self, host: str, path: str, body: bytes, stamp: str, nonce: str, signature: str, now: float) -> None:
        try:
            if not ipaddress.ip_address(host).is_loopback or not re.fullmatch(r"[0-9]{1,12}", stamp) or abs(now-int(stamp)) > 30:
                raise ValueError
            if not re.fullmatch(r"[a-f0-9]{32}", nonce) or not re.fullmatch(r"[a-f0-9]{64}", signature):
                raise ValueError
            if not hmac.compare_digest(self.signature(path, body, stamp, nonce), signature):
                raise ValueError
        except (ValueError, TypeError):
            raise AuthorizationError("Watch loopback authentication failed") from None
        self._seen = {key: expires for key, expires in self._seen.items() if expires > now}
        if nonce in self._seen:
            raise AuthorizationError("Watch loopback replay rejected")
        if len(self._seen) >= 256:
            raise CapacityError("Watch loopback replay window full")
        self._seen[nonce] = now + 61
