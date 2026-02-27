"""CLI entrypoint for toolcli."""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from toolcli.agent.core import ToolcliAgent
from toolcli.config import ToolcliConfig


app = typer.Typer(
    name="toolcli",
    help="CLI agent tool with OpenSpec workflow and Ollama local models",
    rich_markup_mode="rich",
)
console = Console()


@app.command()
def init(
    config_path: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
):
    """Initialize toolcli configuration."""
    config = ToolcliConfig()
    
    if config_path:
        config.save(config_path)
        console.print(f"✅ Configuration saved to {config_path}")
    else:
        default_path = Path.home() / ".config" / "toolcli" / "config.yaml"
        config.save(default_path)
        console.print(f"✅ Configuration saved to {default_path}")
    
    # Create workspace
    workspace = Path(config.opencode.workspace).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)
    console.print(f"✅ Workspace created at {workspace}")


@app.command()
def run(
    task: str = typer.Argument(..., help="Task description to execute"),
    model: str = typer.Option(
        "qwen3:4b",
        "--model",
        "-m",
        help="Ollama model to use for reasoning",
    ),
    openspec: bool = typer.Option(
        False,
        "--openspec",
        "-o",
        help="Use full OpenSpec workflow",
    ),
    change_name: Optional[str] = typer.Option(
        None,
        "--change",
        help="Name for OpenSpec change (if using --openspec)",
    ),
):
    """Run the agent on a task."""
    
    async def _run():
        config = ToolcliConfig.load()
        config.ollama.default_model = model
        
        agent = ToolcliAgent(config)
        await agent.initialize()
        
        try:
            if openspec:
                name = change_name or f"change-{int(asyncio.get_event_loop().time())}"
                console.print(f"🚀 Running OpenSpec workflow: [bold]{name}[/bold]")
                results = await agent.run_openspec_workflow(name, task)
                
                console.print("\n[green]✅ Workflow completed![/green]")
                for step in results["steps"]:
                    status = "✅" if step["result"].get("success", True) else "❌"
                    console.print(f"  {status} {step['action']}")
            else:
                console.print(f"🧠 Reasoning about: [bold]{task}[/bold]")
                result = await agent.execute_task(
                    task_type="reasoning",
                    description=task,
                    params={"prompt": task},
                )
                
                console.print("\n[green]Reasoning:[/green]")
                console.print(result.get("reasoning", "No reasoning provided"))
                
                if result.get("tool_calls"):
                    console.print("\n[yellow]Tool calls:[/yellow]")
                    for call in result["tool_calls"]:
                        console.print(f"  - {call}")
        
        finally:
            await agent.close()
    
    asyncio.run(_run())


@app.command()
def daemon(
    interval: int = typer.Option(
        300,
        "--interval",
        "-i",
        help="Heartbeat interval in seconds",
    ),
    foreground: bool = typer.Option(
        True,
        "--foreground/--background",
        help="Run in foreground or background",
    ),
):
    """Run the agent in daemon mode with heartbeat."""
    
    async def _daemon():
        config = ToolcliConfig.load()
        config.heartbeat.interval = interval
        
        agent = ToolcliAgent(config)
        
        try:
            await agent.start_daemon()
        except KeyboardInterrupt:
            agent.stop_daemon()
    
    if foreground:
        console.print(f"🚀 Starting daemon (interval: {interval}s)")
        console.print("Press Ctrl+C to stop")
        try:
            asyncio.run(_daemon())
        except KeyboardInterrupt:
            console.print("\n🛑 Daemon stopped")
    else:
        # Background mode would require process management
        console.print("Background mode not yet implemented. Use foreground with &")


@app.command()
def queue(
    task_type: str = typer.Argument(..., help="Task type (openspec, opencode, github, reasoning)"),
    description: str = typer.Argument(..., help="Task description"),
    params: Optional[str] = typer.Option(
        None,
        "--params",
        "-p",
        help="JSON parameters for the task",
    ),
):
    """Queue a task for the daemon to process."""
    import json
    
    async def _queue():
        config = ToolcliConfig.load()
        agent = ToolcliAgent(config)
        
        task_params = json.loads(params) if params else {}
        
        result = await agent.execute_task(
            task_type=task_type,
            description=description,
            params=task_params,
            wait=False,
        )
        
        console.print(f"✅ Task queued: [bold]{result['task_id']}[/bold]")
        console.print(f"   Status: {result['status']}")
        
        await agent.close()
    
    asyncio.run(_queue())


@app.command()
def status():
    """Show agent status and task queue."""
    from toolcli.heartbeat.core import StateManager
    
    async def _status():
        config = ToolcliConfig.load()
        state_file = Path(config.heartbeat.state_file).expanduser()
        
        if not state_file.exists():
            console.print("[yellow]No state file found. Agent has not run yet.[/yellow]")
            return
        
        manager = StateManager(state_file)
        state = await manager.load()
        
        # Status table
        table = Table(title="Agent Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Agent ID", state.agent_id)
        table.add_row("Version", state.version)
        table.add_row("Last Heartbeat", str(state.last_heartbeat) if state.last_heartbeat else "Never")
        table.add_row("Total Tasks", str(len(state.tasks)))
        table.add_row("Pending", str(len(state.get_pending_tasks())))
        table.add_row("Completed", str(state.total_tasks_completed))
        table.add_row("Failed", str(state.total_tasks_failed))
        
        console.print(table)
        
        # Pending tasks
        pending = state.get_pending_tasks()
        if pending:
            console.print("\n[yellow]Pending Tasks:[/yellow]")
            for task in pending:
                console.print(f"  • {task.id}: {task.description}")
    
    asyncio.run(_status())


@app.command()
def models(
    host: Optional[str] = typer.Option(
        None,
        "--host",
        "-h",
        help="Ollama host URL",
    ),
):
    """List available Ollama models."""
    
    async def _models():
        from toolcli.tools.ollama import OllamaClient
        
        config = ToolcliConfig.load()
        if host:
            config.ollama.host = host
        
        client = OllamaClient(config.ollama)
        
        try:
            models = await client.list_models()
            
            table = Table(title="Available Ollama Models")
            table.add_column("Name", style="cyan")
            table.add_column("Size", style="green")
            table.add_column("Modified", style="yellow")
            
            for model in models:
                name = model.get("name", "unknown")
                size = f"{model.get('size', 0) / 1e9:.1f} GB"
                modified = model.get("modified_at", "unknown")[:10]
                table.add_row(name, size, modified)
            
            console.print(table)
        
        finally:
            await client.close()
    
    asyncio.run(_models())


if __name__ == "__main__":
    app()
