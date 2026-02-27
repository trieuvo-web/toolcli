"""Core agent implementation for toolcli."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from toolcli.config import ToolcliConfig
from toolcli.heartbeat.core import (
    AgentState,
    AgentTask,
    HeartbeatLogger,
    HeartbeatLoop,
    StateManager,
    TaskStatus,
)
from toolcli.tools.github import GitHubClient
from toolcli.tools.ollama import OllamaClient, ReasoningEngine
from toolcli.tools.opencode import OpencodeClient


class ToolcliAgent:
    """Main toolcli agent that orchestrates OpenSpec workflows."""
    
    def __init__(self, config: Optional[ToolcliConfig] = None):
        self.config = config or ToolcliConfig.load()
        
        # Initialize tool clients
        self.ollama = OllamaClient(self.config.ollama)
        self.reasoning = ReasoningEngine(self.ollama)
        self.opencode = OpencodeClient(self.config.opencode)
        self.github = GitHubClient(self.config.github)
        
        # Initialize heartbeat
        state_file = Path(self.config.heartbeat.state_file).expanduser()
        log_file = Path(self.config.heartbeat.log_file).expanduser()
        
        self.state_manager = StateManager(state_file)
        self.heartbeat_logger = HeartbeatLogger(log_file)
        self.heartbeat = HeartbeatLoop(
            self.state_manager,
            self.heartbeat_logger,
            self.config.heartbeat.interval,
        )
        
        # Set task processor
        self.heartbeat.set_task_processor(self._process_task)
        
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        if self._initialized:
            return
        
        # Resume any interrupted tasks
        interrupted = await self.heartbeat.resume_interrupted_tasks()
        if interrupted:
            print(f"Resuming {len(interrupted)} interrupted tasks")
        
        self._initialized = True
    
    async def close(self) -> None:
        """Cleanup resources."""
        await self.ollama.close()
    
    async def _process_task(self, task: AgentTask) -> Dict[str, Any]:
        """Process a single task based on its type."""
        processors = {
            "openspec": self._process_openspec_task,
            "opencode": self._process_opencode_task,
            "github": self._process_github_task,
            "reasoning": self._process_reasoning_task,
        }
        
        processor = processors.get(task.type)
        if not processor:
            raise ValueError(f"Unknown task type: {task.type}")
        
        return await processor(task)
    
    async def _process_openspec_task(self, task: AgentTask) -> Dict[str, Any]:
        """Process an OpenSpec workflow task."""
        action = task.params.get("action")
        
        if action == "explore":
            result = await self.opencode.explore(
                topic=task.params.get("topic", ""),
                cwd=Path(task.params.get("cwd", self.config.opencode.workspace)),
            )
        elif action == "new":
            result = await self.opencode.new_change(
                name=task.params.get("name", ""),
                cwd=Path(task.params.get("cwd", self.config.opencode.workspace)),
            )
        elif action == "continue":
            result = await self.opencode.continue_change(
                cwd=Path(task.params.get("cwd", self.config.opencode.workspace)),
            )
        elif action == "apply":
            result = await self.opencode.apply_change(
                cwd=Path(task.params.get("cwd", self.config.opencode.workspace)),
            )
        elif action == "verify":
            result = await self.opencode.verify_change(
                name=task.params.get("name", ""),
                cwd=Path(task.params.get("cwd", self.config.opencode.workspace)),
            )
        else:
            raise ValueError(f"Unknown OpenSpec action: {action}")
        
        return result
    
    async def _process_opencode_task(self, task: AgentTask) -> Dict[str, Any]:
        """Process an OpenCode task."""
        action = task.params.get("action")
        
        if action == "create_file":
            result = await self.opencode.create_file(
                file_path=task.params.get("file_path", ""),
                content=task.params.get("content", ""),
                description=task.params.get("description", ""),
            )
        elif action == "analyze":
            result = await self.opencode.analyze_codebase(
                query=task.params.get("query", ""),
            )
        else:
            # Generic command
            result = await self.opencode.run_openspec_command(
                command=task.params.get("command", ""),
                cwd=Path(task.params.get("cwd")) if task.params.get("cwd") else None,
            )
        
        return result
    
    async def _process_github_task(self, task: AgentTask) -> Dict[str, Any]:
        """Process a GitHub task."""
        action = task.params.get("action")
        
        if action == "create_repo":
            result = await self.github.create_repo(
                name=task.params.get("name", ""),
                description=task.params.get("description", ""),
                private=task.params.get("private", False),
            )
        elif action == "create_issue":
            result = await self.github.create_issue(
                title=task.params.get("title", ""),
                body=task.params.get("body", ""),
                repo=task.params.get("repo"),
                labels=task.params.get("labels"),
            )
        elif action == "create_pr":
            result = await self.github.create_pr(
                title=task.params.get("title", ""),
                body=task.params.get("body", ""),
                base=task.params.get("base", "main"),
                head=task.params.get("head"),
                repo=task.params.get("repo"),
            )
        elif action == "commit":
            result = await self.github.commit_and_push(
                message=task.params.get("message", ""),
                branch=task.params.get("branch"),
                cwd=task.params.get("cwd"),
            )
        else:
            raise ValueError(f"Unknown GitHub action: {action}")
        
        return result
    
    async def _process_reasoning_task(self, task: AgentTask) -> Dict[str, Any]:
        """Process a reasoning task using Ollama."""
        return await self.reasoning.reason(
            task=task.params.get("prompt", ""),
            context=task.params.get("context"),
            tools=task.params.get("tools"),
        )
    
    async def execute_task(
        self,
        task_type: str,
        description: str,
        params: Dict[str, Any],
        wait: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Execute a task immediately or queue it."""
        task = AgentTask(
            type=task_type,
            description=description,
            params=params,
        )
        
        if wait:
            # Execute immediately
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            result = await self._process_task(task)
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.result = result
            return result
        else:
            # Add to queue
            task_id = await self.heartbeat.add_task(task)
            return {"task_id": task_id, "status": "queued"}
    
    async def run_openspec_workflow(
        self,
        change_name: str,
        description: str,
        cwd: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Run a complete OpenSpec workflow."""
        workspace = cwd or Path(self.config.opencode.workspace).expanduser()
        
        # Step 1: Reason about the change
        print(f"🔍 Analyzing change: {change_name}")
        analysis = await self.reasoning.analyze_openspec_change(
            change_name=change_name,
            description=description,
        )
        
        results = {"analysis": analysis, "steps": []}
        
        # Step 2: Explore
        print(f"🔬 Exploring: {description}")
        explore_result = await self.opencode.explore(description, cwd=workspace)
        results["steps"].append({"action": "explore", "result": explore_result})
        
        # Step 3: Create change
        print(f"📝 Creating change: {change_name}")
        new_result = await self.opencode.new_change(change_name, cwd=workspace)
        results["steps"].append({"action": "new", "result": new_result})
        
        # Step 4: Continue (create spec)
        print(f"📋 Continuing workflow...")
        continue_result = await self.opencode.continue_change(cwd=workspace)
        results["steps"].append({"action": "continue", "result": continue_result})
        
        # Step 5: Apply
        print(f"🔨 Applying changes...")
        apply_result = await self.opencode.apply_change(cwd=workspace)
        results["steps"].append({"action": "apply", "result": apply_result})
        
        return results
    
    async def start_daemon(self) -> None:
        """Start the agent in daemon mode with heartbeat."""
        await self.initialize()
        print(f"🚀 Starting toolcli daemon (interval: {self.config.heartbeat.interval}s)")
        await self.heartbeat.start()
    
    def stop_daemon(self) -> None:
        """Stop the daemon."""
        print("🛑 Stopping toolcli daemon")
        self.heartbeat.stop()


from datetime import datetime
