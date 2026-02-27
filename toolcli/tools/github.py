"""GitHub CLI integration for toolcli."""

import asyncio
import json
from typing import Dict, List, Optional

from toolcli.config import GitHubConfig


class GitHubClient:
    """Client for GitHub CLI operations."""
    
    def __init__(self, config: GitHubConfig):
        self.config = config
    
    async def _run_gh(
        self,
        args: List[str],
        cwd: Optional[str] = None,
        json_output: bool = True,
    ) -> Dict[str, any]:
        """Run gh CLI command."""
        cmd = ["gh"] + args
        
        if json_output and "--json" not in args:
            cmd.append("--json")
            cmd.append("*")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return {
                "success": False,
                "error": stderr.decode(),
                "stdout": stdout.decode(),
            }
        
        output = stdout.decode()
        
        try:
            if json_output and output:
                parsed = json.loads(output)
                return {"success": True, "data": parsed}
            return {"success": True, "data": output}
        except json.JSONDecodeError:
            return {"success": True, "data": output}
    
    async def create_repo(
        self,
        name: str,
        description: str = "",
        private: bool = False,
        owner: Optional[str] = None,
    ) -> Dict[str, any]:
        """Create a new GitHub repository."""
        args = ["repo", "create", name]
        
        if description:
            args.extend(["--description", description])
        
        if private:
            args.append("--private")
        else:
            args.append("--public")
        
        if owner:
            args.extend(["--owner", owner])
        
        return await self._run_gh(args, json_output=False)
    
    async def clone(
        self,
        repo: str,
        directory: Optional[str] = None,
    ) -> Dict[str, any]:
        """Clone a repository."""
        args = ["repo", "clone", repo]
        
        if directory:
            args.append(directory)
        
        return await self._run_gh(args, json_output=False)
    
    async def list_issues(
        self,
        repo: Optional[str] = None,
        state: str = "open",
        limit: int = 30,
    ) -> Dict[str, any]:
        """List issues in a repository."""
        args = ["issue", "list", "--state", state, "--limit", str(limit)]
        
        if repo:
            args.extend(["--repo", repo])
        
        return await self._run_gh(args)
    
    async def create_issue(
        self,
        title: str,
        body: str = "",
        repo: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> Dict[str, any]:
        """Create a new issue."""
        args = ["issue", "create", "--title", title]
        
        if body:
            args.extend(["--body", body])
        
        if repo:
            args.extend(["--repo", repo])
        
        if labels:
            for label in labels:
                args.extend(["--label", label])
        
        return await self._run_gh(args, json_output=False)
    
    async def create_pr(
        self,
        title: str,
        body: str = "",
        base: str = "main",
        head: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, any]:
        """Create a pull request."""
        args = ["pr", "create", "--title", title, "--base", base]
        
        if body:
            args.extend(["--body", body])
        
        if head:
            args.extend(["--head", head])
        
        if repo:
            args.extend(["--repo", repo])
        
        return await self._run_gh(args, json_output=False)
    
    async def merge_pr(
        self,
        pr_number: int,
        repo: Optional[str] = None,
        method: str = "merge",
    ) -> Dict[str, any]:
        """Merge a pull request."""
        args = ["pr", "merge", str(pr_number), f"--{method}"]
        
        if repo:
            args.extend(["--repo", repo])
        
        return await self._run_gh(args, json_output=False)
    
    async def get_pr_status(
        self,
        pr_number: int,
        repo: Optional[str] = None,
    ) -> Dict[str, any]:
        """Get PR status including checks."""
        args = ["pr", "checks", str(pr_number)]
        
        if repo:
            args.extend(["--repo", repo])
        
        return await self._run_gh(args)
    
    async def list_workflow_runs(
        self,
        repo: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, any]:
        """List recent workflow runs."""
        args = ["run", "list", "--limit", str(limit)]
        
        if repo:
            args.extend(["--repo", repo])
        
        return await self._run_gh(args)
    
    async def create_branch(
        self,
        name: str,
        base: str = "main",
        cwd: Optional[str] = None,
    ) -> Dict[str, any]:
        """Create a new branch."""
        # Switch to base and create new branch
        args = ["repo", "fork", "--clone=false"]  # Placeholder
        
        # Actually use git commands via subprocess
        import subprocess
        
        try:
            subprocess.run(["git", "checkout", base], cwd=cwd, check=True)
            subprocess.run(["git", "pull"], cwd=cwd, check=True)
            subprocess.run(["git", "checkout", "-b", name], cwd=cwd, check=True)
            
            return {"success": True, "branch": name}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": str(e)}
    
    async def commit_and_push(
        self,
        message: str,
        branch: Optional[str] = None,
        cwd: Optional[str] = None,
    ) -> Dict[str, any]:
        """Commit changes and push."""
        import subprocess
        
        try:
            subprocess.run(["git", "add", "."], cwd=cwd, check=True)
            subprocess.run(["git", "commit", "-m", message], cwd=cwd, check=True)
            
            if branch:
                subprocess.run(["git", "push", "-u", "origin", branch], cwd=cwd, check=True)
            else:
                subprocess.run(["git", "push"], cwd=cwd, check=True)
            
            return {"success": True}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": str(e)}
