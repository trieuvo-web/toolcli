"""Heartbeat mechanism for toolcli agent persistence."""

import asyncio
import json
import logging
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class AgentTask(BaseModel):
    """Represents a task in the agent queue."""
    id: str = Field(default_factory=lambda: f"task_{int(time.time() * 1000)}")
    type: str  # "openspec", "opencode", "github", "reasoning"
    description: str
    params: Dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    parent_task_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "params": self.params,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "result": self.result,
            "error": self.error,
            "parent_task_id": self.parent_task_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTask":
        """Create from dictionary."""
        data = data.copy()
        data["status"] = TaskStatus(data["status"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data["started_at"]:
            data["started_at"] = datetime.fromisoformat(data["started_at"])
        if data["completed_at"]:
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])
        return cls(**data)


class AgentState(BaseModel):
    """Persistent state for the agent."""
    agent_id: str = Field(default="toolcli-agent")
    version: str = "0.1.0"
    tasks: List[AgentTask] = Field(default_factory=list)
    current_task_id: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    config: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def get_pending_tasks(self) -> List[AgentTask]:
        """Get all pending tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]
    
    def get_failed_tasks(self) -> List[AgentTask]:
        """Get all failed tasks eligible for retry."""
        return [
            t for t in self.tasks
            if t.status == TaskStatus.FAILED and t.retry_count < t.max_retries
        ]
    
    def get_task_by_id(self, task_id: str) -> Optional[AgentTask]:
        """Get task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None


class HeartbeatLogger:
    """Logger for heartbeat events."""
    
    def __init__(self, log_file: Path):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Configure logging
        self.logger = logging.getLogger("toolcli.heartbeat")
        self.logger.setLevel(logging.INFO)
        
        # File handler
        handler = logging.FileHandler(self.log_file)
        handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(handler)
    
    def log_heartbeat(self, state: AgentState) -> None:
        """Log a heartbeat event."""
        self.logger.info(
            f"Heartbeat - Tasks: {len(state.tasks)}, "
            f"Pending: {len(state.get_pending_tasks())}, "
            f"Completed: {state.total_tasks_completed}, "
            f"Failed: {state.total_tasks_failed}"
        )
    
    def log_task_start(self, task: AgentTask) -> None:
        """Log task start."""
        self.logger.info(f"Task started: {task.id} - {task.description}")
    
    def log_task_complete(self, task: AgentTask) -> None:
        """Log task completion."""
        self.logger.info(f"Task completed: {task.id}")
    
    def log_task_fail(self, task: AgentTask, error: str) -> None:
        """Log task failure."""
        self.logger.error(f"Task failed: {task.id} - {error}")
    
    def log_retry(self, task: AgentTask) -> None:
        """Log task retry."""
        self.logger.warning(
            f"Task retry: {task.id} - Attempt {task.retry_count + 1}/{task.max_retries}"
        )


class StateManager:
    """Manages agent state persistence."""
    
    def __init__(self, state_file: Path):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
    
    async def load(self) -> AgentState:
        """Load state from file."""
        async with self._lock:
            if not self.state_file.exists():
                return AgentState()
            
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                
                # Convert task dicts back to objects
                tasks = [AgentTask.from_dict(t) for t in data.get("tasks", [])]
                data["tasks"] = tasks
                
                return AgentState(**data)
            except (json.JSONDecodeError, KeyError) as e:
                logging.error(f"Failed to load state: {e}")
                return AgentState()
    
    async def save(self, state: AgentState) -> None:
        """Save state to file."""
        async with self._lock:
            # Convert tasks to dicts for serialization
            data = state.model_dump()
            data["tasks"] = [t.to_dict() for t in state.tasks]
            
            # Write atomically
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)
            
            temp_file.rename(self.state_file)


class HeartbeatLoop:
    """Main heartbeat loop for the agent."""
    
    def __init__(
        self,
        state_manager: StateManager,
        logger: HeartbeatLogger,
        interval: int = 300,
    ):
        self.state_manager = state_manager
        self.logger = logger
        self.interval = interval
        self._running = False
        self._task_processor: Optional[callable] = None
    
    def set_task_processor(self, processor: callable) -> None:
        """Set the function to process tasks."""
        self._task_processor = processor
    
    async def start(self) -> None:
        """Start the heartbeat loop."""
        self._running = True
        
        while self._running:
            try:
                await self._beat()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Heartbeat error: {e}")
                await asyncio.sleep(self.interval)
    
    async def _beat(self) -> None:
        """Execute a single heartbeat."""
        # Load current state
        state = await self.state_manager.load()
        state.last_heartbeat = datetime.now()
        
        # Log heartbeat
        self.logger.log_heartbeat(state)
        
        # Process pending tasks
        if self._task_processor:
            pending = state.get_pending_tasks()
            failed = state.get_failed_tasks()
            
            for task in pending + failed:
                if task.status == TaskStatus.FAILED:
                    task.status = TaskStatus.RETRYING
                    task.retry_count += 1
                    self.logger.log_retry(task)
                else:
                    task.status = TaskStatus.RUNNING
                    task.started_at = datetime.now()
                    self.logger.log_task_start(task)
                
                try:
                    result = await self._task_processor(task)
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.now()
                    task.result = result
                    state.total_tasks_completed += 1
                    self.logger.log_task_complete(task)
                except Exception as e:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    state.total_tasks_failed += 1
                    self.logger.log_task_fail(task, str(e))
                
                state.current_task_id = None
                await self.state_manager.save(state)
        
        # Save updated state
        await self.state_manager.save(state)
    
    def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
    
    async def add_task(self, task: AgentTask) -> str:
        """Add a new task to the queue."""
        state = await self.state_manager.load()
        state.tasks.append(task)
        await self.state_manager.save(state)
        return task.id
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task."""
        state = await self.state_manager.load()
        task = state.get_task_by_id(task_id)
        return task.to_dict() if task else None
    
    async def resume_interrupted_tasks(self) -> List[AgentTask]:
        """Resume tasks that were interrupted (e.g., agent crash)."""
        state = await self.state_manager.load()
        
        interrupted = [
            t for t in state.tasks
            if t.status == TaskStatus.RUNNING
        ]
        
        # Mark interrupted tasks for retry
        for task in interrupted:
            task.status = TaskStatus.RETRYING
            task.retry_count += 1
        
        await self.state_manager.save(state)
        
        return interrupted
