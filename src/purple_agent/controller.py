"""Agent Controller for managing Purple Agent lifecycle"""

import asyncio
import logging
from typing import Dict, Any, Optional
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class AgentController:
    """
    Controller pattern for managing agent instances.
    Handles state management, proxying, and lifecycle.
    """
    
    def __init__(
        self,
        agent_script: str,
        agent_name: str = "Controlled Agent",
        working_dir: Optional[Path] = None
    ):
        self.agent_script = agent_script
        self.agent_name = agent_name
        self.working_dir = working_dir or Path.cwd()
        
        # Process management
        self.process: Optional[subprocess.Popen] = None
        self.agent_state = "stopped"
        
        # Memory management
        self.memory: Dict[str, Any] = {}
        self.task_history: list = []
    
    async def start(self):
        """Start the agent process"""
        if self.agent_state != "stopped":
            logger.warning(f"Agent {self.agent_name} is already running")
            return
        
        try:
            # Start the agent script as a subprocess
            self.process = subprocess.Popen(
                [sys.executable, self.agent_script],
                cwd=self.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True
            )
            
            self.agent_state = "running"
            logger.info(f"Started agent {self.agent_name}")
            
            # Monitor process in background
            asyncio.create_task(self._monitor_process())
            
        except Exception as e:
            logger.error(f"Failed to start agent: {e}")
            self.agent_state = "error"
    
    async def stop(self):
        """Stop the agent process"""
        if self.process and self.agent_state == "running":
            try:
                self.process.terminate()
                await asyncio.sleep(1)
                
                if self.process.poll() is None:
                    # Force kill if not terminated
                    self.process.kill()
                
                self.agent_state = "stopped"
                logger.info(f"Stopped agent {self.agent_name}")
                
            except Exception as e:
                logger.error(f"Error stopping agent: {e}")
    
    async def reset(self):
        """Reset agent state and memory"""
        logger.info(f"Resetting agent {self.agent_name}")
        
        # Clear memory
        self.memory.clear()
        self.task_history.clear()
        
        # Restart process if running
        if self.agent_state == "running":
            await self.stop()
            await asyncio.sleep(1)
            await self.start()
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task through the controlled agent.
        
        Args:
            task: Task dictionary
            
        Returns:
            Task result
        """
        if self.agent_state != "running":
            await self.start()
            await asyncio.sleep(1)  # Wait for startup
        
        try:
            # Send task to agent process
            task_json = json.dumps(task)
            self.process.stdin.write(task_json + "\n")
            self.process.stdin.flush()
            
            # Wait for response
            response_line = await self._read_response()
            
            if response_line:
                result = json.loads(response_line)
                
                # Store in history
                self.task_history.append({
                    "task": task,
                    "result": result,
                    "timestamp": asyncio.get_event_loop().time()
                })
                
                return result
            
            return {"success": False, "error": "No response from agent"}
            
        except Exception as e:
            logger.error(f"Error executing task: {e}")
            return {"success": False, "error": str(e)}
    
    async def _read_response(self, timeout: float = 300) -> Optional[str]:
        """Read response from agent process"""
        try:
            # Use asyncio to read with timeout
            future = asyncio.create_task(
                asyncio.get_event_loop().run_in_executor(
                    None, self.process.stdout.readline
                )
            )
            
            response = await asyncio.wait_for(future, timeout=timeout)
            return response.strip() if response else None
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for agent response")
            return None
        except Exception as e:
            logger.error(f"Error reading response: {e}")
            return None
    
    async def _monitor_process(self):
        """Monitor agent process health"""
        while self.agent_state == "running":
            if self.process.poll() is not None:
                # Process has terminated
                self.agent_state = "stopped"
                logger.warning(f"Agent {self.agent_name} terminated unexpectedly")
                break
            
            await asyncio.sleep(5)  # Check every 5 seconds
    
    def get_state(self) -> Dict[str, Any]:
        """Get current agent state"""
        return {
            "name": self.agent_name,
            "state": self.agent_state,
            "memory_size": len(self.memory),
            "tasks_completed": len(self.task_history),
            "pid": self.process.pid if self.process else None
        }
    
    async def proxy_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Proxy a request to the controlled agent.
        
        This is used when the agent is deployed as a microservice.
        """
        # In a real implementation, this would forward HTTP requests
        # to the agent's endpoint
        pass


class ControllerManager:
    """
    Manages multiple agent controllers for team coordination.
    """
    
    def __init__(self):
        self.controllers: Dict[str, AgentController] = {}
    
    def register_controller(self, name: str, controller: AgentController):
        """Register a new controller"""
        self.controllers[name] = controller
        logger.info(f"Registered controller: {name}")
    
    async def start_all(self):
        """Start all registered controllers"""
        tasks = [controller.start() for controller in self.controllers.values()]
        await asyncio.gather(*tasks)
    
    async def stop_all(self):
        """Stop all registered controllers"""
        tasks = [controller.stop() for controller in self.controllers.values()]
        await asyncio.gather(*tasks)
    
    async def reset_all(self):
        """Reset all controllers"""
        tasks = [controller.reset() for controller in self.controllers.values()]
        await asyncio.gather(*tasks)
    
    def get_controller(self, name: str) -> Optional[AgentController]:
        """Get a specific controller"""
        return self.controllers.get(name)
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get state of all controllers"""
        return {
            name: controller.get_state()
            for name, controller in self.controllers.items()
        }