"""Structured logging for toolcli observability."""

import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


class StructuredLogFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, "event_type"):
            log_entry["event_type"] = record.event_type
        if hasattr(record, "context"):
            log_entry["context"] = record.context
        if hasattr(record, "service"):
            log_entry["service"] = record.service
        if hasattr(record, "operation"):
            log_entry["operation"] = record.operation
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "success"):
            log_entry["success"] = record.success
            
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry, default=str)


class StructuredLogger:
    """Structured JSON logger for toolcli."""
    
    def __init__(self, name: str, log_file: Optional[Path] = None):
        """Initialize structured logger.
        
        Args:
            name: Logger name
            log_file: Optional file path for logging
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Clear existing handlers
        self.logger.handlers = []
        
        # Console handler with JSON format
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(StructuredLogFormatter())
        self.logger.addHandler(console_handler)
        
        # File handler if specified
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(StructuredLogFormatter())
            self.logger.addHandler(file_handler)
    
    def log_event(
        self,
        event_type: str,
        message: str,
        level: str = "info",
        service: Optional[str] = None,
        operation: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        success: Optional[bool] = None,
    ):
        """Log a structured event.
        
        Args:
            event_type: Type of event (e.g., "tool_call", "heartbeat")
            message: Log message
            level: Log level (debug, info, warning, error, critical)
            service: Service name (e.g., "ollama", "github")
            operation: Operation name (e.g., "generate", "create_repo")
            context: Additional context dictionary
            duration_ms: Operation duration in milliseconds
            success: Whether operation succeeded
        """
        extra = {
            "event_type": event_type,
        }
        
        if service:
            extra["service"] = service
        if operation:
            extra["operation"] = operation
        if context:
            extra["context"] = context
        if duration_ms is not None:
            extra["duration_ms"] = duration_ms
        if success is not None:
            extra["success"] = success
        
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(message, extra=extra)
    
    def tool_call(
        self,
        service: str,
        operation: str,
        success: bool,
        duration_ms: float,
        message: str = "",
        context: Optional[Dict[str, Any]] = None,
    ):
        """Log a tool/service call."""
        self.log_event(
            event_type="tool_call",
            message=message or f"{service}.{operation} {'succeeded' if success else 'failed'}",
            level="info" if success else "warning",
            service=service,
            operation=operation,
            success=success,
            duration_ms=duration_ms,
            context=context,
        )
    
    def heartbeat(
        self,
        tasks_total: int,
        tasks_pending: int,
        tasks_completed: int,
        tasks_failed: int,
    ):
        """Log heartbeat event."""
        self.log_event(
            event_type="heartbeat",
            message=f"Heartbeat - {tasks_pending} pending, {tasks_completed} completed",
            level="debug",
            context={
                "tasks_total": tasks_total,
                "tasks_pending": tasks_pending,
                "tasks_completed": tasks_completed,
                "tasks_failed": tasks_failed,
            }
        )
    
    def error(
        self,
        message: str,
        error: Optional[Exception] = None,
        service: Optional[str] = None,
        operation: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Log error event."""
        extra = {
            "event_type": "error",
        }
        
        if service:
            extra["service"] = service
        if operation:
            extra["operation"] = operation
        if context:
            extra["context"] = context
        
        if error:
            extra["context"] = extra.get("context", {})
            extra["context"]["error_type"] = type(error).__name__
        
        self.logger.error(message, extra=extra, exc_info=error is not None)
