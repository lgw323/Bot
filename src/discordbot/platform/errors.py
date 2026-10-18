"""Typed errors that may cross V2 context boundaries."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class ErrorCategory(StrEnum):
    """Stable error groups used by adapters and telemetry."""

    USER = "user"
    CAPACITY = "capacity"
    EXTERNAL = "external"
    DATA = "data"
    PLATFORM = "platform"
    CANCELLATION = "cancellation"


class ErrorCode(StrEnum):
    VALIDATION = "validation"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    CAPACITY = "capacity"
    EXTERNAL_TEMPORARY = "external_temporary"
    EXTERNAL_PERMANENT = "external_permanent"
    DATABASE_UNAVAILABLE = "database_unavailable"
    DATA_INTEGRITY = "data_integrity"
    INTERNAL = "internal"
    CONFIGURATION = "configuration"
    CANCELLATION = "cancellation"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    STARTUP = "startup"
    SHUTDOWN = "shutdown"


class AppError(Exception):
    """Base error with a safe public message and structured private context."""

    code: ErrorCode = ErrorCode.INTERNAL
    category: ErrorCategory = ErrorCategory.PLATFORM
    retryable: bool = False
    default_safe_message = "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."

    def __init__(
        self,
        message: str,
        *,
        safe_message: str | None = None,
        context: Mapping[str, str | int | float | bool | None] | None = None,
    ) -> None:
        super().__init__(message)
        self.safe_message = safe_message or self.default_safe_message
        self.context = MappingProxyType(dict(context or {}))

    def to_log_fields(self) -> dict[str, object]:
        return {
            "error_type": type(self).__name__,
            "error_code": self.code.value,
            "error_category": self.category.value,
            "retryable": self.retryable,
            "context": dict(self.context),
        }


class ValidationError(AppError):
    code = ErrorCode.VALIDATION
    category = ErrorCategory.USER
    default_safe_message = "입력값을 확인해 주세요."


class AuthorizationError(AppError):
    code = ErrorCode.AUTHORIZATION
    category = ErrorCategory.USER
    default_safe_message = "이 작업을 수행할 권한이 없습니다."


class NotFoundError(AppError):
    code = ErrorCode.NOT_FOUND
    category = ErrorCategory.USER
    default_safe_message = "요청한 대상을 찾을 수 없습니다."


class ConflictError(AppError):
    code = ErrorCode.CONFLICT
    category = ErrorCategory.USER
    default_safe_message = "현재 상태에서는 요청을 수행할 수 없습니다."


class CapacityError(AppError):
    code = ErrorCode.CAPACITY
    category = ErrorCategory.CAPACITY
    retryable = True
    default_safe_message = "요청이 많습니다. 잠시 후 다시 시도해 주세요."


class ExternalTemporaryError(AppError):
    code = ErrorCode.EXTERNAL_TEMPORARY
    category = ErrorCategory.EXTERNAL
    retryable = True


class ExternalPermanentError(AppError):
    code = ErrorCode.EXTERNAL_PERMANENT
    category = ErrorCategory.EXTERNAL


class DatabaseUnavailableError(AppError):
    code = ErrorCode.DATABASE_UNAVAILABLE
    category = ErrorCategory.DATA
    retryable = True


class DataIntegrityError(AppError):
    code = ErrorCode.DATA_INTEGRITY
    category = ErrorCategory.DATA


class InternalError(AppError):
    code = ErrorCode.INTERNAL
    category = ErrorCategory.PLATFORM


class ConfigurationError(AppError):
    code = ErrorCode.CONFIGURATION
    category = ErrorCategory.PLATFORM
    default_safe_message = "서비스 설정이 올바르지 않습니다."


class CancellationError(AppError):
    code = ErrorCode.CANCELLATION
    category = ErrorCategory.CANCELLATION
    default_safe_message = "요청이 취소되었습니다."


class DeadlineExceededError(AppError):
    code = ErrorCode.DEADLINE_EXCEEDED
    category = ErrorCategory.CANCELLATION
    retryable = True
    default_safe_message = "요청 처리 시간이 초과되었습니다."


class StartupError(AppError):
    code = ErrorCode.STARTUP
    category = ErrorCategory.PLATFORM


class ShutdownError(AppError):
    code = ErrorCode.SHUTDOWN
    category = ErrorCategory.PLATFORM
