"""Error context enrichment for better debugging and observability."""

import traceback
import httpx
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional


class ErrorContext:
    """Enrich error responses with debugging context."""
    
    # Exceptions that are typically retryable
    RETRYABLE_EXCEPTIONS = (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        asyncio.TimeoutError,
        ConnectionRefusedError,
        ConnectionError,
    )
    
    # Error type suggestions
    ACTION_SUGGESTIONS = {
        "ConnectError": "Check if service is running and accessible",
        "TimeoutException": "Increase timeout or check service load",
        "HTTPStatusError": "Check API endpoint and authentication",
        "JSONDecodeError": "Check response format from service",
        "ConnectionRefusedError": "Service not running or wrong port",
        "CircuitBreakerOpenError": "Service temporarily disabled, wait for recovery",
        "RetryExhaustedError": "All retry attempts failed, check service health",
        "FileNotFoundError": "Check file path and permissions",
        "PermissionError": "Check user permissions for operation",
    }
    
    @staticmethod
    def enrich(
        error: Exception,
        operation: str,
        context: Optional[Dict[str, Any]] = None,
        include_traceback: bool = False,
        service_name: str = "unknown"
    ) -> Dict[str, Any]:
        """Create enriched error response.
        
        Args:
            error: The exception that occurred
            operation: Name of the operation being performed
            context: Additional context about the operation
            include_traceback: Whether to include full traceback
            service_name: Name of the external service
            
        Returns:
            Dict with enriched error information
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        # Determine if error is retryable
        is_retryable = isinstance(error, ErrorContext.RETRYABLE_EXCEPTIONS)
        
        # Determine severity
        severity = ErrorContext._determine_severity(error_type, is_retryable)
        
        result = {
            "success": False,
            "error": error_message,
            "error_type": error_type,
            "operation": operation,
            "service": service_name,
            "timestamp": datetime.now().isoformat(),
            "retryable": is_retryable,
            "severity": severity,
            "suggested_action": ErrorContext._suggest_action(error_type, is_retryable),
        }
        
        # Add context if provided
        if context:
            result["context"] = context
        
        # Add traceback for debugging (optional)
        if include_traceback:
            result["traceback"] = traceback.format_exc()
        
        return result
    
    @staticmethod
    def _determine_severity(error_type: str, retryable: bool) -> str:
        """Determine error severity."""
        critical_errors = ["CircuitBreakerOpenError", "RuntimeError", "SystemError"]
        high_errors = ["ConnectError", "ConnectionRefusedError", "PermissionError"]
        
        if error_type in critical_errors:
            return "critical"
        elif error_type in high_errors:
            return "high"
        elif retryable:
            return "medium"  # May resolve on retry
        else:
            return "low"
    
    @staticmethod
    def _suggest_action(error_type: str, retryable: bool) -> str:
        """Suggest recovery action based on error type."""
        suggestion = ErrorContext.ACTION_SUGGESTIONS.get(
            error_type, 
            "Check service status and logs"
        )
        
        if retryable and error_type not in ["RetryExhaustedError", "CircuitBreakerOpenError"]:
            return f"{suggestion} (will retry automatically)"
        
        return suggestion
    
    @staticmethod
    def create_success_response(
        data: Any = None,
        operation: str = "unknown",
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create standardized success response."""
        result = {
            "success": True,
            "operation": operation,
            "timestamp": datetime.now().isoformat(),
        }
        
        if data is not None:
            result["data"] = data
        
        if context:
            result["context"] = context
            
        return result
