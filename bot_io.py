"""Keep blocking table operations off the Telegram event loop."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sheets")


async def run_sheets(operation, *args, **kwargs):
    return await asyncio.get_running_loop().run_in_executor(
        _executor, partial(operation, *args, **kwargs)
    )


async def telegram_call(operation, *args, **kwargs):
    for attempt in range(4):
        try:
            return await operation(*args, **kwargs)
        except Exception as error:
            if (
                type(error).__name__ not in {"RetryAfter", "TelegramRetryAfter"}
                or attempt == 3
            ):
                raise
            delay = getattr(error, "retry_after", getattr(error, "timeout", 1))
            if hasattr(delay, "total_seconds"):
                delay = delay.total_seconds()
            await asyncio.sleep(float(delay) + 1)


def configure_client(client):
    transport = getattr(client, "http_client", client)
    transport.set_timeout((5, 20))
    return client


class LazyResource:
    """Retry connection on the next operation if initial table access fails."""

    def __init__(self, factory):
        from threading import RLock

        self._factory = factory
        self._value = None
        self._lock = RLock()

    def __getattr__(self, name):
        with self._lock:
            if self._value is None:
                self._value = self._factory()
            return getattr(self._value, name)
