"""Ollama planner service for VisionNav-Sim.

Constructs structured prompts with system context, queries the local Ollama instance,
and parses the JSON response into a strongly typed PlannerResponse.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import socket
from typing import Any

from backend.app.constants.actions import ALLOWED_ACTIONS
from backend.app.models.types import (
    PlannerResponse,
    RobotContext,
    ConversationMemory,
)


class OllamaPlanner:
    """Orchestrate prompt generation and local LLM planning via Ollama."""

    def __init__(self) -> None:
        self.endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
        self.model_name = os.getenv("OLLAMA_MODEL", "gemma4:12b")

    def build_context(
        self,
        command: str,
        context: RobotContext,
        memory: ConversationMemory
    ) -> dict[str, Any]:
        """Format the current robot state, memory, and perceptions into a context block."""
        # TODO: Add multimodal image support (encode active frame to base64 if Gemma supports vision)
        return {
            "user_command": command,
            "robot_state": {
                "position": {
                    "x": context.robot_pose.position.x,
                    "y": context.robot_pose.position.y,
                    "z": context.robot_pose.position.z,
                    "frame_id": context.robot_pose.position.frame_id
                },
                "orientation": {
                    "roll": context.robot_pose.orientation.roll,
                    "pitch": context.robot_pose.orientation.pitch,
                    "yaw": context.robot_pose.orientation.yaw
                }
            },
            "navigation_status": context.navigation_status.status_text,
            "current_task": context.current_task,
            "scene_description": context.scene_summary,
            "recent_commands": memory.recent_commands,
            "semantic_objects": [obj.model_dump() for obj in context.semantic_objects]
        }

    def build_prompt(self, command: str, context_block: dict[str, Any]) -> str:
        """Construct the prompt and system instructions for the local Gemma model."""
        action_metadata = {
            "explore_environment": "Autonomously explore unknown areas of the map while cataloging new objects. Parameters: {}",
            "navigate_to_pose": "Go to a coordinate relative to the robot. +x is forward, +y is left. Parameters: {'x': float, 'y': float, 'yaw': float, 'frame_id': 'base_link'}",
            "navigate_to_object": "Navigate to a known object from the semantic map. Parameters: {'object_name': 'String name of the object'}",
            "describe_scene": "Capture image and summarize surroundings. Parameters: {}",
            "return_home": "Return to the configured home position. Parameters: {}",
            "stop_navigation": "Immediately stop navigation. Parameters: {}",
            "cancel_task": "Cancel the current plan. Parameters: {}",
            "report_status": "Tell the user the current status. Parameters: {}"
        }
        
        # Build action whitelist section from shared constants and metadata mapping
        allowed_actions_lines = []
        for action in ALLOWED_ACTIONS:
            if action in action_metadata:
                allowed_actions_lines.append(f"- {action}: {action_metadata[action]}")
        allowed_actions_block = "\n".join(allowed_actions_lines)

        system_instructions = (
            "You are a high-level robot executive with vision capabilities. Translate the user's natural language command "
            "into a structured action plan. Analyze the current pose, active navigation status, "
            "recent commands, and the provided camera image to generate reasoning and a sequence of steps.\n\n"
            "You have access to a static semantic map of known objects in the context. If the user asks to go to an object, you MUST use the `navigate_to_object` action and pass the `object_name` parameter.\n"
            "IMPORTANT: Compare your current `robot_state.position` to the coordinates of objects in `semantic_objects` to understand your relative position. This helps you distinguish whether an object is currently visible in your camera frame or if it is located elsewhere in the map.\n\n"
            "CONSTRAINTS:\n"
            "- You must ONLY output a valid JSON object matching the JSON schema below.\n"
            "- Do NOT include any markdown code blocks, backticks, or extra explanation outside the JSON.\n"
            "- You must NOT generate low-level velocity commands or direct ROS commands.\n"
            "- You must NOT perform path planning or invent coordinates/sensor data.\n"
            "- If the user's intent is ambiguous or targets cannot be resolved, set 'clarification_required' to true "
            "and specify a 'clarification_question'.\n\n"
            "ALLOWED ACTIONS:\n"
            f"{allowed_actions_block}\n\n"
            "REQUIRED JSON SCHEMA:\n"
            "{\n"
            "  \"reasoning\": {\n"
            "    \"user_intent\": \"String detailing user intent\",\n"
            "    \"scene_analysis\": \"String describing the environment from the image\",\n"
            "    \"decision_process\": \"String explaining why this plan was selected\",\n"
            "    \"safety_considerations\": \"String explaining obstacles or hazards\",\n"
            "    \"confidence\": 0.0 to 1.0\n"
            "  },\n"
            "  \"goal\": \"String overall goal\",\n"
            "  \"task_status\": \"pending\" or \"running\" or \"succeeded\" or \"failed\",\n"
            "  \"plan\": [\n"
            "    {\n"
            "      \"step\": int,\n"
            "      \"action\": \"String\",\n"
            "      \"parameters\": {},\n"
            "      \"expected_result\": \"String\"\n"
            "    }\n"
            "  ],\n"
            "  \"target\": {\n"
            "    \"label\": \"Object label if applicable\",\n"
            "    \"confidence\": 0.0 to 1.0\n"
            "  },\n"
            "  \"explanation_for_user\": \"Friendly textual response for the operator dashboard\",\n"
            "  \"clarification_required\": false,\n"
            "  \"clarification_question\": \"String question if clarification_required is true\"\n"
            "}"
        )

        return (
            f"{system_instructions}\n\n"
            f"CURRENT ROBOT CONTEXT (JSON):\n"
            f"{json.dumps(context_block, indent=2)}\n\n"
            f"Generate JSON for command: \"{command}\""
        )

    def parse_response(self, response_text: str) -> PlannerResponse:
        """Clean Ollama response text and parse it into a PlannerResponse model."""
        cleaned = response_text.strip()
        
        # Remove code blocks markdown helper if model ignored the formatting constraint
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            data = json.loads(cleaned)
            return PlannerResponse.model_validate(data)
        except (json.JSONDecodeError, ValueError) as err:
            # Generate a structured error fallback response with empty plan list
            fallback = {
                "reasoning": {
                    "user_intent": "Failed to parse Ollama JSON output.",
                    "scene_analysis": "Error parsing output.",
                    "decision_process": f"Parser error: {str(err)}",
                    "safety_considerations": "Fallback empty plan triggered.",
                    "confidence": 0.0
                },
                "goal": "Error processing command",
                "task_status": "failed",
                "plan": [],
                "target": {},
                "explanation_for_user": "I encountered an error understanding your request. Please try again.",
                "clarification_required": False,
                "clarification_question": ""
            }
            return PlannerResponse.model_validate(fallback)

    def generate_plan(
        self,
        command: str,
        context: RobotContext,
        memory: ConversationMemory,
        image_data: bytes | None = None
    ) -> PlannerResponse:
        """Run the complete planning pipeline by calling local Ollama."""
        context_block = self.build_context(command, context, memory)
        prompt = self.build_prompt(command, context_block)

        import base64

        request_body = {
            "model": self.model_name,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "keep_alive": -1,
            "options": {
                "temperature": 0.1  # Highly deterministic responses
            }
        }

        # Encode and attach the latest camera frame if available
        if image_data:
            try:
                base64_image = base64.b64encode(image_data).decode("utf-8")
                request_body["images"] = [base64_image]
            except Exception as e:
                print(f"Error encoding image: {e}")

        url = f"{self.endpoint}/api/generate"
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(
            url,
            data=json.dumps(request_body).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                response_text = resp_data.get("response", "")
                return self.parse_response(response_text)
        except (urllib.error.URLError, TimeoutError, socket.timeout) as err:
            # Return an empty plan failure response when Ollama is unreachable
            fallback = {
                "reasoning": {
                    "user_intent": "Ollama service connection failed.",
                    "scene_analysis": "Cannot reach local Ollama endpoint.",
                    "decision_process": f"Connection error: {str(err)}",
                    "safety_considerations": "Safety fail-safe activated (empty plan).",
                    "confidence": 0.0
                },
                "goal": "Service unreachable",
                "task_status": "failed",
                "plan": [],
                "target": {},
                "explanation_for_user": "I am currently unable to reach my planning system. Please ensure Ollama is running.",
                "clarification_required": False,
                "clarification_question": ""
            }
            return PlannerResponse.model_validate(fallback)
