from __future__ import annotations

import os
import asyncio
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from google import genai


APP_NAME = "A2A Gemini LLM Agent"
APP_VERSION = "1.0.0"
DEFAULT_USERNAME = "a2a_user"
DEFAULT_PASSWORD = "Welcome1"
DEFAULT_MODEL = "gemini-3.5-flash"
TERMINAL_TASK_STATES = {
    "TASK_STATE_COMPLETED",
    "TASK_STATE_FAILED",
    "TASK_STATE_CANCELED",
    "TASK_STATE_CANCELLED",
    "TASK_STATE_REJECTED",
}

security = HTTPBasic(auto_error=False)
app = FastAPI(title=APP_NAME, version=APP_VERSION)
TASKS: Dict[str, Dict[str, Any]] = {}


def configured_username() -> str:
    return os.getenv("A2A_BASIC_USERNAME", DEFAULT_USERNAME)


def configured_password() -> str:
    return os.getenv("A2A_BASIC_PASSWORD", DEFAULT_PASSWORD)


def configured_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)


def configured_google_api_key() -> Optional[str]:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


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
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "agent": APP_NAME,
        "version": APP_VERSION,
        "model": configured_model(),
        "googleApiKeyConfigured": bool(configured_google_api_key()),
    }


@app.get("/.well-known/agent-card.json")
def agent_card() -> Dict[str, Any]:
    base_url = public_base_url()
    security_requirement = {"schemes": {"basic_auth": {"list": []}}}
    return {
        "name": APP_NAME,
        "description": "A stateful A2A test agent backed by Google Gemini and HTTP Basic authentication.",
        "version": APP_VERSION,
        "provider": {
            "organization": "A2A Connector POC",
            "url": base_url,
        },
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "extendedAgentCard": False,
            "statefulTasks": True,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "supportedInterfaces": [
            {
                "url": base_url,
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": base_url,
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
            },
        ],
        "securitySchemes": {
            "basic_auth": {
                "httpAuthSecurityScheme": {
                    "description": "HTTP Basic authentication for A2A invocation and task endpoints.",
                    "scheme": "Basic",
                }
            }
        },
        "securityRequirements": [security_requirement],
        "skills": [
            {
                "id": "llm_chat",
                "name": "LLM Chat",
                "description": "Uses Gemini to answer general user requests.",
                "tags": ["llm", "chat", "gemini"],
                "examples": [
                    "Explain A2A task state in two sentences.",
                    "Write a short support reply for a delayed delivery.",
                ],
                "inputModes": ["text/plain", "application/json"],
                "outputModes": ["text/plain", "application/json"],
                "securityRequirements": [security_requirement],
            },
            {
                "id": "llm_summarize",
                "name": "LLM Summarize",
                "description": "Uses Gemini to summarize text into concise bullets.",
                "tags": ["llm", "summary", "gemini"],
                "examples": [
                    "Summarize: The customer reported delayed delivery and asked for refund options.",
                    "Summarize this incident update in three bullets.",
                ],
                "inputModes": ["text/plain", "application/json"],
                "outputModes": ["text/plain", "application/json"],
                "securityRequirements": [security_requirement],
            },
            {
                "id": "llm_extract_actions",
                "name": "LLM Extract Actions",
                "description": "Uses Gemini to extract action items, owners, and dates from text.",
                "tags": ["llm", "actions", "gemini"],
                "examples": [
                    "Extract actions from: Rishi will update metadata by Friday.",
                    "Find follow-up tasks in this meeting note.",
                ],
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
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        return jsonrpc_error(request_id, -32000, str(exc))


@app.post("/message:send")
async def http_json_send_message(request: Request, _: str = Depends(require_basic_auth)) -> Dict[str, Any]:
    payload = await request.json()
    return handle_send_message(payload)


@app.post("/message:stream")
async def http_json_stream_message(request: Request, _: str = Depends(require_basic_auth)) -> StreamingResponse:
    payload = await request.json()
    return StreamingResponse(
        stream_send_message(payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


@app.post("/tasks/{task_id}:subscribe")
async def subscribe_task(task_id: str, _: str = Depends(require_basic_auth)) -> StreamingResponse:
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if is_terminal_task(task):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task is already terminal")
    return StreamingResponse(
        stream_task_subscription(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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

    if not text:
        text = "Ask the user for the missing input."

    state = infer_task_state(text, metadata)
    existing_task = TASKS.get(message.get("taskId") or message.get("task_id"))
    if existing_task and existing_task.get("status", {}).get("state") == "TASK_STATE_CANCELED":
        response_text = "This task was canceled. Start a new task to continue."
        state = "TASK_STATE_CANCELED"
    elif state == "TASK_STATE_WORKING":
        response_text = "Task accepted and marked as working for lifecycle testing. Poll get_task with this task id."
    else:
        response_text = generate_llm_response(skill_id, text, existing_task)

    task = upsert_task(message, skill_id, response_text, state)
    return {"task": task}


async def stream_task_subscription(task_id: str):
    task = TASKS[task_id]
    context_id = task["contextId"]
    skill_id = task.get("metadata", {}).get("skillId") or "llm_chat"
    text = latest_user_text(task) or "Continue this task."

    yield sse_data({"task": task})
    await asyncio.sleep(0.1)

    working_task = update_task_status(
        task,
        "Generating response with Gemini.",
        "TASK_STATE_WORKING",
    )
    yield sse_data(
        {
            "statusUpdate": {
                "taskId": task_id,
                "contextId": context_id,
                "status": working_task["status"],
            }
        }
    )
    await asyncio.sleep(0.1)

    try:
        response_text = generate_llm_response(skill_id, text, task)
        final_state = "TASK_STATE_COMPLETED"
    except HTTPException as exc:
        response_text = str(exc.detail)
        final_state = "TASK_STATE_FAILED"

    final_task = upsert_task(
        {"taskId": task_id, "contextId": context_id, "parts": [{"text": text}]},
        skill_id,
        response_text,
        final_state,
    )
    if final_state == "TASK_STATE_COMPLETED":
        yield sse_data(
            {
                "artifactUpdate": {
                    "taskId": task_id,
                    "contextId": context_id,
                    "artifact": final_task["artifacts"][0],
                }
            }
        )
        await asyncio.sleep(0.1)
    yield sse_data(
        {
            "statusUpdate": {
                "taskId": task_id,
                "contextId": context_id,
                "status": final_task["status"],
                "final": True,
            }
        }
    )


async def stream_send_message(payload: Dict[str, Any]):
    message = payload.get("message") or {}
    text = extract_text(message) or "Ask the user for the missing input."
    metadata = merge_metadata(payload.get("metadata"), message.get("metadata"))
    skill_id = resolve_skill_id(text, metadata)
    existing_task = TASKS.get(message.get("taskId") or message.get("task_id"))

    working_task = upsert_task(
        message,
        skill_id,
        "Gemini request accepted.",
        "TASK_STATE_WORKING",
    )
    task_id = working_task["id"]
    context_id = working_task["contextId"]
    yield sse_data({"task": working_task})
    await asyncio.sleep(0.1)

    yield sse_data(
        {
            "statusUpdate": {
                "taskId": task_id,
                "contextId": context_id,
                "status": {
                    "state": "TASK_STATE_WORKING",
                    "timestamp": utc_now(),
                    "message": response_message("Generating response with Gemini.", {"contextId": context_id, "taskId": task_id}),
                },
            }
        }
    )
    await asyncio.sleep(0.1)

    try:
        response_text = generate_llm_response(skill_id, text, existing_task)
        final_state = "TASK_STATE_COMPLETED"
    except HTTPException as exc:
        response_text = str(exc.detail)
        final_state = "TASK_STATE_FAILED"

    final_task = upsert_task(
        {**message, "taskId": task_id, "contextId": context_id},
        skill_id,
        response_text,
        final_state,
    )
    yield sse_data(
        {
            "artifactUpdate": {
                "taskId": task_id,
                "contextId": context_id,
                "artifact": {
                    "artifactId": "artifact-" + task_id,
                    "name": skill_id + "-stream-result",
                    "parts": [{"text": response_text, "mediaType": "text/plain"}],
                },
            }
        }
    )
    await asyncio.sleep(0.1)
    yield sse_data(
        {
            "statusUpdate": {
                "taskId": task_id,
                "contextId": context_id,
                "status": final_task["status"],
                "final": True,
            }
        }
    )


def sse_data(payload: Dict[str, Any]) -> str:
    return "data: " + json.dumps(payload, separators=(",", ":")) + "\n\n"


def generate_llm_response(skill_id: str, text: str, existing_task: Optional[Dict[str, Any]]) -> str:
    api_key = configured_google_api_key()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Set GOOGLE_API_KEY or GEMINI_API_KEY before invoking the LLM agent.",
        )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=configured_model(),
        contents=build_prompt(skill_id, text, existing_task),
    )
    result = getattr(response, "text", None)
    if not result or not result.strip():
        return "Gemini returned an empty response."
    return result.strip()


def build_prompt(skill_id: str, text: str, existing_task: Optional[Dict[str, Any]]) -> str:
    history_text = ""
    if existing_task:
        recent_history = existing_task.get("history", [])[-3:]
        history_text = "\nRecent task history:\n" + "\n".join(
            "- User: %s\n  Agent: %s" % (item.get("text", ""), item.get("response", ""))
            for item in recent_history
        )

    if skill_id == "llm_summarize":
        instruction = "Summarize the user's text in 3 concise bullets. Do not invent facts."
    elif skill_id == "llm_extract_actions":
        instruction = "Extract action items from the user's text. Return concise bullets with owner, action, and due date when present."
    else:
        instruction = "Answer the user's request clearly and concisely."

    return "%s\n%s\n\nUser request:\n%s" % (instruction, history_text, text)


def upsert_task(message: Dict[str, Any], skill_id: str, response_text: str, state: str) -> Dict[str, Any]:
    task_id = message.get("taskId") or message.get("task_id") or str(uuid4())
    existing = TASKS.get(task_id)
    context_id = (
        message.get("contextId")
        or message.get("context_id")
        or (existing or {}).get("contextId")
        or str(uuid4())
    )
    task = existing or {
        "id": task_id,
        "contextId": context_id,
        "kind": "task",
        "metadata": {"skillId": skill_id, "model": configured_model()},
        "history": [],
        "createdAt": utc_now(),
    }
    task["contextId"] = context_id
    task["metadata"]["skillId"] = skill_id
    task["metadata"]["model"] = configured_model()
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
    elif "artifacts" in task:
        task.pop("artifacts")
    TASKS[task_id] = task
    return task


def infer_task_state(text: str, metadata: Dict[str, Any]) -> str:
    forced_state = str(metadata.get("forceState") or metadata.get("force_state") or "").strip().lower()
    if forced_state in ("input_required", "input-required", "TASK_STATE_INPUT_REQUIRED".lower()):
        return "TASK_STATE_INPUT_REQUIRED"
    if forced_state in ("working", "TASK_STATE_WORKING".lower()):
        return "TASK_STATE_WORKING"
    if forced_state in ("completed", "complete", "TASK_STATE_COMPLETED".lower()):
        return "TASK_STATE_COMPLETED"

    lowered = text.lower()
    if "need input" in lowered or "input required" in lowered:
        return "TASK_STATE_INPUT_REQUIRED"
    if (
        "working" in lowered
        or "long running" in lowered
        or "latest info" in lowered
        or "latest information" in lowered
        or "research" in lowered
        or "async" in lowered
    ):
        return "TASK_STATE_WORKING"
    return "TASK_STATE_COMPLETED"


def resolve_skill_id(text: str, metadata: Dict[str, Any]) -> str:
    requested = str(metadata.get("skillId") or metadata.get("skill_id") or "").strip().lower()
    aliases = {
        "chat": "llm_chat",
        "llm_chat": "llm_chat",
        "summarize": "llm_summarize",
        "summary": "llm_summarize",
        "llm_summarize": "llm_summarize",
        "actions": "llm_extract_actions",
        "extract_actions": "llm_extract_actions",
        "llm_extract_actions": "llm_extract_actions",
    }
    if requested in aliases:
        return aliases[requested]

    lowered = text.lower()
    if "summarize" in lowered or "summary" in lowered:
        return "llm_summarize"
    if "action item" in lowered or "extract actions" in lowered:
        return "llm_extract_actions"
    return "llm_chat"


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_terminal_task(task: Dict[str, Any]) -> bool:
    return str(task.get("status", {}).get("state") or "").upper() in TERMINAL_TASK_STATES


def latest_user_text(task: Dict[str, Any]) -> str:
    for item in reversed(task.get("history", [])):
        text = str(item.get("text") or "").strip()
        if text:
            return text
    return ""


def update_task_status(task: Dict[str, Any], response_text: str, state: str) -> Dict[str, Any]:
    task_id = task["id"]
    context_id = task["contextId"]
    task["status"] = {
        "state": state,
        "timestamp": utc_now(),
        "message": response_message(response_text, {"contextId": context_id, "taskId": task_id}),
    }
    task["updatedAt"] = utc_now()
    TASKS[task_id] = task
    return task
