"""toolcli - CLI agent tool with OpenSpec workflow and Ollama local models."""

__version__ = "0.1.0"
__all__ = ["ToolcliAgent", "ToolcliConfig"]

from toolcli.agent.core import ToolcliAgent
from toolcli.config import ToolcliConfig
