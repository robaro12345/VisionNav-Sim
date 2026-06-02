# 🤖 VisionNav Sim

> Natural-language → ROS 2 navigation. Speak a goal; TurtleBot3 goes there.

![ROS2 Jazzy](https://img.shields.io/badge/ROS2-Jazzy-blue?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Ubuntu%2024.04%20%7C%20WSL2-teal?style=flat-square)
![Nav2](https://img.shields.io/badge/Nav2-SLAM%20Toolbox-green?style=flat-square)
![LLM](https://img.shields.io/badge/LLM-Ollama%20(local)-orange?style=flat-square)
![Frontend](https://img.shields.io/badge/frontend-Vite%20React%20Tailwind-fuchsia?style=flat-square)

VisionNav Sim accepts a natural-language command, fuses the latest ROS 2 sensor snapshot into an agent state, runs an AI pipeline (**Planner → Safety → Executor**), and delivers either a Nav2 goal pose or a velocity pulse to a TurtleBot3 Burger in Gazebo. Everything — LLM inference included — runs locally.

---

## Agent pipeline

The pipeline has been streamlined into a single-process FastAPI application with shared memory access to a background ROS 2 event loop.

```text
Natural Language → OllamaPlanner → SafetyLayer → ROSExecutor → Nav2
```

---

## Architecture

| Component | Location | Role |
|---|---|---|
| Dashboard | `frontend/src/App.tsx` | Vite/React premium glassmorphic cockpit. |
| FastAPI App | `backend/app/api/main.py` | REST API exposing command routes, polling state, and camera feeds. |
| ROS Service | `backend/app/services/ros_service.py` | Daemon thread running the `rclpy` MultiThreadedExecutor. |
| AI Planner | `backend/app/services/ollama_planner.py` | Zero-dependency HTTP wrapper translating user intents to JSON plans. |
| Safety & Exec | `backend/app/services/` | Validates plans against whitelists and dispatches Nav2 actions. |
| ROS2 Bringup | `ros2/src/synapse_bringup/` | Gazebo, TurtleBot3, Nav2, RViz, world assets, and ContextNode. |

---

## API & ROS surfaces

### HTTP / API (Port 8000)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/state` | Latest sensor snapshot & metrics |
| `GET` | `/api/camera/frame.jpg` | Latest camera frame as JPEG |
| `GET` | `/api/reasoning` | Details of the last LLM plan generated |
| `GET` | `/api/current-task` | Task history and execution status |
| `GET` | `/api/navigation` | Navigation and trajectory history |
| `POST` | `/api/command` | Submit a natural-language command |
| `POST` | `/api/manual` | Send manual teleop velocity values (WASD) |

### ROS 2 Interfaces

| Direction | Interface | Type | Description |
|---|---|---|---|
| Action | `/navigate_to_pose` | `NavigateToPose` | Navigation goals → Nav2 |
| Publish | `/cmd_vel` | `Twist` | Velocity commands → TurtleBot3 (Teleop/E-Stop) |
| Subscribe | `/camera/image_raw` | `Image` | Camera frame (for YOLO & Dashboard) |
| Subscribe | `/scan` | `LaserScan` | LiDAR scan |
| Subscribe | `/map` | `OccupancyGrid` | SLAM Toolbox map |

---

## Tech stack

| Layer | Technology |
|---|---|
| Robot & sim | TurtleBot3 Burger · Gazebo · ROS 2 Jazzy |
| Navigation | Nav2 · SLAM Toolbox |
| LLM inference | Ollama (local-only) |
| Vision | YOLOv11n (`yolo11n.pt`) |
| Backend | FastAPI · Python Threading |
| Frontend | React · Vite · Tailwind CSS v4 |

---

## Constraints & Scope (V1)

- LLM inference is **local-only** — no external API calls.
- Nav2 manages all obstacle avoidance.
- **No 3D object localization yet.** Object detection queries will log a warning and safely fail or fallback.
- This repository covers the **simulation track only**; the physical robot track is not started.