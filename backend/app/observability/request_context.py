"""Async-safe and thread-safe request context management using contextvars."""
from __future__ import annotations

import contextvars
from typing import Optional

_request_id_ctx_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def get_request_id() -> Optional[str]:
    """Retrieve the current request ID from context."""
    return _request_id_ctx_var.get()


def set_request_id(request_id: str) -> contextvars.Token:
    """Bind a request ID to the current context."""
    return _request_id_ctx_var.set(request_id)


def reset_request_id(token: contextvars.Token) -> None:
    """Reset the context variable using its token."""
    _request_id_ctx_var.reset(token)
