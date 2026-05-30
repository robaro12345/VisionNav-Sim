VisionNav Sim (Simulation Track)

## Project
Agentic robotics system for natural language → ROS2 navigation.
Simulation only. The physical track is separate and not started yet.

## Current scope
- Build the simulation-track navigation stack around ROS2 Jazzy, Nav2, and SLAM Toolbox.
- Keep the backend aligned with the LangGraph agent flow in `backend/services/ai_core/graph.py`.
- Use the demo video in `demo/` as the current presentation artifact for the project.

## Stack
- ROS2 Jazzy (Ubuntu 24.04 Noble WSL2)
- TurtleBot3 Burger (Gazebo simulation)
- Nav2 + SLAM Toolbox
- LangGraph (agent orchestration)
- Ollama — gemma4:e4b (local, GPU)
- LangChain Ollama — tool calling
- YOLOv11n — MS-COCO pretrained (yolo11n.pt)
- FastAPI + WebSockets
- Next.js + Tailwind (dashboard)

## Key ROS2 topics
- /goal_pose — publish PoseStamped to send Nav2 goals
- /camera/image_raw — subscribe for vision frames
- /map — SLAM Toolbox output
- /scan — LiDAR data

## Agent state shape
See services/ai-core/graph.py — AgentState TypedDict

## LangGraph graph
planner → vision → reasoning → safety →(conditional)→ navigation → explainer

## DO NOT suggest
- OpenAI / Anthropic API (local LLM only)
- Any cloud robotics platform
- ROS1 (using ROS2 Jazzy only)
- Replacing Nav2 with custom navigation code
- Isaac Sim (using Gazebo Harmonic)

## File ownership
- graph.py — LangGraph state and graph definition
- ros_bridge.py — rclpy NavBridge, do not modify without updating AGENTS.md
- agents/ — one file per agent, each agent is a pure function
