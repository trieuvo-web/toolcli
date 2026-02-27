"""Configuration management for toolcli."""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class OllamaConfig(BaseModel):
    """Ollama configuration."""
    host: str = Field(default="http://localhost:11434", description="Ollama server host")
    default_model: str = Field(default="qwen3:32b", description="Default model for reasoning")
    timeout: int = Field(default=120, description="Request timeout in seconds")


class OpencodeConfig(BaseModel):
    """OpenCode CLI configuration."""
    workspace: str = Field(default="~/.toolcli/workspace", description="Working directory")
    agent: str = Field(default="build", description="Default agent mode")
    timeout: int = Field(default=300, description="Command timeout in seconds")


class GitHubConfig(BaseModel):
    """GitHub CLI configuration."""
    default_owner: str = Field(default="", description="Default repository owner")
    default_repo: str = Field(default="", description="Default repository name")


class HeartbeatConfig(BaseModel):
    """Heartbeat configuration."""
    interval: int = Field(default=300, description="Heartbeat interval in seconds")
    max_retries: int = Field(default=3, description="Max retries for failed tasks")
    state_file: str = Field(default="~/.toolcli/state.json", description="State persistence file")
    log_file: str = Field(default="~/.toolcli/heartbeat.log", description="Heartbeat log file")


class ToolcliConfig(BaseModel):
    """Main toolcli configuration."""
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    opencode: OpencodeConfig = Field(default_factory=OpencodeConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ToolcliConfig":
        """Load configuration from file."""
        if path is None:
            path = Path.home() / ".config" / "toolcli" / "config.yaml"
        
        if not path.exists():
            return cls()
        
        with open(path) as f:
            data = yaml.safe_load(f)
        
        return cls(**(data or {}))
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to file."""
        if path is None:
            path = Path.home() / ".config" / "toolcli" / "config.yaml"
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)
