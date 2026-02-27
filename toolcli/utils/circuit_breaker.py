"""Circuit breaker pattern implementation for resilience."""

import asyncio
from enum import Enum, auto
from datetime import datetime, timedelta
from typing import Callable, Any, Optional
from dataclasses import dataclass, field


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Failing, reject requests
    HALF_OPEN = "half_open"    # Testing if recovered


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker."""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    state_changes: int = 0
    total_calls: int = 0
    rejected_calls: int = 0


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    
    def __init__(self, service_name: str, message: Optional[str] = None):
        self.service_name = service_name
        self.message = message or f"Circuit breaker is OPEN for {service_name}"
        super().__init__(self.message)


class CircuitBreaker:
    """Circuit breaker for external service calls.
    
    Prevents cascade failures by temporarily disabling calls to failing services.
    
    Usage:
        cb = CircuitBreaker("ollama", failure_threshold=5)
        result = await cb.call(ollama_client.generate, prompt)
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 3,
        success_threshold: int = 2,
    ):
        """Initialize circuit breaker.
        
        Args:
            name: Service name for identification
            failure_threshold: Failures before opening circuit
            recovery_timeout: Seconds before attempting recovery
            half_open_max_calls: Max calls in half-open state
            success_threshold: Successes needed to close circuit
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold
        
        self._state = CircuitState.CLOSED
        self._metrics = CircuitBreakerMetrics()
        self._half_open_successes = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state
    
    @property
    def metrics(self) -> CircuitBreakerMetrics:
        """Current metrics."""
        return self._metrics
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Async function to call
            *args, **kwargs: Arguments for function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Original exception if call fails
        """
        async with self._lock:
            # Check if we should attempt reset
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_successes = 0
                    self._metrics.state_changes += 1
                    print(f"[CircuitBreaker:{self.name}] Entering half-open state")
                else:
                    self._metrics.rejected_calls += 1
                    raise CircuitBreakerOpenError(self.name)
            
            # Check half-open limit
            if self._state == CircuitState.HALF_OPEN:
                if self._metrics.total_calls - self._metrics.rejected_calls >= self.half_open_max_calls:
                    self._metrics.rejected_calls += 1
                    raise CircuitBreakerOpenError(
                        self.name,
                        f"Half-open limit ({self.half_open_max_calls}) reached"
                    )
        
        # Execute call outside lock
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
            
        except CircuitBreakerOpenError:
            raise  # Don't count circuit breaker errors as failures
            
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            self._metrics.total_calls += 1
            self._metrics.success_count += 1
            
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                
                if self._half_open_successes >= self.success_threshold:
                    print(f"[CircuitBreaker:{self.name}] Closing circuit - service recovered")
                    self._reset()
                    self._metrics.state_changes += 1
            else:
                # In closed state, decrement failure count
                self._metrics.failure_count = max(0, self._metrics.failure_count - 1)
    
    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self._metrics.total_calls += 1
            self._metrics.failure_count += 1
            self._metrics.last_failure_time = datetime.now()
            
            if self._state == CircuitState.HALF_OPEN:
                # Recovery failed, open circuit again
                print(f"[CircuitBreaker:{self.name}] Opening circuit - recovery failed")
                self._state = CircuitState.OPEN
                self._metrics.state_changes += 1
                
            elif self._metrics.failure_count >= self.failure_threshold:
                # Threshold reached, open circuit
                print(f"[CircuitBreaker:{self.name}] Opening circuit - threshold reached "
                      f"({self._metrics.failure_count}/{self.failure_threshold})")
                self._state = CircuitState.OPEN
                self._metrics.state_changes += 1
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time passed to try recovery."""
        if not self._metrics.last_failure_time:
            return True
            
        elapsed = (datetime.now() - self._metrics.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout
    
    def _reset(self):
        """Reset circuit to closed state."""
        self._state = CircuitState.CLOSED
        self._metrics.failure_count = 0
        self._metrics.success_count = 0
        self._half_open_successes = 0
    
    def get_state_dict(self) -> dict:
        """Get current state as dictionary."""
        return {
            "name": self.name,
            "state": self._state.value,
            "metrics": {
                "failure_count": self._metrics.failure_count,
                "success_count": self._metrics.success_count,
                "total_calls": self._metrics.total_calls,
                "rejected_calls": self._metrics.rejected_calls,
                "state_changes": self._metrics.state_changes,
                "last_failure": self._metrics.last_failure_time.isoformat() 
                    if self._metrics.last_failure_time else None,
            },
            "config": {
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "half_open_max_calls": self.half_open_max_calls,
            }
        }


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""
    
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
    
    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
    ) -> CircuitBreaker:
        """Get existing or create new circuit breaker."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name."""
        return self._breakers.get(name)
    
    def get_all_states(self) -> dict:
        """Get states of all circuit breakers."""
        return {
            name: breaker.get_state_dict()
            for name, breaker in self._breakers.items()
        }
