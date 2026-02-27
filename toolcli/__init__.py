"""toolcli - CLI agent tool with OpenSpec workflow and Ollama local models."""

__version__ = "0.1.0"
__all__ = ["Agent", "ToolcliConfig"]

from toolcli.agent.core import Agent
from toolcli.config import ToolcliConfig
