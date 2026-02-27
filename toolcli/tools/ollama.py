"""Ollama integration for toolcli agent."""

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from toolcli.config import OllamaConfig


class OllamaClient:
    """Client for Ollama API."""
    
    def __init__(self, config: OllamaConfig):
        self.config = config
        self.base_url = config.host.rstrip("/")
        self.client = httpx.AsyncClient(timeout=config.timeout)
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Send chat request to Ollama."""
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
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate completion from Ollama."""
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
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models."""
        response = await self.client.get(f"{self.base_url}/api/tags")
        response.raise_for_status()
        data = response.json()
        return data.get("models", [])
    
    async def embed(
        self,
        text: str,
        model: str = "bge-m3",
    ) -> List[float]:
        """Get embeddings for text."""
        response = await self.client.post(
            f"{self.base_url}/api/embed",
            json={"model": model, "input": text}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embeddings", [[]])[0]
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


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
        """Perform reasoning on a task."""
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
        
        response = await self.client.chat(
            messages=messages,
            tools=tools,
        )
        
        return {
            "reasoning": response.get("message", {}).get("content", ""),
            "tool_calls": response.get("message", {}).get("tool_calls", []),
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
        
        response = await self.client.generate(prompt=prompt)
        content = response.get("response", "{}")
        
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
