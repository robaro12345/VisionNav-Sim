
from services.ai_core.graph import AgentState
import os
import logging

logger = logging.getLogger(__name__)

_MODEL = None
_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "yolo11n.pt"))


def _load_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    try:
        if not os.path.exists(_MODEL_PATH):
            raise FileNotFoundError(_MODEL_PATH)

        try:
            from ultralytics import YOLO

            _MODEL = YOLO(_MODEL_PATH)
            logger.info("Loaded YOLO model from %s", _MODEL_PATH)
        except Exception:
            import torch

            try:
                _MODEL = torch.jit.load(_MODEL_PATH, map_location="cpu")
            except Exception:
                _MODEL = torch.load(_MODEL_PATH, map_location="cpu")
            logger.info("Loaded torch model from %s", _MODEL_PATH)
    except Exception as e:
        logger.warning("Failed to load YOLO model (%s). Vision agent will fall back to a stub: %s", _MODEL_PATH, e)
        _MODEL = None
    return _MODEL


def _detect_with_model(img):
    # Try to run model if available. This function should be adapted for your model API.
    model = _load_model()
    if model is None:
        return []

    try:
        if hasattr(model, "predict"):
            res = model.predict(img, verbose=False)
            dets = []
            for r in res:
                names = getattr(r, "names", {}) or {}
                for box in getattr(r, "boxes", []):
                    cls_value = int(box.cls.item()) if hasattr(box.cls, "item") else int(box.cls)
                    dets.append(
                        {
                            "label": names.get(cls_value, str(cls_value)),
                            "confidence": float(box.conf.item()) if hasattr(box.conf, "item") else float(box.conf),
                            "bbox": [float(v) for v in box.xyxy[0].tolist()],
                        }
                    )
            return dets
        else:
            import torch
            tensor = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).float() / 255.0
            out = model(tensor)
            return []
    except Exception:
        logger.exception("Model-based detection failed")
        return []


def _stub_detect(img):
    # Very simple heuristic detector: look for large bright regions
    try:
        import cv2
        import numpy as np
    except Exception:
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    dets = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < 100:  # skip tiny
            continue
        dets.append({"label": "bright", "confidence": 0.5, "bbox": [float(x), float(y), float(w), float(h)]})
    return dets


def vision(state: AgentState) -> AgentState:
    """Vision agent: takes `state['sensors']['image']` (numpy BGR image) and populates
    `state['memory']['detections']`. If a likely target is detected, place a `memory.goal`.
    """
    state.setdefault("sensors", {})
    state.setdefault("memory", {})

    if state["memory"].get("drive_request"):
        state["memory"].setdefault("detections", [])
        state["memory"].setdefault("scene_description", "No camera frame available")
        return state

    img = state["sensors"].get("image")
    if img is None:
        state["memory"]["scene_description"] = "No camera frame available"
        state["memory"]["detections"] = []
        return state

    dets = []
    # try model first
    try:
        dets = _detect_with_model(img)
    except Exception:
        dets = []

    if not dets:
        dets = _stub_detect(img)

    state["memory"]["detections"] = dets

    state["memory"]["scene_description"] = _describe_detections(dets)
    state["memory"].setdefault("events", [])
    if dets:
        state["memory"]["events"].append({"type": "vision_detection", "count": len(dets)})

    if dets and not state["memory"].get("goal"):
        state["memory"]["goal"] = {
            "frame_id": "map",
            "position": {"x": 1.0, "y": 0.0, "z": 0.0},
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        }
        state["memory"]["goal_source"] = "vision"

    return state


def _describe_detections(detections):
    if not detections:
        return "No detections"

    top = detections[0]
    label = top.get("label", "object")
    confidence = top.get("confidence", 0.0)
    bbox = top.get("bbox", [])
    return f"{len(detections)} detections; top={label} confidence={confidence:.2f} bbox={bbox}"
