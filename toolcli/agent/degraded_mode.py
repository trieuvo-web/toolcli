"""Degraded mode handler for graceful service degradation."""

import asyncio
from enum import Enum, auto
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime


class ServiceHealth(Enum):
    """Health status of a service."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Slow or intermittent failures
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass
class ServiceStatus:
    """Status of a single service."""
    name: str
    health: ServiceHealth
    last_check: datetime
    error: Optional[str] = None
    latency_ms: Optional[float] = None
    fallback_available: bool = False


class DegradedModeHandler:
    """Handle agent operation when services are degraded.
    
    Provides graceful degradation by:
    1. Checking health of all services
    2. Determining available capabilities
    3. Executing with fallbacks when primary services fail
    """
    
    def __init__(self, agent):
        """Initialize degraded mode handler.
        
        Args:
            agent: ToolcliAgent instance
        """
        self.agent = agent
        self.service_status: Dict[str, ServiceStatus] = {}
        self._last_full_check: Optional[datetime] = None
    
    async def check_all_services(self, force: bool = False) -> Dict[str, Any]:
        """Check health of all external services.
        
        Args:
            force: Force check even if recent check exists
            
        Returns:
            Dictionary with service statuses and overall health
        """
        # Skip if checked recently (within 30 seconds)
        if (not force and self._last_full_check and
            (datetime.now() - self._last_full_check).total_seconds() < 30):
            return self._get_current_status()
        
        # Check each service
        checks = await asyncio.gather(
            self._check_ollama(),
            self._check_opencode(),
            self._check_github(),
            return_exceptions=True,
        )
        
        self.service_status = {
            "ollama": checks[0] if not isinstance(checks[0], Exception) else ServiceStatus(
                name="ollama",
                health=ServiceHealth.UNKNOWN,
                last_check=datetime.now(),
                error=str(checks[0]),
            ),
            "opencode": checks[1] if not isinstance(checks[1], Exception) else ServiceStatus(
                name="opencode",
                health=ServiceHealth.UNKNOWN,
                last_check=datetime.now(),
                error=str(checks[1]),
            ),
            "github": checks[2] if not isinstance(checks[2], Exception) else ServiceStatus(
                name="github",
                health=ServiceHealth.UNKNOWN,
                last_check=datetime.now(),
                error=str(checks[2]),
            ),
        }
        
        self._last_full_check = datetime.now()
        
        return self._get_current_status()
    
    async def _check_ollama(self) -> ServiceStatus:
        """Check Ollama health."""
        start = datetime.now()
        try:
            result = await self.agent.ollama.health_check()
            latency = (datetime.now() - start).total_seconds() * 1000
            
            if result.get("healthy"):
                health = ServiceHealth.HEALTHY
            else:
                health = ServiceHealth.UNAVAILABLE
            
            return ServiceStatus(
                name="ollama",
                health=health,
                last_check=datetime.now(),
                error=result.get("error"),
                latency_ms=latency,
                fallback_available=False,  # No fallback for Ollama
            )
        except Exception as e:
            return ServiceStatus(
                name="ollama",
                health=ServiceHealth.UNAVAILABLE,
                last_check=datetime.now(),
                error=str(e),
                fallback_available=False,
            )
    
    async def _check_opencode(self) -> ServiceStatus:
        """Check OpenCode CLI availability."""
        import subprocess
        start = datetime.now()
        
        try:
            result = subprocess.run(
                ["opencode", "--version"],
                capture_output=True,
                timeout=5,
            )
            latency = (datetime.now() - start).total_seconds() * 1000
            
            if result.returncode == 0:
                return ServiceStatus(
                    name="opencode",
                    health=ServiceHealth.HEALTHY,
                    last_check=datetime.now(),
                    latency_ms=latency,
                    fallback_available=False,
                )
            else:
                return ServiceStatus(
                    name="opencode",
                    health=ServiceHealth.UNAVAILABLE,
                    last_check=datetime.now(),
                    error=result.stderr.decode() if result.stderr else "Unknown error",
                    fallback_available=False,
                )
        except subprocess.TimeoutExpired:
            return ServiceStatus(
                name="opencode",
                health=ServiceHealth.DEGRADED,
                last_check=datetime.now(),
                error="Timeout checking OpenCode version",
                fallback_available=False,
            )
        except FileNotFoundError:
            return ServiceStatus(
                name="opencode",
                health=ServiceHealth.UNAVAILABLE,
                last_check=datetime.now(),
                error="OpenCode CLI not found in PATH",
                fallback_available=False,
            )
        except Exception as e:
            return ServiceStatus(
                name="opencode",
                health=ServiceHealth.UNKNOWN,
                last_check=datetime.now(),
                error=str(e),
                fallback_available=False,
            )
    
    async def _check_github(self) -> ServiceStatus:
        """Check GitHub CLI authentication."""
        start = datetime.now()
        
        try:
            result = await self.agent.github._run_gh(["auth", "status"])
            latency = (datetime.now() - start).total_seconds() * 1000
            
            if result.get("success"):
                return ServiceStatus(
                    name="github",
                    health=ServiceHealth.HEALTHY,
                    last_check=datetime.now(),
                    latency_ms=latency,
                    fallback_available=True,  # Can use git directly
                )
            else:
                return ServiceStatus(
                    name="github",
                    health=ServiceHealth.UNAVAILABLE,
                    last_check=datetime.now(),
                    error=result.get("error", "Not authenticated"),
                    fallback_available=True,
                )
        except Exception as e:
            return ServiceStatus(
                name="github",
                health=ServiceHealth.UNAVAILABLE,
                last_check=datetime.now(),
                error=str(e),
                fallback_available=True,
            )
    
    def _get_current_status(self) -> Dict[str, Any]:
        """Get current status as dictionary."""
        return {
            "services": {
                name: {
                    "health": status.health.value,
                    "last_check": status.last_check.isoformat(),
                    "error": status.error,
                    "latency_ms": status.latency_ms,
                    "fallback_available": status.fallback_available,
                }
                for name, status in self.service_status.items()
            },
            "overall_status": self._determine_overall_status(),
            "capabilities": self._get_available_capabilities(),
            "degraded": self._is_degraded(),
        }
    
    def _determine_overall_status(self) -> str:
        """Determine overall agent status."""
        if not self.service_status:
            return "unknown"
        
        healths = [s.health for s in self.service_status.values()]
        
        if all(h == ServiceHealth.HEALTHY for h in healths):
            return "healthy"
        elif all(h == ServiceHealth.UNAVAILABLE for h in healths):
            return "unavailable"
        else:
            return "degraded"
    
    def _is_degraded(self) -> bool:
        """Check if any service is degraded."""
        return any(
            s.health != ServiceHealth.HEALTHY
            for s in self.service_status.values()
        )
    
    def _get_available_capabilities(self) -> List[str]:
        """List capabilities available in current state."""
        capabilities = []
        
        ollama = self.service_status.get("ollama")
        if ollama and ollama.health == ServiceHealth.HEALTHY:
            capabilities.extend([
                "reasoning",
                "analysis",
                "chat",
                "code_generation",
            ])
        
        opencode = self.service_status.get("opencode")
        if opencode and opencode.health == ServiceHealth.HEALTHY:
            capabilities.extend([
                "openspec_workflow",
                "file_creation",
                "codebase_analysis",
            ])
        
        github = self.service_status.get("github")
        if github and github.health == ServiceHealth.HEALTHY:
            capabilities.extend([
                "repo_management",
                "issue_tracking",
                "pr_management",
            ])
        elif github and github.fallback_available:
            # Git operations still available via git CLI
            capabilities.extend([
                "git_operations",
            ])
        
        # Always available (local operations)
        capabilities.extend([
            "state_management",
            "task_queue",
            "heartbeat",
            "logging",
        ])
        
        return capabilities
    
    async def execute_with_fallback(
        self,
        service_name: str,
        primary_func: Callable,
        fallback_func: Optional[Callable] = None,
        *args,
        **kwargs
    ) -> Any:
        """Execute with fallback if service degraded.
        
        Args:
            service_name: Name of service to check
            primary_func: Primary function to execute
            fallback_func: Optional fallback function
            *args, **kwargs: Arguments for functions
            
        Returns:
            Result from primary or fallback function
        """
        status = self.service_status.get(service_name)
        
        # Check health first if not checked recently
        if not status or (datetime.now() - status.last_check).total_seconds() > 60:
            await self.check_all_services()
            status = self.service_status.get(service_name)
        
        # If service unavailable and fallback provided, use fallback
        if status and status.health == ServiceHealth.UNAVAILABLE:
            if fallback_func:
                print(f"[DegradedMode] {service_name} unavailable, using fallback")
                return await fallback_func(*args, **kwargs)
            else:
                return {
                    "success": False,
                    "error": f"{service_name} is unavailable and no fallback provided",
                    "degraded": True,
                    "suggested_action": "Check service status or provide fallback",
                }
        
        # Try primary function
        try:
            return await primary_func(*args, **kwargs)
        except Exception as e:
            # If failed and fallback available, try fallback
            if fallback_func and status and status.fallback_available:
                print(f"[DegradedMode] {service_name} failed ({e}), using fallback")
                return await fallback_func(*args, **kwargs)
            raise
    
    def can_execute(self, capability: str) -> bool:
        """Check if a capability is available."""
        return capability in self._get_available_capabilities()
