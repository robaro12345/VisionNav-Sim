VisionNav Sim (Simulation Track)

## Project
Agentic robotics system for natural language → ROS2 navigation.
Simulation only. The physical track is separate and not started yet.

## Current Architecture & Scope (V1)
- Built a streamlined `Planner -> Safety -> Executor` pipeline replacing the legacy LangGraph approach.
- The backend runs as a single FastAPI process hosting a background `rclpy` thread (`ROSService`) to avoid IPC overhead.
- Frontend dashboard built with Vite, React, and Tailwind CSS (v4) with live polling for state and AI reasoning.
- Object localization is currently deferred to V2 (actions like `navigate_to_object` are safely stubbed).
- Obstacle avoidance remains the responsibility of the ROS 2 Nav2 stack.

## Tech Stack
- **Robot & Sim:** ROS 2 Jazzy (Ubuntu 24.04 Noble WSL2), TurtleBot3 Burger, Gazebo, Nav2 + SLAM Toolbox
- **AI Core:** Ollama (local) via custom `OllamaPlanner` (no LangGraph dependency)
- **Vision:** YOLOv11n (MS-COCO pretrained) inside `ContextNode` (returning `label`, `confidence`, `bbox` only in V1)
- **Backend:** FastAPI, Python threading for ROS 2 lifecycle
- **Frontend:** Vite, React, Tailwind CSS (Glassmorphic dark cockpit)

## Key ROS 2 Topics & Actions
- **Actions:** `/navigate_to_pose` (Nav2)
- **Topics (Pub):** `/cmd_vel` (Twist) for teleop and emergency stops
- **Topics (Sub):** `/camera/image_raw` (Image), `/map` (OccupancyGrid), `/scan` (LaserScan), `/odom` (Odometry), `/tf`

## Directory Structure
- `backend/app/api/main.py` — FastAPI entry point & endpoints
- `backend/app/services/` — Core business logic (`ros_service.py`, `ros_executor.py`, `ollama_planner.py`, `safety_layer.py`)
- `backend/app/models/` — Shared Pydantic types
- `backend/app/memory/` — Thread-safe session tracking
- `backend/app/state/` — Fast shared-memory robot context cache
- `ros2/src/synapse_bringup/` — ROS 2 launch, worlds, URDF, and `context_node.py`
- `frontend/` — Vite + React Cockpit

## DO NOT suggest
- OpenAI / Anthropic API (local LLM only)
- Any cloud robotics platform
- ROS1 (using ROS 2 Jazzy only)
- Replacing Nav2 with custom navigation code
- Isaac Sim (using Gazebo Harmonic)
