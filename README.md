# 🤖 VisionNav Sim

> Natural-language → ROS2 navigation. Speak a goal; TurtleBot3 goes there.

![ROS2 Jazzy](https://img.shields.io/badge/ROS2-Jazzy-blue?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Ubuntu%2024.04%20%7C%20WSL2-teal?style=flat-square)
![Nav2](https://img.shields.io/badge/Nav2-SLAM%20Toolbox-green?style=flat-square)
![LLM](https://img.shields.io/badge/LLM-Ollama%20gemma4%3Ae4b%20%28local%29-orange?style=flat-square)
![Simulation](https://img.shields.io/badge/track-simulation%20only-lightgrey?style=flat-square)

VisionNav Sim accepts a natural-language command, fuses the latest ROS2 sensor snapshot into an agent state, runs a LangGraph **planner → vision → reasoning → safety → navigation → explainer** pipeline, and delivers either a Nav2 goal pose or a velocity pulse to a TurtleBot3 Burger in Gazebo. Everything — LLM inference included — runs locally.

---

## Agent pipeline

Defined in `backend/services/ai_core/graph.py`. Each stage is a pure function in `backend/agents/`.

```
Planner → Vision → Reasoning → Safety → Navigation → Explainer
```

---

## Architecture

| Component | Location | Role |
|---|---|---|
| FastAPI layer | `backend/services/api/main.py` | HTTP + WebSocket control surface |
| ROS bridge | `backend/services/ros_bridge.py` | Publishes `/goal_pose` & `/cmd_vel`; subscribes camera, LiDAR, map |
| AI core | `backend/services/ai_core/graph.py` | LangGraph orchestration + Ollama (gemma4:e4b) |
| ROS2 bringup | `ros2/src/synapse_bringup/` | Gazebo, TurtleBot3, Nav2, RViz, world assets |

---

## Repository layout

```
VisionNav-Sim/
├── backend/
│   ├── agents/               # one pure-function agent per file
│   └── services/
│       ├── ai_core/          # graph.py — LangGraph pipeline
│       ├── api/              # FastAPI app + static dashboard assets
│       └── ros_bridge.py     # main ROS2 integration layer
├── ros2/src/synapse_bringup/ # launch files, URDF, RViz config, worlds
└── demo/                     # demo video
```

---

## API & ROS surfaces

### HTTP / WebSocket

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | FastAPI + ROS bridge health summary |
| `GET` | `/state` | Latest sensor snapshot + last command result |
| `GET` | `/camera/frame.jpg` | Latest camera frame as JPEG |
| `POST` | `/command` | Run LangGraph pipeline for a natural-language command |
| `POST` | `/drive` | Send a manual velocity pulse |
| `POST` | `/stop` | Stop the robot immediately |
| `WS` | `/ws` | WebSocket control channel |

### ROS2 topics

| Direction | Topic | Type | Description |
|---|---|---|---|
| Publish | `/goal_pose` | `PoseStamped` | Navigation goals → Nav2 |
| Publish | `/cmd_vel` | `Twist` | Velocity commands → TurtleBot3 |
| Subscribe | `/camera/image_raw` | `Image` | Camera frame |
| Subscribe | `/scan` | `LaserScan` | LiDAR scan |
| Subscribe | `/map` | `OccupancyGrid` | SLAM Toolbox map |

---

## Tech stack

| Layer | Technology |
|---|---|
| Robot & sim | TurtleBot3 Burger · Gazebo · ROS2 Jazzy |
| Navigation | Nav2 · SLAM Toolbox |
| LLM inference | Ollama · `gemma4:e4b` (local-only) |
| Agent orchestration | LangGraph · LangChain Ollama |
| Vision | YOLOv11n (`yolo11n.pt`) |
| Backend | FastAPI · WebSockets |
| Dashboard (future scope) | Next.js · Tailwind CSS |

---

## Getting started

### Prerequisites

- ROS2 Jazzy on Ubuntu 24.04 or WSL2
- TurtleBot3 and Nav2 simulation packages installed
- Ollama running locally with `gemma4:e4b` pulled

### 1. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Launch the ROS2 simulation

```bash
cd ros2
ros2 launch synapse_bringup sim_launch.py
```

### 3. Start the backend

```bash
cd backend
python -m services.api.main
```

Send navigation commands via `POST /command` or the WebSocket channel.

---

## Constraints & scope

- LLM inference is **local-only** — no external API calls.
- Nav2 is the navigation stack and is not intended to be replaced.
- This repository covers the **simulation track only**; the physical robot track is not started.

---

## Demo

[Watch demo video]()