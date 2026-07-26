VisionNav Sim (Simulation Track)

## Project
Agentic robotics system for natural language → ROS2 navigation.
Simulation only. The physical track is separate and not started yet.

## Current Architecture & Scope (V1)
- **Pipeline:** `OllamaPlanner → SafetyLayer → ROSExecutor` — no LangGraph dependency.
- **Backend:** Single FastAPI process. A background `rclpy` thread (`ROSService`) runs two nodes: `ContextNode` (sensor subscriber) and `ExecutorNode` (Nav2 action client).
- **Context Sync:** `ROSService._sync_loop` runs at 10 Hz, syncing `ContextStore → RobotContextCache`. It also hot-reloads `map/semantic_map.json` whenever the file changes, injecting known objects into every planner call.
- **Frontend:** Vite + React + TypeScript dashboard (Tailwind CSS v4, glassmorphic dark cockpit) with live camera feed, state polling, and AI reasoning panel.
- **`navigate_to_object`** is in `ALLOWED_ACTIONS` and the LLM will plan with it, but the executor stubs it as `False` (V2 work).
- Object detection / vision inference does **not** run on the robot. The `ContextNode` uses OpenCV + `cv_bridge` only to JPEG-encode raw camera frames for the dashboard.
- Obstacle avoidance remains the responsibility of the ROS 2 Nav2 stack.

## Robot
- **Model:** TurtleBot3 Waffle (`turtlebot3_waffle.urdf`, `gz_waffle_rgb.sdf.xacro`)
- **Simulation:** Gazebo Harmonic (launched via `gz sim -r <world>`)
- **World:** `synapse_bringup/worlds/test_world.sdf`

## Tech Stack
- **Robot & Sim:** ROS 2 Jazzy (Ubuntu 24.04 / WSL2), TurtleBot3 Waffle, Gazebo Harmonic, Nav2 + SLAM Toolbox
- **AI Core:** Ollama (local) · `gemma4:12b` via custom `OllamaPlanner` (HTTP to `localhost:11434`)
- **Camera:** OpenCV + `cv_bridge` (JPEG encode from `/camera/image_raw`)
- **Backend:** FastAPI, Python threading, Pydantic v2, PyYAML
- **Frontend:** Vite, React 19, TypeScript, Tailwind CSS v4

## Key ROS 2 Topics & Actions
- **Actions:** `/navigate_to_pose` (Nav2)
- **Topics (Pub):** `/cmd_vel` (Twist) — teleop and emergency stops
- **Topics (Sub):** `/camera/image_raw` (Image), `/map` (OccupancyGrid), `/scan` (LaserScan), `/odom` (Odometry), `/tf` (TFMessage)
- **Pose source:** TF `map → base_link` lookup via `tf2_ros.Buffer` (updated at 10 Hz timer)

## Exploration Pipeline
When `explore_environment` is dispatched:
1. `ros2 run fronter_exploration main_node` — frontier-based exploration
2. `ros2 run nav2_map_server map_saver_cli -f <map_dir>/map` — saves occupancy grid
3. `ros2 run semantic_mapper main_node --ros-args -p map_dir:=<map_dir>` — writes `semantic_map.json`

The launch file auto-detects `map/map.yaml` from `config/paths.yaml`. If it exists, Nav2 starts in AMCL localization mode instead of SLAM.

## Planner Allowed Actions
`explore_environment`, `navigate_to_pose`, `navigate_to_object` *(stubbed)*, `search_for_object` *(stubbed)*, `inspect_object` *(stubbed)*, `follow_person` *(stubbed)*, `count_objects`, `describe_scene`, `return_home`, `stop_navigation`, `cancel_task`, `report_status`

## Directory Structure
- `backend/app/api/main.py` — FastAPI entry point & endpoints
- `backend/app/services/` — `ollama_planner.py`, `ros_executor.py`, `ros_service.py`, `safety_layer.py`
- `backend/app/models/types.py` — All shared Pydantic domain types
- `backend/app/memory/` — `conversation_memory.py`, `memory_store.py`, `session_manager.py`
- `backend/app/state/robot_context_cache.py` — Shared-memory context cache
- `backend/app/constants/actions.py` — `ALLOWED_ACTIONS` whitelist
- `ros2/src/synapse_bringup/launch/sim_launch.py` — Simulation launch file
- `ros2/src/synapse_bringup/synapse_bringup/context_node.py` — Sensor subscriber node
- `ros2/src/synapse_bringup/synapse_bringup/context_store.py` — Thread-safe sensor store
- `config/paths.yaml` — Map directory path
- `map/` — `map.pgm`, `map.yaml`, `semantic_map.json`
- `frontend/` — Vite + React + TypeScript cockpit

## DO NOT suggest
- OpenAI / Anthropic API (local LLM only)
- Any cloud robotics platform
- ROS1 (using ROS 2 Jazzy only)
- Replacing Nav2 with custom navigation code
- Isaac Sim (using Gazebo Harmonic)
- YOLO or any vision model (not used in this project)
