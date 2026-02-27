"""GitHub CLI integration for toolcli with resilience features."""

import asyncio
import subprocess
from typing import Dict, List, Optional, Any
from datetime import datetime

from toolcli.config import GitHubConfig
from toolcli.utils.error_context import ErrorContext
from toolcli.utils.logging import StructuredLogger
from toolcli.utils.metrics import MetricsCollector


class GitHubClient:
    """Client for GitHub CLI operations with resilience features.
    
    Features:
    - Health checking
    - Enhanced error context
    - Metrics collection
    - Git fallback for when gh CLI unavailable
    """
    
    def __init__(
        self,
        config: GitHubConfig,
        metrics: Optional[MetricsCollector] = None,
        logger: Optional[StructuredLogger] = None,
    ):
        """Initialize GitHub client.
        
        Args:
            config: GitHub configuration
            metrics: Optional metrics collector
            logger: Optional structured logger
        """
        self.config = config
        self.metrics = metrics
        self.logger = logger or StructuredLogger("github")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check GitHub CLI health and authentication.
        
        Returns:
            Dictionary with health status
        """
        start_time = datetime.now()
        
        try:
            result = await self._run_gh(["auth", "status"])
            latency_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            if result.get("success"):
                return {
                    "healthy": True,
                    "authenticated": True,
                    "latency_ms": latency_ms,
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                return {
                    "healthy": False,
                    "authenticated": False,
                    "error": result.get("error", "Not authenticated"),
                    "latency_ms": latency_ms,
                    "timestamp": datetime.now().isoformat(),
                }
                
        except FileNotFoundError:
            return {
                "healthy": False,
                "authenticated": False,
                "error": "GitHub CLI (gh) not found in PATH",
                "error_type": "FileNotFoundError",
                "fallback_available": True,  # Can use git CLI
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            return {
                "healthy": False,
                "authenticated": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "fallback_available": True,
                "timestamp": datetime.now().isoformat(),
            }
    
    async def _run_gh(
        self,
        args: List[str],
        cwd: Optional[str] = None,
        json_output: bool = True,
    ) -> Dict[str, Any]:
        """Run gh CLI command with error handling.
        
        Args:
            args: Command arguments
            cwd: Working directory
            json_output: Whether to request JSON output
            
        Returns:
            Result dictionary
        """
        start_time = datetime.now()
        cmd = ["gh"] + args
        
        if json_output and "--json" not in args:
            cmd.append("--json")
            cmd.append("*")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            
            stdout, stderr = await process.communicate()
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            if process.returncode != 0:
                error_msg = stderr.decode()
                
                # Log error
                self.logger.error(
                    message=f"gh command failed: {error_msg}",
                    service="github",
                    operation=args[0] if args else "unknown",
                    context={"args": args},
                )
                
                return {
                    "success": False,
                    "error": error_msg,
                    "stdout": stdout.decode(),
                    "duration_ms": duration_ms,
                }
            
            output = stdout.decode()
            
            # Parse JSON if requested
            if json_output and output:
                import json
                try:
                    parsed = json.loads(output)
                    return {
                        "success": True,
                        "data": parsed,
                        "duration_ms": duration_ms,
                    }
                except json.JSONDecodeError:
                    return {
                        "success": True,
                        "data": output,
                        "duration_ms": duration_ms,
                    }
            
            return {
                "success": True,
                "data": output,
                "duration_ms": duration_ms,
            }
            
        except FileNotFoundError:
            return ErrorContext.enrich(
                error=FileNotFoundError("GitHub CLI (gh) not found"),
                operation=args[0] if args else "unknown",
                service_name="github",
                context={"args": args},
            )
            
        except Exception as e:
            return ErrorContext.enrich(
                error=e,
                operation=args[0] if args else "unknown",
                service_name="github",
                context={"args": args},
            )
    
    async def create_repo(
        self,
        name: str,
        description: str = "",
        private: bool = False,
        owner: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new GitHub repository.
        
        Args:
            name: Repository name
            description: Repository description
            private: Whether to create private repo
            owner: Optional owner (for org repos)
            
        Returns:
            Result dictionary
        """
        start_time = datetime.now()
        operation = "create_repo"
        
        args = ["repo", "create", name]
        
        if description:
            args.extend(["--description", description])
        
        if private:
            args.append("--private")
        else:
            args.append("--public")
        
        if owner:
            args.extend(["--owner", owner])
        
        result = await self._run_gh(args, json_output=False)
        
        # Record metrics
        if self.metrics:
            self.metrics.record(
                service="github",
                operation=operation,
                success=result.get("success", False),
                duration_ms=result.get("duration_ms", 0),
                error_type=result.get("error_type") if not result.get("success") else None,
            )
        
        return result
    
    async def clone(
        self,
        repo: str,
        directory: Optional[str] = None,
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        """Merge a pull request."""
        args = ["pr", "merge", str(pr_number), f"--{method}"]
        
        if repo:
            args.extend(["--repo", repo])
        
        return await self._run_gh(args, json_output=False)
    
    async def get_pr_status(
        self,
        pr_number: int,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get PR status including checks."""
        args = ["pr", "checks", str(pr_number)]
        
        if repo:
            args.extend(["--repo", repo])
        
        return await self._run_gh(args)
    
    async def list_workflow_runs(
        self,
        repo: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        """Create a new branch using git (fallback when gh unavailable)."""
        try:
            # Use git commands directly
            subprocess.run(["git", "checkout", base], cwd=cwd, check=True)
            subprocess.run(["git", "pull"], cwd=cwd, check=True)
            subprocess.run(["git", "checkout", "-b", name], cwd=cwd, check=True)
            
            return {"success": True, "branch": name}
            
        except subprocess.CalledProcessError as e:
            return ErrorContext.enrich(
                error=e,
                operation="create_branch",
                service_name="git",
                context={"branch": name, "base": base},
            )
    
    async def commit_and_push(
        self,
        message: str,
        branch: Optional[str] = None,
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Commit changes and push using git (fallback when gh unavailable)."""
        try:
            subprocess.run(["git", "add", "."], cwd=cwd, check=True)
            subprocess.run(["git", "commit", "-m", message], cwd=cwd, check=True)
            
            if branch:
                subprocess.run(["git", "push", "-u", "origin", branch], cwd=cwd, check=True)
            else:
                subprocess.run(["git", "push"], cwd=cwd, check=True)
            
            return {"success": True}
            
        except subprocess.CalledProcessError as e:
            return ErrorContext.enrich(
                error=e,
                operation="commit_and_push",
                service_name="git",
                context={"message": message, "branch": branch},
            )
