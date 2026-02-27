"""Ollama integration for toolcli agent with resilience features."""

import json
import httpx
from typing import Any, Dict, List, Optional
from datetime import datetime

from toolcli.config import OllamaConfig
from toolcli.utils.resilience import with_retry, RetryConfig, ResilientClient, RetryExhaustedError
from toolcli.utils.error_context import ErrorContext
from toolcli.utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from toolcli.utils.logging import StructuredLogger
from toolcli.utils.metrics import MetricsCollector, TimedOperation


class OllamaClient(ResilientClient):
    """Client for Ollama API with resilience features.
    
    Features:
    - Health checking
    - Automatic retry with exponential backoff
    - Circuit breaker pattern
    - Enhanced error context
    - Metrics collection
    """
    
    def __init__(
        self,
        config: OllamaConfig,
        metrics: Optional[MetricsCollector] = None,
        logger: Optional[StructuredLogger] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        """Initialize Ollama client.
        
        Args:
            config: Ollama configuration
            metrics: Optional metrics collector
            logger: Optional structured logger
            circuit_breaker: Optional circuit breaker
        """
        super().__init__(RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            retryable_exceptions=(
                httpx.ConnectError,
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.ReadTimeout,
            )
        ))
        self.config = config
        self.base_url = config.host.rstrip("/")
        self.client = httpx.AsyncClient(timeout=config.timeout)
        self.metrics = metrics
        self.logger = logger or StructuredLogger("ollama")
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            name="ollama",
            failure_threshold=5,
            recovery_timeout=30,
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Ollama service health.
        
        Returns:
            Dictionary with health status and details
        """
        try:
            # Quick check - list models (lightweight)
            response = await self.client.get(
                f"{self.base_url}/api/tags",
                timeout=5.0  # Short timeout for health check
            )
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                
                result = {
                    "healthy": True,
                    "available_models": len(models),
                    "default_model_available": any(
                        m.get("name") == self.config.default_model
                        for m in models
                    ),
                    "latency_ms": response.elapsed.total_seconds() * 1000,
                    "timestamp": datetime.now().isoformat(),
                }
                
                self._update_health(result)
                return result
            else:
                result = {
                    "healthy": False,
                    "error": f"HTTP {response.status_code}",
                    "available_models": 0,
                    "default_model_available": False,
                    "timestamp": datetime.now().isoformat(),
                }
                self._update_health(result)
                return result
                
        except httpx.ConnectError as e:
            result = {
                "healthy": False,
                "error": "Connection refused - Ollama server not running",
                "error_type": "ConnectError",
                "retryable": True,
                "available_models": 0,
                "default_model_available": False,
                "timestamp": datetime.now().isoformat(),
            }
            self._update_health(result)
            return result
            
        except Exception as e:
            result = {
                "healthy": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "retryable": True,
                "available_models": 0,
                "default_model_available": False,
                "timestamp": datetime.now().isoformat(),
            }
            self._update_health(result)
            return result
    
    @with_retry(RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        retryable_exceptions=(
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.ReadTimeout,
        )
    ))
    async def _chat_with_retry(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Internal chat method with retry."""
        payload = {
            "model": model or self.config.default_model,
            "messages": messages,
            "stream": stream,
        }
        
        if tools:
            payload["tools"] = tools
        
        response = await self.client.post(
            f"{self.base_url}/api/chat",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Send chat request to Ollama with circuit breaker and metrics.
        
        Args:
            messages: List of message dicts with role and content
            model: Model name (defaults to config)
            tools: Optional tool definitions
            stream: Whether to stream response
            
        Returns:
            Response dictionary or enriched error
        """
        start_time = datetime.now()
        operation = "chat"
        
        try:
            # Use circuit breaker
            result = await self.circuit_breaker.call(
                self._chat_with_retry,
                messages, model, tools, stream
            )
            
            # Record metrics
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            if self.metrics:
                self.metrics.record(
                    service="ollama",
                    operation=operation,
                    success=True,
                    duration_ms=duration_ms,
                )
            
            # Log
            self.logger.tool_call(
                service="ollama",
                operation=operation,
                success=True,
                duration_ms=duration_ms,
                context={"model": model or self.config.default_model},
            )
            
            return {"success": True, "data": result}
            
        except CircuitBreakerOpenError as e:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            if self.metrics:
                self.metrics.record(
                    service="ollama",
                    operation=operation,
                    success=False,
                    duration_ms=duration_ms,
                    error_type="CircuitBreakerOpenError",
                )
            
            return ErrorContext.enrich(
                error=e,
                operation=operation,
                service_name="ollama",
                context={"circuit_state": self.circuit_breaker.state.value},
            )
            
        except RetryExhaustedError as e:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            if self.metrics:
                self.metrics.record(
                    service="ollama",
                    operation=operation,
                    success=False,
                    duration_ms=duration_ms,
                    error_type="RetryExhaustedError",
                )
            
            return ErrorContext.enrich(
                error=e.original_error,
                operation=operation,
                service_name="ollama",
                context={"attempts": e.attempts},
            )
            
        except Exception as e:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            if self.metrics:
                self.metrics.record(
                    service="ollama",
                    operation=operation,
                    success=False,
                    duration_ms=duration_ms,
                    error_type=type(e).__name__,
                )
            
            self.logger.error(
                message=f"Ollama chat failed: {e}",
                error=e,
                service="ollama",
                operation=operation,
            )
            
            return ErrorContext.enrich(
                error=e,
                operation=operation,
                service_name="ollama",
                context={"model": model or self.config.default_model},
            )
    
    @with_retry(RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        retryable_exceptions=(
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.ReadTimeout,
        )
    ))
    async def _generate_with_retry(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Internal generate method with retry."""
        payload = {
            "model": model or self.config.default_model,
            "prompt": prompt,
            "stream": False,
        }
        
        if system:
            payload["system"] = system
        
        response = await self.client.post(
            f"{self.base_url}/api/generate",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate completion from Ollama with resilience.
        
        Args:
            prompt: Generation prompt
            model: Model name (defaults to config)
            system: Optional system prompt
            
        Returns:
            Response dictionary or enriched error
        """
        start_time = datetime.now()
        operation = "generate"
        
        try:
            result = await self.circuit_breaker.call(
                self._generate_with_retry,
                prompt, model, system
            )
            
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            if self.metrics:
                self.metrics.record(
                    service="ollama",
                    operation=operation,
                    success=True,
                    duration_ms=duration_ms,
                )
            
            return {"success": True, "data": result}
            
        except CircuitBreakerOpenError as e:
            return ErrorContext.enrich(
                error=e,
                operation=operation,
                service_name="ollama",
            )
            
        except RetryExhaustedError as e:
            return ErrorContext.enrich(
                error=e.original_error,
                operation=operation,
                service_name="ollama",
                context={"attempts": e.attempts},
            )
            
        except Exception as e:
            if self.metrics:
                self.metrics.record(
                    service="ollama",
                    operation=operation,
                    success=False,
                    duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
                    error_type=type(e).__name__,
                )
            
            return ErrorContext.enrich(
                error=e,
                operation=operation,
                service_name="ollama",
            )
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models with error handling."""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
        except Exception as e:
            self.logger.error(
                message=f"Failed to list models: {e}",
                error=e,
                service="ollama",
                operation="list_models",
            )
            return []
    
    async def embed(
        self,
        text: str,
        model: str = "bge-m3",
    ) -> List[float]:
        """Get embeddings for text with error handling."""
        try:
            response = await self.client.post(
                f"{self.base_url}/api/embed",
                json={"model": model, "input": text}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("embeddings", [[]])[0]
        except Exception as e:
            self.logger.error(
                message=f"Failed to get embeddings: {e}",
                error=e,
                service="ollama",
                operation="embed",
            )
            return []
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
    
    def get_circuit_state(self) -> Dict[str, Any]:
        """Get circuit breaker state."""
        return self.circuit_breaker.get_state_dict()


class ReasoningEngine:
    """Ollama-based reasoning engine for the agent."""
    
    SYSTEM_PROMPT = """You are an intelligent CLI agent assistant. Your job is to:
1. Analyze user requests and determine the best course of action
2. Select appropriate tools and workflows to accomplish tasks
3. Reason through complex problems step by step
4. Make decisions about when to delegate to OpenCode, use GitHub CLI, or handle directly

When responding, provide:
- Your reasoning process
- The specific action to take
- Any parameters or context needed"""
    
    def __init__(self, client: OllamaClient):
        self.client = client
    
    async def reason(
        self,
        task: str,
        context: Optional[Dict] = None,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Perform reasoning on a task with resilience."""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
        ]
        
        if context:
            context_str = json.dumps(context, indent=2)
            messages.append({
                "role": "system",
                "content": f"Context: {context_str}"
            })
        
        messages.append({"role": "user", "content": task})
        
        result = await self.client.chat(
            messages=messages,
            tools=tools,
        )
        
        if result.get("success"):
            response = result["data"]
            return {
                "success": True,
                "reasoning": response.get("message", {}).get("content", ""),
                "tool_calls": response.get("message", {}).get("tool_calls", []),
            }
        else:
            return {
                "success": False,
                "error": result.get("error"),
                "error_type": result.get("error_type"),
                "suggested_action": result.get("suggested_action"),
            }
    
    async def analyze_openspec_change(
        self,
        change_name: str,
        description: str,
    ) -> Dict[str, Any]:
        """Analyze an OpenSpec change and determine workflow steps."""
        prompt = f"""Analyze this OpenSpec change:
Name: {change_name}
Description: {description}

Determine:
1. What type of change is this? (feature, bugfix, refactor, etc.)
2. What OpenSpec workflow commands are needed?
3. What tools should be used? (opencode, gh, git)
4. What are the potential risks or blockers?

Provide your analysis in JSON format:
{{
    "change_type": "...",
    "workflow_steps": ["..."],
    "tools_required": ["..."],
    "risks": ["..."]
}}"""
        
        result = await self.client.generate(prompt=prompt)
        
        if not result.get("success"):
            return {
                "change_type": "unknown",
                "workflow_steps": [],
                "tools_required": [],
                "risks": [f"Failed to analyze: {result.get('error')}"],
            }
        
        content = result["data"].get("response", "{}")
        
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "change_type": "unknown",
                "workflow_steps": [],
                "tools_required": [],
                "risks": ["Failed to parse analysis"],
                "raw_response": content,
            }
