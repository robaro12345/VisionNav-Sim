# 🤖 VisionNav Sim

> Natural-language → ROS 2 navigation. Type a goal; TurtleBot3 goes there.

![ROS2 Jazzy](https://img.shields.io/badge/ROS2-Jazzy-blue?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Ubuntu%2024.04%20%7C%20WSL2-teal?style=flat-square)
![Nav2](https://img.shields.io/badge/Nav2-SLAM%20Toolbox-green?style=flat-square)
![LLM](<https://img.shields.io/badge/LLM-Ollama%20(local)-orange?style=flat-square>)
![Frontend](https://img.shields.io/badge/frontend-Vite%20React%20TypeScript-fuchsia?style=flat-square)

VisionNav Sim accepts a natural-language command, fuses the latest ROS 2 sensor snapshot into an agent state, runs it through a local LLM planning pipeline, and delivers a validated navigation goal to a TurtleBot3 Waffle in Gazebo. Everything runs locally — no external APIs.

---

## Algorithmic Pipeline

```text
Natural Language Command
│
▼
Ollama Planner (gemma4:12b — local LLM)
│
▼
Safety Validation Layer
│
▼
ROS Executor (Nav2 action dispatch)
│
▼
Nav2 (Navigation & Obstacle Avoidance)
```

---

## Architecture

```text
    +-------------+      +-------------------+      +----------------+
    | Web UI      | ---> | FastAPI Backend   | ---> | Ollama Planner |
    | (React/Vite)| <--- | (State & Control) | <--- | (LLM Agent)    |
    +-------------+      +-------------------+      +----------------+
                                  |
                                  v
                         +-------------------+
                         | ROSService        |
                         | (Background       |
                         |  rclpy thread)    |
                         +-------------------+
                                  |
               +------------------+------------------+
               |                  |                  |
               v                  v                  v
    +-------------+      +----------------+  +---------------+
    | Nav2 Stack  |      | ContextNode    |  | Gazebo Sim    |
    | (SLAM/AMCL) |      | (Sensor Cache) |  | (TurtleBot3   |
    +-------------+      +----------------+  |  Waffle)      |
                                             +---------------+
```

---

## Features

- **Natural Language Control:** Type goals to the robot; the local Ollama-powered planner interprets and dispatches them.
- **Local AI Planning:** Zero external API calls — entirely powered by `gemma4:12b` via Ollama.
- **Autonomous Exploration:** `explore_environment` triggers a frontier exploration pipeline (`fronter_exploration` ROS package) followed by `semantic_mapper` to build a `semantic_map.json`.
- **Semantic Map Integration:** The backend hot-reloads `semantic_map.json` at 10 Hz and injects known objects into every planner context call — enabling "go to the box"-style commands.
- **Session Memory:** Per-session history tracks recent commands, task lifecycle (start → complete/cancel), and navigation records across the conversation.
- **Live Dashboard:** Glassmorphic Vite/React/TypeScript cockpit with live camera feed, robot state polling, and AI reasoning display.

---

## 🔌 API & ROS Surfaces

### HTTP / API (Port 8000)

| Method | Endpoint                | Description                                                        |
| ------ | ----------------------- | ------------------------------------------------------------------ |
| `GET`  | `/api/state`            | Latest cached robot context (pose, nav status, map progress)       |
| `GET`  | `/api/camera/frame.jpg` | Latest camera frame as JPEG (encoded via OpenCV/cv_bridge)         |
| `GET`  | `/api/reasoning`        | Latest LLM reasoning breakdown for a given `session_id`            |
| `GET`  | `/api/current-task`     | Active task, recent task history, and exploration status           |
| `GET`  | `/api/navigation`       | Full navigation history for a given `session_id`                   |
| `POST` | `/api/command`          | Submit a natural-language command; plan is executed in background  |
| `POST` | `/api/manual`           | Publish a `Twist` directly to `/cmd_vel` (`linear_x`, `angular_z`) |

### ROS 2 Interfaces

| Direction | Interface           | Type             | Description                                             |
| --------- | ------------------- | ---------------- | ------------------------------------------------------- |
| Action    | `/navigate_to_pose` | `NavigateToPose` | Navigation goals → Nav2                                 |
| Publish   | `/cmd_vel`          | `Twist`          | Velocity commands (teleop & emergency stop)             |
| Subscribe | `/camera/image_raw` | `Image`          | Camera frames (bridged from Gazebo via `ros_gz_bridge`) |
| Subscribe | `/map`              | `OccupancyGrid`  | SLAM Toolbox map                                        |
| Subscribe | `/scan`             | `LaserScan`      | LiDAR scan data                                         |
| Subscribe | `/odom`             | `Odometry`       | Robot velocity from DiffDrive plugin                    |
| Subscribe | `/tf`               | `TFMessage`      | Transform tree (pose derived via `map→base_link`)       |

---

## 🛠️ Tech Stack

- **Robot & Sim:** TurtleBot3 Waffle · Gazebo Harmonic · ROS 2 Jazzy (Ubuntu 24.04 / WSL2)
- **Navigation & Exploration:** Nav2 · SLAM Toolbox · `fronter_exploration` · `semantic_mapper`
- **AI:** Ollama (local-only) · `gemma4:12b`
- **Camera:** OpenCV + `cv_bridge` (JPEG encoding from `/camera/image_raw`)
- **Backend:** FastAPI · Python threading · Pydantic v2 · PyYAML
- **Frontend:** React 19 · TypeScript · Vite · Tailwind CSS v4

---

## 📁 Directory Structure

```text
RobotProject/
├── backend/
│   └── app/
│       ├── api/
│       │   ├── main.py               # FastAPI entry point & all REST endpoints
│       │   └── schemas.py            # Pydantic request/response schemas
│       ├── constants/
│       │   └── actions.py            # ALLOWED_ACTIONS whitelist
│       ├── memory/
│       │   ├── conversation_memory.py  # Thread-safe per-session task memory
│       │   ├── memory_store.py         # Session registry (robot_id → session_id)
│       │   └── session_manager.py      # Session lifecycle helpers
│       ├── models/
│       │   └── types.py              # All shared Pydantic domain types
│       ├── services/
│       │   ├── ollama_planner.py     # Prompt builder & local Ollama client
│       │   ├── ros_executor.py       # Nav2 action dispatch, teleop, exploration
│       │   ├── ros_service.py        # rclpy thread + 10Hz context sync loop
│       │   └── safety_layer.py       # Action whitelist & parameter validation
│       └── state/
│           └── robot_context_cache.py  # Shared-memory RobotContext cache
├── ros2/
│   └── src/
│       └── synapse_bringup/
│           ├── launch/
│           │   └── sim_launch.py     # Launches Gazebo, Nav2, RViz
│           ├── worlds/               # Gazebo SDF world files
│           ├── urdf/                 # TurtleBot3 Waffle URDF & SDF
│           ├── rviz/                 # RViz config
│           └── synapse_bringup/
│               ├── context_node.py   # ROS node: subscribes to all sensor topics
│               └── context_store.py  # Thread-safe sensor snapshot store
├── config/
│   └── paths.yaml                    # Map directory path config
├── map/
│   ├── map.pgm                       # Saved occupancy grid image
│   ├── map.yaml                      # Map metadata
│   └── semantic_map.json             # Object list from semantic_mapper
└── frontend/                         # Vite + React + TypeScript cockpit UI
```

---

## ⚠️ Constraints & Scope

- LLM inference is **local-only** — no external API calls are made.
- Nav2 exclusively handles obstacle avoidance and path planning; the LLM handles high-level intent only.
- **`navigate_to_object` is stubbed** — the action is in the planner whitelist but the executor returns `False` (V1 limitation). Semantic objects from `semantic_map.json` are injected into the planner context to enable object-aware reasoning, but autonomous pose lookup is not yet implemented.
- The `ContextNode` records a scene summary from raw LiDAR and camera metadata only — no object detection runs on the robot.
- This repository covers the **simulation track only**; the physical robot track is not started.

---

## 🚀 Getting Started

### 1. Start the Local LLM

Ensure Ollama is running with the configured model:

```bash
ollama run gemma4:12b
```

### 2. Build & Launch ROS 2 Environment

Build the workspace and launch the simulation (Gazebo + Nav2 + RViz):

```bash
# From RobotProject/ros2/
colcon build
source install/setup.bash
ros2 launch synapse_bringup sim_launch.py
```

> **Note:** `fronter_exploration` and `semantic_mapper` packages must also be built in your workspace for the `explore_environment` action to work. The map is auto-detected from `config/paths.yaml` — if a saved map exists, Nav2 starts in localization mode instead of SLAM.

### 3. Start the Backend API

```bash
cd /path/to/RobotProject
pip install -r backend/requirements.txt
source ros2/install/setup.bash
uvicorn backend.app.api.main:app --host 0.0.0.0 --port 8000
```

### 4. Start the Frontend Dashboard

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` and command your robot using natural language.

---

## Demo

Will Make One some time later...

---
