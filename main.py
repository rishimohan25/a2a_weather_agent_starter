from __future__ import annotations

import ast
import operator
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials


APP_NAME = "A2A Basic Auth Interop Agent"
APP_VERSION = "1.0.0"
DEFAULT_USERNAME = "a2a_user"
DEFAULT_PASSWORD = "Welcome1"

security = HTTPBasic(auto_error=False)
app = FastAPI(title=APP_NAME, version=APP_VERSION)
TASKS: Dict[str, Dict[str, Any]] = {}


def configured_username() -> str:
    return os.getenv("A2A_BASIC_USERNAME", DEFAULT_USERNAME)


def configured_password() -> str:
    return os.getenv("A2A_BASIC_PASSWORD", DEFAULT_PASSWORD)


def public_base_url() -> str:
    configured = os.getenv("PUBLIC_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return "http://localhost:%s" % os.getenv("PORT", "8080")


def require_basic_auth(credentials: Optional[HTTPBasicCredentials] = Depends(security)) -> str:
    if credentials is not None:
        valid_username = secrets.compare_digest(credentials.username, configured_username())
        valid_password = secrets.compare_digest(credentials.password, configured_password())
        if valid_username and valid_password:
            return credentials.username
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Basic authentication required",
        headers={"WWW-Authenticate": "Basic"},
    )


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "agent": APP_NAME, "version": APP_VERSION}


@app.get("/.well-known/agent-card.json")
def agent_card() -> Dict[str, Any]:
    base_url = public_base_url()
    security_requirement = {"schemes": {"basic_auth": {"list": []}}}
    return {
        "name": APP_NAME,
        "description": "A deterministic A2A test agent with multiple skills and HTTP Basic authentication.",
        "version": APP_VERSION,
        "provider": {
            "organization": "A2A Connector POC",
            "url": base_url,
        },
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extendedAgentCard": False,
            "statefulTasks": True,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "supportedInterfaces": [
            {
                "url": base_url,
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
            },
            {
                "url": base_url + "/message:send",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
        ],
        "securitySchemes": {
            "basic_auth": {
                "httpAuthSecurityScheme": {
                    "description": "HTTP Basic authentication for A2A invocation endpoints.",
                    "scheme": "Basic",
                }
            }
        },
        "securityRequirements": [security_requirement],
        "skills": [
            {
                "id": "weather_lookup",
                "name": "Weather Lookup",
                "description": "Returns deterministic current weather and forecast text for supported cities.",
                "tags": ["weather", "forecast", "temperature"],
                "examples": ["weather in Bengaluru", "forecast for Tokyo", "weather in Chicago"],
                "inputModes": ["text/plain", "application/json"],
                "outputModes": ["text/plain", "application/json"],
                "securityRequirements": [security_requirement],
            },
            {
                "id": "calculator",
                "name": "Calculator",
                "description": "Evaluates simple arithmetic using +, -, *, /, and parentheses.",
                "tags": ["calculator", "math", "arithmetic"],
                "examples": ["calculate 12 * (4 + 2)", "what is 144 / 12?"],
                "inputModes": ["text/plain", "application/json"],
                "outputModes": ["text/plain", "application/json"],
                "securityRequirements": [security_requirement],
            },
            {
                "id": "text_transform",
                "name": "Text Transform",
                "description": "Transforms text to uppercase, lowercase, title case, or reverse order.",
                "tags": ["text", "transform", "formatting"],
                "examples": ["uppercase hello agent", "reverse connector", "title case agent to agent"],
                "inputModes": ["text/plain", "application/json"],
                "outputModes": ["text/plain", "application/json"],
                "securityRequirements": [security_requirement],
            },
        ],
    }


@app.post("/")
async def jsonrpc_invoke(request: Request, _: str = Depends(require_basic_auth)) -> JSONResponse:
    payload = await request.json()
    request_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return jsonrpc_error(request_id, -32600, "Invalid JSON-RPC request")
    if payload.get("method") != "message/send":
        return jsonrpc_error(request_id, -32601, "Method not found")
    try:
        result = handle_send_message(payload.get("params") or {})
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})
    except Exception as exc:
        return jsonrpc_error(request_id, -32000, str(exc))


@app.post("/message:send")
async def http_json_send_message(request: Request, _: str = Depends(require_basic_auth)) -> Dict[str, Any]:
    payload = await request.json()
    return handle_send_message(payload)


@app.get("/tasks/{task_id}")
def get_task(task_id: str, _: str = Depends(require_basic_auth)) -> Dict[str, Any]:
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@app.get("/tasks")
def list_tasks(contextId: Optional[str] = None, _: str = Depends(require_basic_auth)) -> List[Dict[str, Any]]:
    tasks = list(TASKS.values())
    if contextId:
        tasks = [task for task in tasks if task.get("contextId") == contextId]
    return tasks


@app.post("/tasks/{task_id}:cancel")
def cancel_task(task_id: str, _: str = Depends(require_basic_auth)) -> Dict[str, Any]:
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    task["status"] = {
        "state": "TASK_STATE_CANCELED",
        "timestamp": utc_now(),
        "message": response_message("Task canceled.", {"contextId": task.get("contextId"), "taskId": task_id}),
    }
    task["updatedAt"] = utc_now()
    return task


def jsonrpc_error(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
    )


def handle_send_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    message = payload.get("message") or {}
    text = extract_text(message)
    metadata = merge_metadata(payload.get("metadata"), message.get("metadata"))
    skill_id = resolve_skill_id(text, metadata)
    response_text = dispatch_skill(skill_id, text, metadata)
    task = upsert_task(message, skill_id, response_text)
    return {"task": task}


def upsert_task(message: Dict[str, Any], skill_id: str, response_text: str) -> Dict[str, Any]:
    task_id = message.get("taskId") or message.get("task_id") or str(uuid4())
    context_id = message.get("contextId") or message.get("context_id") or str(uuid4())
    state = infer_task_state(extract_text(message))
    existing = TASKS.get(task_id)
    task = existing or {
        "id": task_id,
        "contextId": context_id,
        "kind": "task",
        "metadata": {"skillId": skill_id},
        "history": [],
        "createdAt": utc_now(),
    }
    task["contextId"] = context_id
    task["metadata"]["skillId"] = skill_id
    task["status"] = {
        "state": state,
        "timestamp": utc_now(),
        "message": response_message(response_text, {"contextId": context_id, "taskId": task_id}),
    }
    task["updatedAt"] = utc_now()
    task["history"].append(
        {
            "messageId": message.get("messageId") or message.get("message_id"),
            "text": extract_text(message),
            "response": response_text,
            "state": state,
            "timestamp": utc_now(),
        }
    )
    if state == "TASK_STATE_COMPLETED":
        task["artifacts"] = [
            {
                "artifactId": "artifact-" + task_id,
                "name": skill_id + "-result",
                "parts": [{"text": response_text, "mediaType": "text/plain"}],
            }
        ]
    TASKS[task_id] = task
    return task


def infer_task_state(text: str) -> str:
    lowered = text.lower()
    if "need input" in lowered or "input required" in lowered:
        return "TASK_STATE_INPUT_REQUIRED"
    if "working" in lowered or "long running" in lowered:
        return "TASK_STATE_WORKING"
    return "TASK_STATE_COMPLETED"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_text(message: Dict[str, Any]) -> str:
    parts = message.get("parts") or []
    values = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if isinstance(part.get("text"), str):
            values.append(part["text"])
        elif isinstance(part.get("data"), (dict, list, str, int, float, bool)):
            values.append(str(part["data"]))
    return " ".join(values).strip()


def merge_metadata(*items: Any) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for item in items:
        if isinstance(item, dict):
            merged.update(item)
    return merged


def resolve_skill_id(text: str, metadata: Dict[str, Any]) -> str:
    requested = str(metadata.get("skillId") or metadata.get("skill_id") or "").strip().lower()
    aliases = {
        "weather": "weather_lookup",
        "weather_lookup": "weather_lookup",
        "calculator": "calculator",
        "calculate": "calculator",
        "math": "calculator",
        "text": "text_transform",
        "text_transform": "text_transform",
        "transform": "text_transform",
    }
    if requested in aliases:
        return aliases[requested]

    lowered = text.lower()
    if any(word in lowered for word in ("weather", "forecast", "temperature")):
        return "weather_lookup"
    if any(word in lowered for word in ("uppercase", "lowercase", "title case", "reverse", "transform")):
        return "text_transform"
    if looks_like_calculation(lowered):
        return "calculator"
    return "help"


def dispatch_skill(skill_id: str, text: str, metadata: Dict[str, Any]) -> str:
    if skill_id == "weather_lookup":
        return weather_lookup(text, metadata)
    if skill_id == "calculator":
        return calculator(text, metadata)
    if skill_id == "text_transform":
        return text_transform(text, metadata)
    return (
        "I can run weather_lookup, calculator, or text_transform. "
        "Try 'weather in Bengaluru', 'calculate 12 * (4 + 2)', or 'uppercase hello agent'."
    )


def response_message(text: str, request_message: Dict[str, Any]) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "messageId": str(uuid4()),
        "role": "ROLE_AGENT",
        "parts": [{"text": text, "mediaType": "text/plain"}],
    }
    context_id = request_message.get("contextId") or request_message.get("context_id")
    task_id = request_message.get("taskId") or request_message.get("task_id")
    if context_id:
        response["contextId"] = context_id
    if task_id:
        response["taskId"] = task_id
    return response


def weather_lookup(text: str, metadata: Dict[str, Any]) -> str:
    requested_city = str(metadata.get("city") or "").strip()
    lowered = (requested_city or text).lower()
    forecasts = {
        "bengaluru": "Bengaluru, India: now 24.0 C, partly cloudy, wind 11 km/h. Today: high 30 C, low 21 C, scattered showers.",
        "bangalore": "Bengaluru, India: now 24.0 C, partly cloudy, wind 11 km/h. Today: high 30 C, low 21 C, scattered showers.",
        "tokyo": "Tokyo, Japan: now 27.0 C, humid, wind 9 km/h. Today: high 31 C, low 24 C, light rain late evening.",
        "chicago": "Chicago, USA: now 18.0 C, clear, wind 16 km/h. Today: high 23 C, low 14 C, dry and breezy.",
    }
    for city, forecast in forecasts.items():
        if city in lowered:
            return forecast
    return "Tell me a supported city, for example: 'weather in Bengaluru', 'forecast for Tokyo', or 'weather in Chicago'."


def looks_like_calculation(text: str) -> bool:
    return bool(re.search(r"\d", text) and re.search(r"[+\-*/()]", text))


def calculator(text: str, metadata: Dict[str, Any]) -> str:
    expression = str(metadata.get("expression") or "").strip() or extract_expression(text)
    if not expression:
        return "Send a simple arithmetic expression, for example: 'calculate 12 * (4 + 2)'."
    try:
        result = evaluate_expression(expression)
    except ZeroDivisionError:
        return "Cannot divide by zero."
    except Exception:
        return "I can only evaluate numbers with +, -, *, /, and parentheses."
    return "%s = %s" % (expression, format_number(result))


def extract_expression(text: str) -> str:
    candidate = re.sub(r"(?i)\b(calculate|compute|what is|what's|math|please)\b", " ", text)
    candidate = candidate.strip(" ?:=\t\n")
    allowed = "".join(ch for ch in candidate if ch.isdigit() or ch in " +-*/().")
    return re.sub(r"\s+", " ", allowed).strip()


ALLOWED_BINARY_OPERATORS: Dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

ALLOWED_UNARY_OPERATORS: Dict[type, Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def evaluate_expression(expression: str) -> float:
    parsed = ast.parse(expression, mode="eval")
    return evaluate_node(parsed.body)


def evaluate_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINARY_OPERATORS:
        return ALLOWED_BINARY_OPERATORS[type(node.op)](evaluate_node(node.left), evaluate_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY_OPERATORS:
        return ALLOWED_UNARY_OPERATORS[type(node.op)](evaluate_node(node.operand))
    raise ValueError("unsupported expression")


def format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return ("%.6f" % value).rstrip("0").rstrip(".")


def text_transform(text: str, metadata: Dict[str, Any]) -> str:
    operation = str(metadata.get("operation") or "").strip().lower()
    content = str(metadata.get("text") or metadata.get("value") or "").strip()
    if not operation:
        operation = infer_text_operation(text)
    if not content:
        content = extract_transform_content(text, operation)
    if not content:
        return "Send text to transform, for example: 'uppercase hello agent' or 'reverse connector'."

    if operation in ("uppercase", "upper"):
        return content.upper()
    if operation in ("lowercase", "lower"):
        return content.lower()
    if operation in ("title", "titlecase", "title case"):
        return content.title()
    if operation == "reverse":
        return content[::-1]
    return "Supported text operations are uppercase, lowercase, title case, and reverse."


def infer_text_operation(text: str) -> str:
    lowered = text.lower()
    if "uppercase" in lowered or re.search(r"\bupper\b", lowered):
        return "uppercase"
    if "lowercase" in lowered or re.search(r"\blower\b", lowered):
        return "lowercase"
    if "title case" in lowered or re.search(r"\btitle\b", lowered):
        return "title"
    if "reverse" in lowered:
        return "reverse"
    return ""


def extract_transform_content(text: str, operation: str) -> str:
    if ":" in text:
        return text.split(":", 1)[1].strip()
    content = text
    for phrase in ("uppercase", "lowercase", "title case", "titlecase", "reverse", "transform", operation):
        if phrase:
            content = re.sub(re.escape(phrase), " ", content, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", content).strip(" ?:=\t\n")
