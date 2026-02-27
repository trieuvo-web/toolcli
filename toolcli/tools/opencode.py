"""OpenCode CLI integration for toolcli with resilience features."""

import asyncio
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from toolcli.config import OpencodeConfig
from toolcli.utils.error_context import ErrorContext
from toolcli.utils.logging import StructuredLogger
from toolcli.utils.metrics import MetricsCollector


class OpencodeClient:
    """Client for OpenCode CLI with resilience features.
    
    Features:
    - Health checking
    - Timeout handling
    - Enhanced error context
    - Metrics collection
    """
    
    def __init__(
        self,
        config: OpencodeConfig,
        metrics: Optional[MetricsCollector] = None,
        logger: Optional[StructuredLogger] = None,
    ):
        """Initialize OpenCode client.
        
        Args:
            config: OpenCode configuration
            metrics: Optional metrics collector
            logger: Optional structured logger
        """
        self.config = config
        self.workspace = Path(config.workspace).expanduser()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.metrics = metrics
        self.logger = logger or StructuredLogger("opencode")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check OpenCode CLI health.
        
        Returns:
            Dictionary with health status
        """
        start_time = datetime.now()
        
        try:
            # Check if opencode command exists
            result = subprocess.run(
                ["opencode", "--version"],
                capture_output=True,
                timeout=5,
            )
            
            latency_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            if result.returncode == 0:
                version = result.stdout.decode().strip()
                return {
                    "healthy": True,
                    "version": version,
                    "latency_ms": latency_ms,
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                return {
                    "healthy": False,
                    "error": result.stderr.decode() if result.stderr else "Unknown error",
                    "latency_ms": latency_ms,
                    "timestamp": datetime.now().isoformat(),
                }
                
        except subprocess.TimeoutExpired:
            return {
                "healthy": False,
                "error": "Timeout checking OpenCode version",
                "error_type": "TimeoutExpired",
                "retryable": True,
                "timestamp": datetime.now().isoformat(),
            }
            
        except FileNotFoundError:
            return {
                "healthy": False,
                "error": "OpenCode CLI not found in PATH",
                "error_type": "FileNotFoundError",
                "retryable": False,
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "retryable": True,
                "timestamp": datetime.now().isoformat(),
            }
    
    async def run_openspec_command(
        self,
        command: str,
        cwd: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Run an OpenSpec slash command with resilience.
        
        Args:
            command: OpenSpec command to run
            cwd: Working directory
            
        Returns:
            Result dictionary with success status
        """
        start_time = datetime.now()
        operation = "run_openspec_command"
        
        cmd = [
            "opencode", "run",
            f"{command}",
            "--agent", self.config.agent,
        ]
        
        if cwd:
            cmd.extend(["--cwd", str(cwd)])
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd or self.workspace,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.timeout,
            )
            
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            success = process.returncode == 0
            
            # Record metrics
            if self.metrics:
                self.metrics.record(
                    service="opencode",
                    operation=operation,
                    success=success,
                    duration_ms=duration_ms,
                )
            
            # Log
            self.logger.tool_call(
                service="opencode",
                operation=operation,
                success=success,
                duration_ms=duration_ms,
                context={"command": command[:50]},
            )
            
            return {
                "success": success,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": process.returncode,
                "duration_ms": duration_ms,
            }
            
        except asyncio.TimeoutError:
            process.kill()
            
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            if self.metrics:
                self.metrics.record(
                    service="opencode",
                    operation=operation,
                    success=False,
                    duration_ms=duration_ms,
                    error_type="TimeoutError",
                )
            
            self.logger.error(
                message=f"OpenCode command timed out after {self.config.timeout}s",
                service="opencode",
                operation=operation,
                context={"command": command[:50]},
            )
            
            return ErrorContext.enrich(
                error=asyncio.TimeoutError(f"Command timed out after {self.config.timeout}s"),
                operation=operation,
                service_name="opencode",
                context={"command": command[:50], "timeout": self.config.timeout},
            )
            
        except Exception as e:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            if self.metrics:
                self.metrics.record(
                    service="opencode",
                    operation=operation,
                    success=False,
                    duration_ms=duration_ms,
                    error_type=type(e).__name__,
                )
            
            self.logger.error(
                message=f"OpenCode command failed: {e}",
                error=e,
                service="opencode",
                operation=operation,
            )
            
            return ErrorContext.enrich(
                error=e,
                operation=operation,
                service_name="opencode",
                context={"command": command[:50]},
            )
    
    async def explore(
        self,
        topic: str,
        cwd: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Run OpenSpec explore phase."""
        return await self.run_openspec_command(
            f"/opsx-explore {topic}",
            cwd=cwd,
        )
    
    async def new_change(
        self,
        name: str,
        cwd: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Create new OpenSpec change."""
        return await self.run_openspec_command(
            f"/opsx-new {name}",
            cwd=cwd,
        )
    
    async def continue_change(
        self,
        cwd: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Continue OpenSpec workflow."""
        return await self.run_openspec_command(
            "/opsx-continue",
            cwd=cwd,
        )
    
    async def apply_change(
        self,
        cwd: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Apply/Implement OpenSpec tasks."""
        return await self.run_openspec_command(
            "/opsx-apply",
            cwd=cwd,
        )
    
    async def verify_change(
        self,
        name: str,
        cwd: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Verify OpenSpec change."""
        return await self.run_openspec_command(
            f"/opsx-verify {name}",
            cwd=cwd,
        )
    
    async def create_file(
        self,
        file_path: str,
        content: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """Create a file using OpenCode."""
        start_time = datetime.now()
        operation = "create_file"
        
        cmd = [
            "opencode", "run",
            f"Create file {file_path}: {description}",
            "--agent", "build",
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.timeout,
            )
            
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            success = process.returncode == 0
            
            if self.metrics:
                self.metrics.record(
                    service="opencode",
                    operation=operation,
                    success=success,
                    duration_ms=duration_ms,
                )
            
            return {
                "success": success,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
            }
            
        except asyncio.TimeoutError:
            process.kill()
            return ErrorContext.enrich(
                error=asyncio.TimeoutError(f"File creation timed out"),
                operation=operation,
                service_name="opencode",
                context={"file_path": file_path},
            )
            
        except Exception as e:
            return ErrorContext.enrich(
                error=e,
                operation=operation,
                service_name="opencode",
                context={"file_path": file_path},
            )
    
    async def analyze_codebase(
        self,
        query: str,
    ) -> Dict[str, Any]:
        """Analyze codebase using OpenCode."""
        start_time = datetime.now()
        operation = "analyze_codebase"
        
        cmd = [
            "opencode", "run",
            f"Analyze codebase: {query}",
            "--agent", "plan",
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            success = process.returncode == 0
            
            if self.metrics:
                self.metrics.record(
                    service="opencode",
                    operation=operation,
                    success=success,
                    duration_ms=duration_ms,
                )
            
            return {
                "success": success,
                "analysis": stdout.decode(),
                "errors": stderr.decode(),
            }
            
        except Exception as e:
            return ErrorContext.enrich(
                error=e,
                operation=operation,
                service_name="opencode",
                context={"query": query[:100]},
            )
