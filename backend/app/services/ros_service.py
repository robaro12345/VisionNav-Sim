"""ROS 2 lifecycle management service for the VisionNav-Sim backend.

Runs ROS 2 nodes in a background thread and synchronizes the ROS ContextStore
with the FastAPI RobotContextCache.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import rclpy
from rclpy.executors import MultiThreadedExecutor

from backend.app.models.types import RobotContext
from backend.app.memory.memory_store import MemoryStore
from backend.app.services.ros_executor import ExecutorNode, ROSExecutor
from backend.app.state.robot_context_cache import RobotContextCache

# Import the existing ContextNode from the ROS workspace
from synapse_bringup.context_node import ContextNode

logger = logging.getLogger(__name__)


class ROSService:
    """Manages the ROS 2 execution loop and context synchronization."""

    def __init__(self, memory_store: MemoryStore, context_cache: RobotContextCache) -> None:
        self.memory_store = memory_store
        self.context_cache = context_cache
        
        self.context_node: ContextNode | None = None
        self.executor_node: ExecutorNode | None = None
        self.action_executor: ROSExecutor | None = None
        
        self._ros_executor: MultiThreadedExecutor | None = None
        self._spin_thread: threading.Thread | None = None
        self._sync_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()

    def start(self) -> None:
        """Initialize rclpy, create nodes, and start background threads."""
        if self._spin_thread and self._spin_thread.is_alive():
            logger.warning("ROSService is already running.")
            return

        logger.info("Initializing ROS 2 service...")
        
        # 1. Initialize ROS 2
        if not rclpy.ok():
            rclpy.init()
        
        # 2. Instantiate nodes
        self.context_node = ContextNode()
        self.executor_node = ExecutorNode()
        
        # 3. Initialize business logic executor
        self.action_executor = ROSExecutor(self.memory_store, self.executor_node, self.context_node)
        
        # 4. Setup MultiThreadedExecutor
        self._ros_executor = MultiThreadedExecutor()
        self._ros_executor.add_node(self.context_node)
        self._ros_executor.add_node(self.executor_node)
        
        # 5. Start spin thread
        self._shutdown_event.clear()
        self._spin_thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._spin_thread.start()
        
        # 6. Start context sync thread
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._sync_thread.start()
        
        logger.info("ROS 2 background threads started successfully.")

    def shutdown(self) -> None:
        """Gracefully terminate ROS 2 nodes and threads."""
        logger.info("Shutting down ROS 2 service...")
        
        # Signal threads to stop
        self._shutdown_event.set()
        
        # Shutdown executors to unblock spin loop
        if self._ros_executor:
            self._ros_executor.shutdown()
            
        # Join threads
        if self._spin_thread and self._spin_thread.is_alive():
            self._spin_thread.join(timeout=2.0)
            
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=2.0)
            
        # Destroy nodes
        if self.context_node:
            self.context_node.destroy_node()
            
        if self.executor_node:
            self.executor_node.destroy_node()
            
        # Global shutdown
        if rclpy.ok():
            rclpy.shutdown()
            
        logger.info("ROS 2 service shut down completely.")

    def get_executor(self) -> ROSExecutor:
        """Return the active action executor for FastAPI routes."""
        if not self.action_executor:
            raise RuntimeError("ROSService is not running. Cannot get executor.")
        return self.action_executor

    def get_context_cache(self) -> RobotContextCache:
        """Return the active context cache."""
        return self.context_cache

    def get_memory_store(self) -> MemoryStore:
        """Return the active memory store."""
        return self.memory_store

    def _spin_loop(self) -> None:
        """Background thread target for rclpy.spin()."""
        try:
            if self._ros_executor:
                self._ros_executor.spin()
        except Exception as e:
            logger.error(f"Error in ROS 2 spin loop: {e}")

    def _sync_loop(self) -> None:
        """Background thread target for syncing ContextStore to RobotContextCache at 10Hz."""
        while not self._shutdown_event.is_set():
            try:
                if self.context_node:
                    ros_context: dict[str, Any] = self.context_node.store.get_context()
                    # Ensure strict validation through the Pydantic model before caching
                    validated_context = RobotContext.model_validate(ros_context)
                    self.context_cache.update_context(validated_context)
            except Exception as e:
                logger.error(f"Error syncing ROS context: {e}")
                
            time.sleep(0.1) # 10Hz sync rate
