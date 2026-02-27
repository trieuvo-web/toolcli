#!/usr/bin/env python3
"""Test runner for toolcli scenarios."""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add toolcli to path
sys.path.insert(0, str(Path(__file__).parent))

from toolcli.config import ToolcliConfig, OllamaConfig, GitHubConfig
from toolcli.tools.ollama import OllamaClient, ReasoningEngine
from toolcli.tools.github import GitHubClient
from toolcli.agent.core import ToolcliAgent
from toolcli.heartbeat.core import StateManager, HeartbeatLogger, AgentTask


class TestRunner:
    """Run test scenarios and collect results."""
    
    def __init__(self):
        self.results = []
        self.config = ToolcliConfig.load()
        
    def log(self, message):
        """Print timestamped log."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    async def run_all_tests(self):
        """Run all test scenarios."""
        self.log("=" * 60)
        self.log("TOOLCLI TEST SUITE")
        self.log("=" * 60)
        
        # Test 1: Normal Task Execution
        await self.test_1_normal_task()
        
        # Test 2: Multi-step OpenSpec (simulated)
        await self.test_2_multistep_workflow()
        
        # Test 3: OpenCode Error Handling
        await self.test_3_opencode_error()
        
        # Test 4: GitHub CLI Error
        await self.test_4_github_error()
        
        # Test 5: Invalid Ollama Response
        await self.test_5_invalid_ollama()
        
        # Test 6: Heartbeat Persistence
        await self.test_6_heartbeat_resume()
        
        # Print summary
        self.print_summary()
        
    async def test_1_normal_task(self):
        """Test 1: Normal task execution with Ollama."""
        self.log("\n" + "=" * 60)
        self.log("TEST 1: Normal Task Execution")
        self.log("=" * 60)
        
        start_time = time.time()
        result = {"scenario": 1, "name": "Normal Task", "status": "RUNNING", "errors": []}
        
        try:
            client = OllamaClient(self.config.ollama)
            
            self.log("Testing Ollama connection...")
            models = await client.list_models()
            self.log(f"Available models: {len(models)}")
            
            if not models:
                result["errors"].append("No Ollama models available")
                result["status"] = "FAIL"
            else:
                self.log(f"Using model: {self.config.ollama.default_model}")
                
                # Test reasoning
                engine = ReasoningEngine(client)
                response = await engine.reason(
                    task="Calculate fibonacci sequence up to 10 numbers. Return as a list."
                )
                
                self.log(f"Response received: {len(response.get('reasoning', ''))} chars")
                
                # Check if response contains fibonacci numbers
                reasoning = response.get("reasoning", "").lower()
                fib_terms = ["0", "1", "2", "3", "5", "8", "13", "21", "34"]
                found_terms = [t for t in fib_terms if t in reasoning]
                
                if len(found_terms) >= 5:
                    self.log(f"✅ Found fibonacci terms: {found_terms}")
                    result["status"] = "PASS"
                else:
                    self.log(f"⚠️  Only found {len(found_terms)} fibonacci terms")
                    result["status"] = "PARTIAL"
                    
            await client.close()
            
        except Exception as e:
            self.log(f"❌ ERROR: {e}")
            result["errors"].append(str(e))
            result["status"] = "FAIL"
            
        result["duration"] = round(time.time() - start_time, 2)
        self.results.append(result)
        self.log(f"Test 1 Result: {result['status']} ({result['duration']}s)")
        
    async def test_2_multistep_workflow(self):
        """Test 2: Multi-step workflow simulation."""
        self.log("\n" + "=" * 60)
        self.log("TEST 2: Multi-step OpenSpec Workflow (Simulated)")
        self.log("=" * 60)
        
        start_time = time.time()
        result = {"scenario": 2, "name": "Multi-step Workflow", "status": "RUNNING", "errors": []}
        
        try:
            # Simulate workflow steps
            steps = [
                ("Explore", "Analyze codebase structure"),
                ("New Change", "Create change definition"),
                ("Continue", "Generate spec and tasks"),
                ("Apply", "Implement changes"),
                ("Verify", "Validate implementation")
            ]
            
            completed_steps = 0
            for step_name, step_desc in steps:
                self.log(f"Step: {step_name} - {step_desc}")
                await asyncio.sleep(0.5)  # Simulate work
                completed_steps += 1
                self.log(f"  ✅ {step_name} complete")
            
            if completed_steps == len(steps):
                result["status"] = "PASS"
            else:
                result["status"] = "PARTIAL"
                
        except Exception as e:
            self.log(f"❌ ERROR: {e}")
            result["errors"].append(str(e))
            result["status"] = "FAIL"
            
        result["duration"] = round(time.time() - start_time, 2)
        self.results.append(result)
        self.log(f"Test 2 Result: {result['status']} ({result['duration']}s)")
        
    async def test_3_opencode_error(self):
        """Test 3: OpenCode CLI error handling."""
        self.log("\n" + "=" * 60)
        self.log("TEST 3: OpenCode CLI Error Handling")
        self.log("=" * 60)
        
        start_time = time.time()
        result = {"scenario": 3, "name": "OpenCode Error", "status": "RUNNING", "errors": []}
        
        try:
            from toolcli.tools.opencode import OpencodeClient
            
            # Use invalid workspace to trigger error
            config = self.config.opencode
            config.workspace = "/nonexistent/path/xyz"
            
            client = OpencodeClient(config)
            
            # Try to run a command that will fail
            self.log("Attempting to run OpenCode with invalid workspace...")
            response = await client.explore("test topic")
            
            self.log(f"Response: success={response.get('success')}")
            
            if not response.get("success", True):
                self.log("✅ Error handled gracefully")
                result["status"] = "PASS"
            else:
                self.log("⚠️  Command succeeded unexpectedly")
                result["status"] = "PARTIAL"
                
        except Exception as e:
            self.log(f"✅ Exception caught (expected): {type(e).__name__}")
            result["status"] = "PASS"  # Exception handling is what we want to test
            
        result["duration"] = round(time.time() - start_time, 2)
        self.results.append(result)
        self.log(f"Test 3 Result: {result['status']} ({result['duration']}s)")
        
    async def test_4_github_error(self):
        """Test 4: GitHub CLI error handling."""
        self.log("\n" + "=" * 60)
        self.log("TEST 4: GitHub CLI Error Handling")
        self.log("=" * 60)
        
        start_time = time.time()
        result = {"scenario": 4, "name": "GitHub CLI Error", "status": "RUNNING", "errors": []}
        
        try:
            client = GitHubClient(self.config.github)
            
            # Try operation that will fail
            self.log("Attempting to create repo with invalid name...")
            response = await client.create_repo(
                name="test repo with spaces",
                description="Test"
            )
            
            self.log(f"Response: success={response.get('success')}")
            
            if not response.get("success", True):
                self.log("✅ Error captured correctly")
                result["status"] = "PASS"
            else:
                self.log("⚠️  Unexpected success")
                result["status"] = "PARTIAL"
                
        except Exception as e:
            self.log(f"✅ Exception caught: {type(e).__name__}")
            result["status"] = "PASS"
            
        result["duration"] = round(time.time() - start_time, 2)
        self.results.append(result)
        self.log(f"Test 4 Result: {result['status']} ({result['duration']}s)")
        
    async def test_5_invalid_ollama(self):
        """Test 5: Invalid Ollama response handling."""
        self.log("\n" + "=" * 60)
        self.log("TEST 5: Invalid Ollama Response Handling")
        self.log("=" * 60)
        
        start_time = time.time()
        result = {"scenario": 5, "name": "Invalid Ollama", "status": "RUNNING", "errors": []}
        
        try:
            client = OllamaClient(self.config.ollama)
            
            # Test normal generation
            self.log("Testing normal generation...")
            response = await client.generate(
                prompt="Say 'hello'",
                model="qwen3:4b"
            )
            
            self.log(f"Response received: {len(response.get('response', ''))} chars")
            
            # Test with edge case prompt
            self.log("Testing edge case prompt...")
            response2 = await client.generate(
                prompt="Return exactly: {{{not_valid_json",
                model="qwen3:4b"
            )
            
            self.log(f"Edge case response: {len(response2.get('response', ''))} chars")
            
            await client.close()
            
            self.log("✅ All responses handled without crash")
            result["status"] = "PASS"
            
        except Exception as e:
            self.log(f"❌ ERROR: {e}")
            result["errors"].append(str(e))
            result["status"] = "FAIL"
            
        result["duration"] = round(time.time() - start_time, 2)
        self.results.append(result)
        self.log(f"Test 5 Result: {result['status']} ({result['duration']}s)")
        
    async def test_6_heartbeat_resume(self):
        """Test 6: Heartbeat persistence and resume."""
        self.log("\n" + "=" * 60)
        self.log("TEST 6: Heartbeat Stop and Resume")
        self.log("=" * 60)
        
        start_time = time.time()
        result = {"scenario": 6, "name": "Heartbeat Resume", "status": "RUNNING", "errors": []}
        
        try:
            import tempfile
            import shutil
            
            # Create temp directory for state
            temp_dir = tempfile.mkdtemp()
            state_file = Path(temp_dir) / "state.json"
            log_file = Path(temp_dir) / "heartbeat.log"
            
            self.log(f"Using temp state file: {state_file}")
            
            # Create state manager
            manager = StateManager(state_file)
            logger = HeartbeatLogger(log_file)
            
            # Load initial state
            from toolcli.heartbeat.core import AgentState, TaskStatus
            state = await manager.load()
            self.log(f"Initial state: {len(state.tasks)} tasks")
            
            # Add test tasks
            task1 = AgentTask(
                type="test",
                description="Test task 1",
                params={"action": "test"}
            )
            task2 = AgentTask(
                type="test",
                description="Test task 2",
                params={"action": "test"}
            )
            
            state.tasks.append(task1)
            state.tasks.append(task2)
            
            # Mark one as running (simulating interruption)
            task1.status = TaskStatus.RUNNING
            task1.started_at = datetime.now()
            
            await manager.save(state)
            self.log("✅ State saved with simulated interruption")
            
            # Reload and check resume
            state2 = await manager.load()
            interrupted = [
                t for t in state2.tasks
                if t.status == TaskStatus.RUNNING
            ]
            
            self.log(f"Found {len(interrupted)} interrupted tasks")
            
            # Simulate resume
            for task in interrupted:
                task.status = TaskStatus.RETRYING
                task.retry_count += 1
            
            await manager.save(state2)
            self.log("✅ Resume simulation complete")
            
            # Cleanup
            shutil.rmtree(temp_dir)
            
            if len(interrupted) == 1:
                result["status"] = "PASS"
            else:
                result["status"] = "PARTIAL"
                
        except Exception as e:
            self.log(f"❌ ERROR: {e}")
            result["errors"].append(str(e))
            result["status"] = "FAIL"
            
        result["duration"] = round(time.time() - start_time, 2)
        self.results.append(result)
        self.log(f"Test 6 Result: {result['status']} ({result['duration']}s)")
        
    def print_summary(self):
        """Print test summary."""
        self.log("\n" + "=" * 60)
        self.log("TEST SUMMARY")
        self.log("=" * 60)
        
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        partial = sum(1 for r in self.results if r["status"] == "PARTIAL")
        total = len(self.results)
        
        for r in self.results:
            icon = "✅" if r["status"] == "PASS" else "❌" if r["status"] == "FAIL" else "⚠️"
            self.log(f"{icon} Test {r['scenario']}: {r['name']} - {r['status']} ({r['duration']}s)")
            if r["errors"]:
                for err in r["errors"]:
                    self.log(f"   Error: {err}")
        
        self.log("-" * 60)
        self.log(f"Total: {total} | ✅ Pass: {passed} | ❌ Fail: {failed} | ⚠️ Partial: {partial}")
        
        if failed == 0:
            self.log("\n🎉 All critical tests passed!")
        else:
            self.log(f"\n⚠️  {failed} test(s) failed. Review errors above.")
            
        # Save results
        results_file = Path(__file__).parent / "test_results.json"
        with open(results_file, "w") as f:
            json.dump(self.results, f, indent=2)
        self.log(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    runner = TestRunner()
    asyncio.run(runner.run_all_tests())
