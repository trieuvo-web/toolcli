"""OpenCode CLI integration for toolcli."""

import asyncio
import json
import subprocess
from typing import Dict, List, Optional

from toolcli.config import OpencodeConfig


class OpencodeClient:
    """Client for OpenCode CLI."""
    
    def __init__(self, config: OpencodeConfig):
        self.config = config
        self.workspace = Path(config.workspace).expanduser()
        self.workspace.mkdir(parents=True, exist_ok=True)
    
    async def run_openspec_command(
        self,
        command: str,
        cwd: Optional[Path] = None,
    ) -> Dict[str, any]:
        """Run an OpenSpec slash command."""
        cmd = [
            "opencode", "run",
            f"{command}",
            "--agent", self.config.agent,
        ]
        
        if cwd:
            cmd.extend(["--cwd", str(cwd)])
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or self.workspace,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.timeout,
            )
            
            return {
                "success": process.returncode == 0,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "returncode": process.returncode,
            }
        except asyncio.TimeoutError:
            process.kill()
            return {
                "success": False,
                "stdout": "",
                "stderr": "Command timed out",
                "returncode": -1,
            }
    
    async def explore(
        self,
        topic: str,
        cwd: Optional[Path] = None,
    ) -> Dict[str, any]:
        """Run OpenSpec explore phase."""
        return await self.run_openspec_command(
            f"/opsx-explore {topic}",
            cwd=cwd,
        )
    
    async def new_change(
        self,
        name: str,
        cwd: Optional[Path] = None,
    ) -> Dict[str, any]:
        """Create new OpenSpec change."""
        return await self.run_openspec_command(
            f"/opsx-new {name}",
            cwd=cwd,
        )
    
    async def continue_change(
        self,
        cwd: Optional[Path] = None,
    ) -> Dict[str, any]:
        """Continue OpenSpec workflow."""
        return await self.run_openspec_command(
            "/opsx-continue",
            cwd=cwd,
        )
    
    async def apply_change(
        self,
        cwd: Optional[Path] = None,
    ) -> Dict[str, any]:
        """Apply/Implement OpenSpec tasks."""
        return await self.run_openspec_command(
            "/opsx-apply",
            cwd=cwd,
        )
    
    async def verify_change(
        self,
        name: str,
        cwd: Optional[Path] = None,
    ) -> Dict[str, any]:
        """Verify OpenSpec change."""
        return await self.run_openspec_command(
            f"/opsx-verify {name}",
            cwd=cwd,
        )
    
    async def create_file(
        self,
        file_path: str,
        content: str,
        description: str = "",
    ) -> Dict[str, any]:
        """Create a file using OpenCode."""
        cmd = [
            "opencode", "run",
            f"Create file {file_path}: {description}",
            "--agent", "build",
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.timeout,
            )
            
            return {
                "success": process.returncode == 0,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
            }
        except asyncio.TimeoutError:
            process.kill()
            return {"success": False, "error": "Timeout"}
    
    async def analyze_codebase(
        self,
        query: str,
    ) -> Dict[str, any]:
        """Analyze codebase using OpenCode."""
        cmd = [
            "opencode", "run",
            f"Analyze codebase: {query}",
            "--agent", "plan",
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await process.communicate()
        
        return {
            "success": process.returncode == 0,
            "analysis": stdout.decode(),
            "errors": stderr.decode(),
        }


from pathlib import Path
