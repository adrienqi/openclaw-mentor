"""Central logging setup with secret redaction."""

from __future__ import annotations

import logging
import os
import re


_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"bot\d+:[A-Za-z0-9_-]+"), "bot***:***"),
    (re.compile(r"sk-ant-api[A-Za-z0-9_-]+"), "sk-ant-api***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9]+"), "Bearer ***"),
    (re.compile(r"HA_WEBHOOK_SECRET=[A-Za-z0-9]+"), "HA_WEBHOOK_SECRET=***"),
    (re.compile(r"DASHBOARD_PIN=\d+"), "DASHBOARD_PIN=***"),
]

# Extra patterns from env (never log raw token values)
for _env_key in ("TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "HA_WEBHOOK_SECRET", "DASHBOARD_PIN"):
    _val = os.environ.get(_env_key, "")
    if len(_val) >= 8:
        _REDACTIONS.append((re.compile(re.escape(_val)), "***"))


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = msg
        for pattern, repl in _REDACTIONS:
            redacted = pattern.sub(repl, redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)

    # httpx logs full Telegram URLs at INFO — never enable that in production
    for name in ("httpx", "httpcore", "telegram", "telegram.ext", "anthropic"):
        logging.getLogger(name).setLevel(logging.WARNING)
