# 🤖 VisionNav Sim

> Natural-language → ROS 2 navigation. Speak a goal; TurtleBot3 goes there.

![ROS2 Jazzy](https://img.shields.io/badge/ROS2-Jazzy-blue?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Ubuntu%2024.04%20%7C%20WSL2-teal?style=flat-square)
![Nav2](https://img.shields.io/badge/Nav2-SLAM%20Toolbox-green?style=flat-square)
![LLM](<https://img.shields.io/badge/LLM-Ollama%20(local)-orange?style=flat-square>)
![Frontend](https://img.shields.io/badge/frontend-Vite%20React%20Tailwind-fuchsia?style=flat-square)

VisionNav Sim accepts a natural-language command, fuses the latest ROS 2 sensor snapshot into an agent state, runs an AI pipeline, and delivers a safe navigation goal to a TurtleBot3 in Gazebo. Everything runs locally.

---

## Algorithmic Pipeline

```text
Natural Language Command
│
▼
Ollama Planner (LLM)
│
▼
Safety Validation Layer
│
▼
ROS Executor & Semantic Mapping Orchestrator
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
                         | ROS 2 Orchestrator|
                         | (Context Sync)    |
                         +-------------------+
                                  |
               +------------------+------------------+
               |                  |                  |
               v                  v                  v
    +-------------+      +----------------+  +---------------+
    | Nav2 Stack  |      | Fronter /      |  | Gazebo Sim    |
    | (SLAM/AMCL) |      | Semantic Map   |  | (TurtleBot3)  |
    +-------------+      +----------------+  +---------------+
```

---

## Features

- **Natural Language Control:** Speak or type goals directly to the robot.
- **Local AI Planning:** Zero external API dependencies; entirely powered by local Ollama models.
- **Autonomous Exploration:** Automatically map unknown areas using frontier exploration.
- **Semantic Mapping:** Build a spatial-semantic database of objects using YOLO.
- **Semantic Navigation:** "Go to the couch" dynamically finds the closest obstacle-free viewing cell near the object.
- **Modern Glassmorphic UI:** Control the robot from a sleek Vite/React dashboard.

---

## 🔌 API & ROS Surfaces

### HTTP / API (Port 8000)

| Method | Endpoint                | Description                               |
| ------ | ----------------------- | ----------------------------------------- |
| `GET`  | `/api/state`            | Latest sensor snapshot & metrics          |
| `GET`  | `/api/camera/frame.jpg` | Latest camera frame as JPEG               |
| `POST` | `/api/command`          | Submit a natural-language command         |
| `POST` | `/api/manual`           | Send manual teleop velocity values (WASD) |

### ROS 2 Interfaces

| Direction | Interface           | Type             | Description                    |
| --------- | ------------------- | ---------------- | ------------------------------ |
| Action    | `/navigate_to_pose` | `NavigateToPose` | Navigation goals → Nav2        |
| Publish   | `/cmd_vel`          | `Twist`          | Velocity commands → TurtleBot3 |
| Subscribe | `/camera/image_raw` | `Image`          | Camera frame                   |
| Subscribe | `/map`              | `OccupancyGrid`  | SLAM Toolbox / Map Server      |

---

## 🛠️ Tech Stack

- **Robot & Sim:** TurtleBot3 Burger · Gazebo · ROS 2 Jazzy
- **Navigation & Exploration:** Nav2 · SLAM Toolbox · Fronter_exploration · Semantic_Mapping
- **AI & Vision:** Ollama (local-only) · YOLOv11n
- **Backend:** FastAPI · Python Threading
- **Frontend:** React · Vite · Tailwind CSS v4

---

## ⚠️ Constraints & Scope (V1)

- LLM inference is **local-only** — no external API calls are made.
- Nav2 exclusively manages obstacle avoidance; the LLM handles high-level intent.
- **Semantic Navigation:** The robot relies on a generated `semantic_map.json` and occupancy grid raycasting to find safe stand-off poses for detected objects.
- This repository covers the **simulation track only**; the physical robot track is not started.

---

## 🚀 Getting Started

### 1. Start the Local LLM

Ensure Ollama is running in the background with the default model:

```bash
ollama run gemma4:12b
```

### 2. Build & Launch ROS 2 Environment

Build the packages in your colcon workspaces and launch the simulation:

```bash
# In your ROS 2 workspace (make sure Fronter and Semantic_Mapping are built too)
colcon build
source install/setup.bash
ros2 launch synapse_bringup sim_launch.py
```

### 3. Start the Backend API

Run the FastAPI application (this orchestrates the ROS Executor and the LLM Planner):

```bash
cd backend
pip install -r requirements.txt
cd ..
source ros2/install/setup.bash
uvicorn backend.app.api.main:app --host 0.0.0.0 --port 8000
```

### 4. Start the Frontend Dashboard

Run the Vite React app to access the control panel:

```bash
cd frontend
npm install
npm run dev
```

You can now navigate to the local frontend URL (usually `http://localhost:5173`) and command your robot using natural language!
