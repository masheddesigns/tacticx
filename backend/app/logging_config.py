"""Structured (JSON-ish, key=value) logging setup."""
from __future__ import annotations

import logging
import re
import sys

_configured = False

# Never let secret query params (e.g. odds apiKey) reach logs — httpx logs
# full request URLs at INFO level.
_SECRET_PATTERNS = (
    re.compile(r"(?i)(apikey=)[^&\s'\"]*"),
    re.compile(r"(?i)(x-apisports-key['\"\s:=]+)[^'\"\s,;]*"),
)


def redact_secrets(text: str) -> str:
    out = text or ""
    for pat in _SECRET_PATTERNS:
        out = pat.sub(r"\1***", out)
    return out


class _RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_secrets(record.msg)
            if record.args:
                cleaned = []
                for arg in record.args:  # type: ignore[union-attr]
                    if isinstance(arg, str):
                        cleaned.append(redact_secrets(arg))
                        continue
                    # httpx passes URL objects (not str) as format args;
                    # stringify to catch embedded secrets, then redact.
                    try:
                        text = str(arg)
                    except Exception:
                        cleaned.append(arg)
                        continue
                    cleaned.append(redact_secrets(text)
                                   if _has_secret(text) else arg)
                record.args = tuple(cleaned)
        except Exception:
            pass
        return True


def _has_secret(text: str) -> bool:
    return any(pat.search(text) is not None for pat in _SECRET_PATTERNS)


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    # Logs go to stderr so scripts can emit machine-readable JSON on stdout.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s"
    ))
    filt = _RedactSecretsFilter()
    handler.addFilter(filt)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # httpx logs request URLs (which may carry key query params) — redact there too.
    logging.getLogger("httpx").addFilter(filt)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
