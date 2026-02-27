# Toolcli Retest Analysis & Resilience Improvement Plan

**Analysis Date:** 2026-02-27  
**Analyst:** OpenCode Agent  
**Status:** Post-Test Analysis & Fix Recommendations

---

## 1. Tóm tắt retest (overall status, rating mới)

### Current State Analysis

**Baseline Test Results (v0.1.0):**
- Total Tests: 6
- Pass: 3 (50%)
- Fail: 2 (33%) - Environment/dependency related
- Partial: 1 (17%)

**Root Cause Analysis:**

| Issue | Location | Root Cause | Severity |
|-------|----------|------------|----------|
| Ollama 404 | Tests 1, 5 | No health check, no graceful degradation | High |
| Missing Retry | All tools | No retry logic for transient failures | High |
| Poor Error Context | All tools | Error responses lack metadata | Medium |
| No Circuit Breaker | All tools | Cascade failure risk | Medium |
| No Timeout Config | GitHub/Ollama | Hardcoded or missing timeouts | Low |

### Rating Assessment

| Aspect | Previous | Current | Gap |
|--------|----------|---------|-----|
| Core Architecture | 8/10 | 8/10 | ✅ Stable |
| Heartbeat/Persistence | 9/10 | 9/10 | ✅ Stable |
| Error Handling | 8/10 | 8/10 | ✅ Stable |
| External Dependencies | 5/10 | 5/10 | ⚠️ **No improvement yet** |
| **Overall** | **7/10** | **7/10** | ⚠️ **Needs fixes** |

### Verdict

**Status:** ❌ **CHƯA ĐẠT** - Các cải thiện đề xuất trong TEST_RESULTS.md **chưa được triển khai**.

**Evidence:**
1. OllamaClient không có `health_check()` method
2. Không có retry decorator trong codebase
3. Error responses thiếu `error_type`, `retryable`, `context`
4. Không có circuit breaker implementation

---

## 2. Bảng so sánh test cũ vs test mới

### Test Comparison Matrix

| Scenario | Test 1 Result | Expected After Fixes | Gap |
|----------|---------------|---------------------|-----|
| 1. Normal Task | ❌ FAIL (Ollama 404) | ✅ PASS (health check + graceful) | 🔴 **Not implemented** |
| 2. Multi-step Workflow | ✅ PASS | ✅ PASS | 🟢 No change needed |
| 3. OpenCode Error | ✅ PASS | ✅ PASS | 🟢 No change needed |
| 4. GitHub CLI Error | ⚠️ PARTIAL | ✅ PASS (better error context) | 🟡 **Needs enhancement** |
| 5. Invalid Ollama | ❌ FAIL (Ollama 404) | ✅ PASS (degraded mode) | 🔴 **Not implemented** |
| 6. Heartbeat Resume | ✅ PASS | ✅ PASS | 🟢 No change needed |

### Implementation Status Check

| Proposed Improvement | Status | Location |
|---------------------|--------|----------|
| Ollama health_check() | ❌ **MISSING** | toolcli/tools/ollama.py |
| Retry decorator | ❌ **MISSING** | Not in codebase |
| Enhanced error context | ❌ **MISSING** | All tool files |
| Circuit breaker | ❌ **MISSING** | Not implemented |
| Structured logging | ❌ **MISSING** | Not implemented |

---

## 3. Danh sách issue còn tồn tại (ưu tiên theo mức độ)

### 🔴 **P0 - Critical (Block Production)**

#### Issue 1: No Health Check for External Services
**Impact:** Agent crashes or hangs when Ollama/opencode/gh unavailable  
**Frequency:** High (every time service down)  
**Risk:** Complete task failure, no graceful degradation

```python
# Current: Direct call, exception propagates
try:
    result = await ollama.generate(prompt)  # Crashes if 404
except Exception as e:
    # Only basic handling
    return {"success": False, "error": str(e)}
```

#### Issue 2: No Retry Logic for Transient Failures
**Impact:** Temporary network blips cause task failure  
**Frequency:** Medium (depends on network stability)  
**Risk:** Unnecessary failures, poor reliability

```python
# Current: Single attempt only
response = await client.post(url, json=payload)  # One shot
```

#### Issue 3: Poor Error Context for Debugging
**Impact:** Hard to diagnose failures in production  
**Frequency:** Always  
**Risk:** Longer MTTR (Mean Time To Recovery)

```python
# Current: Basic error message
return {"success": False, "error": str(e)}

# Missing: error_type, retryable, context, timestamp
```

### 🟡 **P1 - High (Degrade Experience)**

#### Issue 4: No Circuit Breaker Pattern
**Impact:** Cascade failures when service degraded  
**Frequency:** Low-Medium  
**Risk:** System overload, retry storms

#### Issue 5: No Timeout Configuration
**Impact:** Operations hang indefinitely  
**Frequency:** Low  
**Risk:** Resource exhaustion

#### Issue 6: Missing Degraded Mode
**Impact:** All-or-nothing operation  
**Frequency:** Medium  
**Risk:** Complete failure when partial success possible

### 🟢 **P2 - Medium (Nice to Have)**

#### Issue 7: No Structured Logging
**Impact:** Hard to aggregate/monitor  
**Frequency:** Always  
**Risk:** Poor observability

#### Issue 8: Missing Metrics Collection
**Impact:** No visibility into success rates  
**Frequency:** Always  
**Risk:** Blind spots in production

---

## 4. Đề xuất cách fix chi tiết cho từng issue

### 🔴 **P0 Fixes**

---

#### Fix 1: Add Health Check Pattern

**Root Cause:** Services called without availability check  
**Fix Approach:** Implement health check methods + pre-flight validation  
**Mức tác động:** Low (additive)  
**Độ ưu tiên:** P0

**Implementation:**

```python
# toolcli/tools/ollama.py - Add to OllamaClient

async def health_check(self) -> Dict[str, Any]:
    """Check Ollama service health."""
    try:
        # Quick check - list models (lightweight)
        response = await self.client.get(
            f"{self.base_url}/api/tags",
            timeout=5.0  # Short timeout for health check
        )
        
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            return {
                "healthy": True,
                "available_models": len(models),
                "default_model_available": any(
                    m.get("name") == self.config.default_model 
                    for m in models
                ),
                "latency_ms": response.elapsed.total_seconds() * 1000
            }
        else:
            return {
                "healthy": False,
                "error": f"HTTP {response.status_code}",
                "available_models": 0,
                "default_model_available": False
            }
            
    except httpx.ConnectError:
        return {
            "healthy": False,
            "error": "Connection refused - Ollama server not running",
            "retryable": True,
            "available_models": 0,
            "default_model_available": False
        }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "retryable": True,
            "available_models": 0,
            "default_model_available": False
        }
```

**OpenSpec Flow Integration:**

```yaml
# Add to openspec/flows/pre-flight-check.yaml
flow_id: dependency-health-check
steps:
  - id: check_ollama
    action: ollama-reasoning.health_check
    on_failure:
      action: log.warning
      message: "Ollama unavailable, using degraded mode"
      
  - id: check_opencode
    action: opencode-execution.health_check
    on_failure:
      action: log.warning
      message: "OpenCode unavailable"
```

---

#### Fix 2: Implement Retry Logic with Exponential Backoff

**Root Cause:** Single attempt only, no transient failure handling  
**Fix Approach:** Decorator-based retry with jitter  
**Mức tác động:** Low (wrapper)  
**Độ ưu tiên:** P0

**Implementation:**

```python
# toolcli/utils/resilience.py

import functools
import asyncio
import random
from typing import Callable, TypeVar, Tuple, Optional
from datetime import datetime

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
        )
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions

def with_retry(config: Optional[RetryConfig] = None):
    """Decorator for adding retry logic to async functions."""
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
                    
                    print(f"Attempt {attempt} failed: {e}. Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
            
            # Should never reach here
            raise last_exception or RuntimeError("Unexpected retry loop exit")
        
        return wrapper
    return decorator

class RetryExhaustedError(Exception):
    """Raised when all retry attempts exhausted."""
    def __init__(self, message: str, original_error: Exception, attempts: int):
        super().__init__(message)
        self.original_error = original_error
        self.attempts = attempts
```

**Usage in OllamaClient:**

```python
from toolcli.utils.resilience import with_retry, RetryConfig

class OllamaClient:
    
    @with_retry(RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        retryable_exceptions=(
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.NetworkError,
        )
    ))
    async def generate(self, prompt: str, ...) -> Dict[str, Any]:
        """Generate with automatic retry."""
        ...
    
    @with_retry(RetryConfig(max_attempts=3))
    async def chat(self, messages: ..., ...) -> Dict[str, Any]:
        """Chat with automatic retry."""
        ...
```

---

#### Fix 3: Enhanced Error Context

**Root Cause:** Error responses lack debugging metadata  
**Fix Approach:** Enrich all error responses with context  
**Mức tác động:** Low (response enhancement)  
**Độ ưu tiên:** P0

**Implementation:**

```python
# toolcli/utils/error_context.py

from datetime import datetime
from typing import Dict, Any, Optional
import traceback

class ErrorContext:
    """Enrich error responses with debugging context."""
    
    @staticmethod
    def enrich(
        error: Exception,
        operation: str,
        context: Optional[Dict[str, Any]] = None,
        include_traceback: bool = False
    ) -> Dict[str, Any]:
        """Create enriched error response."""
        
        error_type = type(error).__name__
        
        # Determine if error is retryable
        retryable_exceptions = (
            "ConnectError",
            "TimeoutException",
            "NetworkError",
            "ConnectionRefusedError",
        )
        is_retryable = error_type in retryable_exceptions or \
                      any(isinstance(error, exc) for exc in [
                          httpx.ConnectError,
                          httpx.TimeoutException,
                      ])
        
        result = {
            "success": False,
            "error": str(error),
            "error_type": error_type,
            "operation": operation,
            "timestamp": datetime.now().isoformat(),
            "retryable": is_retryable,
            "suggested_action": ErrorContext._suggest_action(error_type, is_retryable)
        }
        
        # Add context if provided
        if context:
            result["context"] = context
        
        # Add traceback for debugging (optional)
        if include_traceback:
            result["traceback"] = traceback.format_exc()
        
        return result
    
    @staticmethod
    def _suggest_action(error_type: str, retryable: bool) -> str:
        """Suggest recovery action based on error type."""
        suggestions = {
            "ConnectError": "Check if service is running",
            "TimeoutException": "Increase timeout or check service load",
            "HTTPStatusError": "Check API endpoint and authentication",
            "JSONDecodeError": "Check response format from service",
        }
        
        if retryable:
            base = suggestions.get(error_type, "Retry operation")
            return f"{base} (will retry automatically)"
        
        return suggestions.get(error_type, "Manual intervention required")
```

**Usage in Tools:**

```python
# OllamaClient.generate()
async def generate(self, ...):
    try:
        response = await self.client.post(...)
        return {"success": True, "data": response.json()}
        
    except Exception as e:
        return ErrorContext.enrich(
            error=e,
            operation="ollama.generate",
            context={
                "model": model or self.config.default_model,
                "prompt_length": len(prompt),
                "timeout": self.config.timeout
            }
        )
```

---

### 🟡 **P1 Fixes**

---

#### Fix 4: Circuit Breaker Pattern

**Root Cause:** No protection against cascade failures  
**Fix Approach:** State machine with half-open probe  
**Mức tác động:** Medium (new component)  
**Độ ưu tiên:** P1

```python
# toolcli/utils/circuit_breaker.py

from enum import Enum
from datetime import datetime, timedelta
from typing import Callable, Any
import asyncio

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered

class CircuitBreaker:
    """Circuit breaker for external service calls."""
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 3,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                print(f"[{self.name}] Circuit entering half-open state")
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is OPEN for {self.name}. "
                    f"Service temporarily unavailable."
                )
        
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker half-open limit reached for {self.name}"
                )
            self.half_open_calls += 1
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
            
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                print(f"[{self.name}] Circuit closed - service recovered")
                self._reset()
        else:
            self.failure_count = max(0, self.failure_count - 1)
    
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            print(f"[{self.name}] Circuit opening - recovery failed")
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            print(f"[{self.name}] Circuit opening - threshold reached")
            self.state = CircuitState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time passed to try recovery."""
        if not self.last_failure_time:
            return True
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout
    
    def _reset(self):
        """Reset circuit to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0
        self.last_failure_time = None

class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass
```

---

#### Fix 5: Degraded Mode Support

**Root Cause:** All-or-nothing failure when services unavailable  
**Fix Approach:** Graceful degradation with fallback strategies  
**Mức tác động:** Medium (requires agent logic change)  
**Độ ưu tiên:** P1

```python
# toolcli/agent/degraded_mode.py

from typing import Dict, Any, Optional
from enum import Enum

class ServiceHealth(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"

class DegradedModeHandler:
    """Handle agent operation when services degraded."""
    
    def __init__(self, agent):
        self.agent = agent
        self.service_health: Dict[str, ServiceHealth] = {}
    
    async def check_all_services(self) -> Dict[str, Any]:
        """Check health of all external services."""
        checks = {
            "ollama": await self._check_ollama(),
            "opencode": await self._check_opencode(),
            "github": await self._check_github(),
        }
        
        self.service_health = {
            name: ServiceHealth.HEALTHY if check["healthy"] else ServiceHealth.UNAVAILABLE
            for name, check in checks.items()
        }
        
        return {
            "services": checks,
            "overall_status": self._determine_overall_status(),
            "capabilities": self._get_available_capabilities()
        }
    
    async def _check_ollama(self) -> Dict[str, Any]:
        """Check Ollama health."""
        try:
            return await self.agent.ollama.health_check()
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "fallback_available": True
            }
    
    async def _check_opencode(self) -> Dict[str, Any]:
        """Check OpenCode CLI availability."""
        try:
            # Quick version check
            import subprocess
            result = subprocess.run(
                ["opencode", "--version"],
                capture_output=True,
                timeout=5
            )
            return {
                "healthy": result.returncode == 0,
                "version": result.stdout.decode().strip() if result.returncode == 0 else None
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}
    
    async def _check_github(self) -> Dict[str, Any]:
        """Check GitHub CLI authentication."""
        try:
            result = await self.agent.github._run_gh(["auth", "status"])
            return {
                "healthy": result.get("success", False),
                "authenticated": result.get("success", False)
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}
    
    def _determine_overall_status(self) -> str:
        """Determine overall agent status."""
        if all(h == ServiceHealth.HEALTHY for h in self.service_health.values()):
            return "full"
        elif all(h == ServiceHealth.UNAVAILABLE for h in self.service_health.values()):
            return "offline"
        else:
            return "degraded"
    
    def _get_available_capabilities(self) -> list:
        """List capabilities available in current state."""
        capabilities = []
        
        if self.service_health.get("ollama") == ServiceHealth.HEALTHY:
            capabilities.extend(["reasoning", "analysis", "chat"])
        
        if self.service_health.get("opencode") == ServiceHealth.HEALTHY:
            capabilities.extend(["code_generation", "openspec_workflow"])
        
        if self.service_health.get("github") == ServiceHealth.HEALTHY:
            capabilities.extend(["repo_management", "issue_tracking", "pr_management"])
        
        # Always available (local operations)
        capabilities.extend(["state_management", "task_queue", "heartbeat"])
        
        return capabilities
    
    async def execute_with_fallback(
        self,
        primary_func: Callable,
        fallback_func: Optional[Callable] = None,
        service_name: str = "unknown"
    ) -> Any:
        """Execute with fallback if service degraded."""
        
        health = self.service_health.get(service_name)
        
        if health == ServiceHealth.UNAVAILABLE and fallback_func:
            print(f"[{service_name}] Service unavailable, using fallback")
            return await fallback_func()
        
        if health == ServiceHealth.UNAVAILABLE:
            return {
                "success": False,
                "error": f"{service_name} is unavailable and no fallback provided",
                "degraded": True
            }
        
        return await primary_func()
```

---

### 🟢 **P2 Fixes**

---

#### Fix 6: Structured Logging

```python
# toolcli/utils/logging.py

import json
import logging
from datetime import datetime
from typing import Dict, Any

class StructuredLogger:
    """JSON-structured logging for observability."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
    
    def log_event(
        self,
        event_type: str,
        message: str,
        context: Dict[str, Any] = None,
        level: str = "info"
    ):
        """Log structured event."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "message": message,
            "context": context or {},
            "level": level
        }
        
        getattr(self.logger, level)(json.dumps(log_entry))
```

---

## 5. Checklist các thay đổi cần thực hiện trước production

### Phase 1: Critical (P0) - Block Production

- [ ] **1.1** Implement `OllamaClient.health_check()` method
- [ ] **1.2** Add retry decorator in `toolcli/utils/resilience.py`
- [ ] **1.3** Apply retry decorator to OllamaClient methods
- [ ] **1.4** Create `ErrorContext.enrich()` utility
- [ ] **1.5** Update all tool methods to use enriched error context
- [ ] **1.6** Add health checks to OpencodeClient and GitHubClient
- [ ] **1.7** Run full test suite, verify all P0 issues resolved

**Estimated Effort:** 1-2 days  
**Expected Outcome:** Pass rate >= 83% (5/6 tests)

### Phase 2: High (P1) - Required for Beta

- [ ] **2.1** Implement CircuitBreaker class
- [ ] **2.2** Add circuit breaker to OllamaClient
- [ ] **2.3** Implement DegradedModeHandler
- [ ] **2.4** Add service health checks to agent initialization
- [ ] **2.5** Add degraded mode execution path in agent
- [ ] **2.6** Test degraded mode scenarios

**Estimated Effort:** 2-3 days  
**Expected Outcome:** System resilient to partial failures

### Phase 3: Medium (P2) - Production Polish

- [ ] **3.1** Implement StructuredLogger
- [ ] **3.2** Add metrics collection (success rates, latency)
- [ ] **3.3** Create health endpoint for daemon mode
- [ ] **3.4** Add configurable timeouts to all clients
- [ ] **3.5** Write resilience documentation

**Estimated Effort:** 1-2 days  
**Expected Outcome:** Production-ready monitoring

### Total Effort Estimate

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| P0 | 1-2 days | Critical fixes, 83%+ pass rate |
| P1 | 2-3 days | Resilience patterns, beta ready |
| P2 | 1-2 days | Observability, production ready |
| **Total** | **4-7 days** | **Production-ready toolcli** |

---

## Quick Reference: Fix Implementation Order

```
Priority Order:
1. ErrorContext.enrich()     [Foundation]
2. with_retry decorator      [Foundation]
3. health_check() methods    [Critical]
4. CircuitBreaker            [Resilience]
5. DegradedModeHandler       [Graceful]
6. StructuredLogger          [Observability]
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-02-27  
**Status:** Ready for Implementation
