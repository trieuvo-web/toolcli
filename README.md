# toolcli

CLI agent tool with OpenSpec workflow and Ollama local models.

## Features

- 🤖 **Ollama-powered reasoning** - Uses local LLMs for intelligent decision making
- 🔧 **OpenSpec workflow** - Structured agent execution with spec-driven development
- 🎯 **opencode CLI integration** - Control OpenCode programmatically
- 🌐 **GitHub automation** - Manage repositories via gh CLI
- 💓 **Heartbeat mechanism** - Persistent agent state with resume capability
- 🔁 **Multi-agent ready** - Extensible architecture for future expansion

## Quick Start

```bash
# Install dependencies
pip install -e .

# Initialize toolcli
openspec init

# Run the agent (single mode)
toolcli run --task "Create a Python script that calculates fibonacci"

# Run as daemon (heartbeat mode)
toolcli daemon --interval 300
```

## Architecture

```
toolcli/
├── openspec/
│   ├── specs/           # Agent capability specs
│   ├── flows/           # OpenSpec workflow definitions
│   ├── changes/         # Active change tracking
│   └── config.yaml      # OpenSpec configuration
├── toolcli/
│   ├── agent/           # Core agent implementation
│   ├── cli/             # CLI entrypoint
│   ├── heartbeat/       # Heartbeat & persistence
│   └── tools/           # Tool integrations (opencode, gh, ollama)
└── tests/
```

## Configuration

Create `~/.config/toolcli/config.yaml`:

```yaml
ollama:
  host: http://localhost:11434
  default_model: qwen3:4b
  
opencode:
  workspace: ~/.toolcli/workspace
  
github:
  default_owner: trieuvo-web
```

## License

MIT
