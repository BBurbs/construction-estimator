import asyncio
import logging
import functools

logger = logging.getLogger(__name__)


def retry_with_backoff(max_retries: int = 2, base_delay: float = 1.0, exceptions: tuple = (Exception,)):
    """Retry decorator with exponential backoff for async functions."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "Retry %d/%d for %s after %s: %s",
                            attempt + 1,
                            max_retries,
                            func.__name__,
                            type(e).__name__,
                            str(e),
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "All %d retries exhausted for %s: %s",
                            max_retries,
                            func.__name__,
                            str(e),
                        )
            raise last_exception

        return wrapper

    return decorator
