"""Resilience utilities for toolcli - retry logic and circuit breaker support."""

import functools
import asyncio
import random
from typing import Callable, TypeVar, Optional, Tuple, Any
from datetime import datetime
import httpx

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Tuple[type, ...] = (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.NetworkError,
            asyncio.TimeoutError,
            ConnectionRefusedError,
        )
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions


class RetryExhaustedError(Exception):
    """Raised when all retry attempts exhausted."""
    
    def __init__(self, message: str, original_error: Exception, attempts: int):
        super().__init__(message)
        self.original_error = original_error
        self.attempts = attempts
        self.timestamp = datetime.now().isoformat()


def with_retry(config: Optional[RetryConfig] = None):
    """Decorator for adding retry logic to async functions.
    
    Args:
        config: RetryConfig instance or None for defaults
        
    Usage:
        @with_retry(RetryConfig(max_attempts=3))
        async def my_function():
            ...
    """
    cfg = config or RetryConfig()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(1, cfg.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except cfg.retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt == cfg.max_attempts:
                        # Final attempt failed
                        raise RetryExhaustedError(
                            f"Failed after {cfg.max_attempts} attempts",
                            original_error=e,
                            attempts=attempt
                        ) from e
                    
                    # Calculate delay with exponential backoff
                    delay = min(
                        cfg.base_delay * (cfg.exponential_base ** (attempt - 1)),
                        cfg.max_delay
                    )
                    
                    # Add jitter to prevent thundering herd
                    if cfg.jitter:
                        delay *= (0.5 + random.random())
                    
                    print(f"[Retry] Attempt {attempt} failed: {e}. Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
            
            # Should never reach here
            raise last_exception or RuntimeError("Unexpected retry loop exit")
        
        return wrapper
    return decorator


class ResilientClient:
    """Base class for resilient external service clients."""
    
    def __init__(self, retry_config: Optional[RetryConfig] = None):
        self.retry_config = retry_config or RetryConfig()
        self._health_status: Optional[dict] = None
        self._last_health_check: Optional[datetime] = None
    
    async def health_check(self) -> dict:
        """Check service health. Override in subclass."""
        raise NotImplementedError("Subclasses must implement health_check()")
    
    async def is_healthy(self, max_age_seconds: int = 60) -> bool:
        """Check if service was healthy recently."""
        if (self._last_health_check is None or 
            self._health_status is None):
            return False
            
        age = (datetime.now() - self._last_health_check).total_seconds()
        if age > max_age_seconds:
            return False
            
        return self._health_status.get("healthy", False)
    
    def _update_health(self, status: dict):
        """Update cached health status."""
        self._health_status = status
        self._last_health_check = datetime.now()
