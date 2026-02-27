"""Metrics collection for toolcli observability."""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict


@dataclass
class OperationMetrics:
    """Metrics for a single operation type."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0
    errors: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_call: Optional[datetime] = None
    
    def record_call(self, success: bool, duration_ms: float, error_type: Optional[str] = None):
        """Record a single call."""
        self.total_calls += 1
        self.last_call = datetime.now()
        
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
            if error_type:
                self.errors[error_type] += 1
        
        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate (0-1)."""
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls
    
    @property
    def avg_duration_ms(self) -> float:
        """Calculate average duration."""
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": f"{self.success_rate:.2%}",
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2) if self.min_duration_ms != float('inf') else 0,
            "max_duration_ms": round(self.max_duration_ms, 2),
            "errors": dict(self.errors),
            "last_call": self.last_call.isoformat() if self.last_call else None,
        }


class MetricsCollector:
    """Collect and aggregate metrics for toolcli operations."""
    
    def __init__(self):
        """Initialize metrics collector."""
        self._metrics: Dict[str, OperationMetrics] = defaultdict(OperationMetrics)
        self._start_time = datetime.now()
    
    def record(
        self,
        service: str,
        operation: str,
        success: bool,
        duration_ms: float,
        error_type: Optional[str] = None,
    ):
        """Record a single operation.
        
        Args:
            service: Service name (e.g., "ollama", "github")
            operation: Operation name (e.g., "generate", "create_repo")
            success: Whether operation succeeded
            duration_ms: Duration in milliseconds
            error_type: Type of error if failed
        """
        key = f"{service}.{operation}"
        self._metrics[key].record_call(success, duration_ms, error_type)
    
    def get_metrics(self, service: Optional[str] = None) -> Dict[str, Any]:
        """Get metrics, optionally filtered by service.
        
        Args:
            service: Filter by service name, or None for all
            
        Returns:
            Dictionary of metrics
        """
        if service:
            return {
                key: metrics.to_dict()
                for key, metrics in self._metrics.items()
                if key.startswith(f"{service}.")
            }
        
        return {key: metrics.to_dict() for key, metrics in self._metrics.items()}
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        total_calls = sum(m.total_calls for m in self._metrics.values())
        total_success = sum(m.successful_calls for m in self._metrics.values())
        total_failed = sum(m.failed_calls for m in self._metrics.values())
        
        return {
            "uptime_seconds": (datetime.now() - self._start_time).total_seconds(),
            "total_operations": total_calls,
            "total_successful": total_success,
            "total_failed": total_failed,
            "overall_success_rate": f"{total_success / total_calls:.2%}" if total_calls > 0 else "N/A",
            "services_tracked": len(set(k.split(".")[0] for k in self._metrics.keys())),
            "operations_tracked": len(self._metrics),
        }
    
    def get_health_score(self) -> float:
        """Calculate overall health score (0-100)."""
        if not self._metrics:
            return 100.0
        
        total_success_rate = sum(
            m.success_rate for m in self._metrics.values()
        ) / len(self._metrics)
        
        return total_success_rate * 100
    
    def reset(self):
        """Reset all metrics."""
        self._metrics.clear()
        self._start_time = datetime.now()


class TimedOperation:
    """Context manager for timing operations and recording metrics."""
    
    def __init__(
        self,
        metrics: MetricsCollector,
        service: str,
        operation: str,
    ):
        """Initialize timed operation.
        
        Args:
            metrics: MetricsCollector instance
            service: Service name
            operation: Operation name
        """
        self.metrics = metrics
        self.service = service
        self.operation = operation
        self.start_time: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.success: Optional[bool] = None
        self.error_type: Optional[str] = None
    
    async def __aenter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and record metrics."""
        end_time = time.time()
        self.duration_ms = (end_time - self.start_time) * 1000
        
        if exc_val is None:
            self.success = True
        else:
            self.success = False
            self.error_type = exc_type.__name__ if exc_type else "Unknown"
        
        self.metrics.record(
            service=self.service,
            operation=self.operation,
            success=self.success,
            duration_ms=self.duration_ms,
            error_type=self.error_type,
        )
        
        # Don't suppress exception
        return False
    
    def __enter__(self):
        """Synchronous entry."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Synchronous exit."""
        end_time = time.time()
        self.duration_ms = (end_time - self.start_time) * 1000
        
        if exc_val is None:
            self.success = True
        else:
            self.success = False
            self.error_type = exc_type.__name__ if exc_type else "Unknown"
        
        self.metrics.record(
            service=self.service,
            operation=self.operation,
            success=self.success,
            duration_ms=self.duration_ms,
            error_type=self.error_type,
        )
        
        return False
