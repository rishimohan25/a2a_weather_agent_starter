from __future__ import annotations

import os
import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from google import genai


APP_NAME = "A2A Gemini LLM Agent"
APP_VERSION = "1.0.0"
DEFAULT_USERNAME = "a2a_user"
DEFAULT_PASSWORD = "Welcome1"
DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_OAUTH_CLIENT_ID = "a2a_client"
DEFAULT_OAUTH_CLIENT_SECRET = "Welcome1"
DEFAULT_OAUTH_SCOPE = "a2a.invoke"
DEFAULT_OAUTH_TOKEN_TTL_SECONDS = 3600
TERMINAL_TASK_STATES = {
    "TASK_STATE_COMPLETED",
    "TASK_STATE_FAILED",
    "TASK_STATE_CANCELED",
    "TASK_STATE_CANCELLED",
    "TASK_STATE_REJECTED",
}

app = FastAPI(title=APP_NAME, version=APP_VERSION)
TASKS: Dict[str, Dict[str, Any]] = {}


def configured_auth_mode() -> str:
    return os.getenv("A2A_AUTH_MODE", "basic").strip().lower()


def configured_username() -> str:
    return os.getenv("A2A_BASIC_USERNAME", DEFAULT_USERNAME)


def configured_password() -> str:
    return os.getenv("A2A_BASIC_PASSWORD", DEFAULT_PASSWORD)


def configured_oauth_client_id() -> str:
    return os.getenv("A2A_OAUTH_CLIENT_ID", DEFAULT_OAUTH_CLIENT_ID)


def configured_oauth_client_secret() -> str:
    return os.getenv("A2A_OAUTH_CLIENT_SECRET", DEFAULT_OAUTH_CLIENT_SECRET)


def configured_oauth_scope() -> str:
    return os.getenv("A2A_OAUTH_SCOPE", DEFAULT_OAUTH_SCOPE)


def configured_oauth_token_ttl_seconds() -> int:
    raw_value = os.getenv("A2A_OAUTH_TOKEN_TTL_SECONDS")
    if not raw_value:
        return DEFAULT_OAUTH_TOKEN_TTL_SECONDS
    try:
        return max(60, int(raw_value))
    except ValueError:
        return DEFAULT_OAUTH_TOKEN_TTL_SECONDS


def oauth_signing_secret() -> str:
    return os.getenv("A2A_OAUTH_TOKEN_SIGNING_SECRET") or configured_oauth_client_secret()


def configured_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)


def configured_google_api_key() -> Optional[str]:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


def public_base_url() -> str:
    configured = os.getenv("PUBLIC_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return "http://localhost:%s" % os.getenv("PORT", "8080")


def require_auth(request: Request) -> str:
    auth_mode = configured_auth_mode()
    if auth_mode == "basic":
        return require_basic_auth(request)
    if auth_mode == "oauth2":
        return require_bearer_auth(request)
    if auth_mode == "both":
        try:
            return require_bearer_auth(request)
        except HTTPException:
            return require_basic_auth(request)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unsupported A2A_AUTH_MODE. Use basic, oauth2, or both.",
    )


def require_basic_auth(request: Request) -> str:
    scheme, value = split_authorization_header(request.headers.get("Authorization"))
    if scheme == "basic" and value:
        try:
            decoded = base64.b64decode(value).decode("utf-8")
        except Exception:
            decoded = ""
        username, separator, password = decoded.partition(":")
        if separator:
            valid_username = secrets.compare_digest(username, configured_username())
            valid_password = secrets.compare_digest(password, configured_password())
            if valid_username and valid_password:
                return username
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Basic authentication required",
        headers={"WWW-Authenticate": "Basic"},
    )


def require_bearer_auth(request: Request) -> str:
    scheme, token = split_authorization_header(request.headers.get("Authorization"))
    if scheme == "bearer" and token:
        subject = validate_oauth_access_token(token)
        if subject:
            return subject
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Bearer token required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def split_authorization_header(value: Optional[str]) -> tuple[str, str]:
    if not value:
        return "", ""
    scheme, separator, credentials = value.strip().partition(" ")
    if not separator:
        return "", ""
    return scheme.lower(), credentials.strip()


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "agent": APP_NAME,
        "version": APP_VERSION,
        "model": configured_model(),
        "googleApiKeyConfigured": bool(configured_google_api_key()),
        "authMode": configured_auth_mode(),
    }


@app.get("/.well-known/agent-card.json")
def agent_card() -> Dict[str, Any]:
    base_url = public_base_url()
    auth_mode = configured_auth_mode()
    security_scheme_id = "oauth2_client_credentials" if auth_mode == "oauth2" else "basic_auth"
    security_requirement = {"schemes": {security_scheme_id: {"list": []}}}
    security_schemes = {
        "basic_auth": {
            "httpAuthSecurityScheme": {
                "description": "HTTP Basic authentication for A2A invocation and task endpoints.",
                "scheme": "Basic",
            }
        }
    }
    if auth_mode == "oauth2":
        security_schemes = {
            "oauth2_client_credentials": {
                "oauth2SecurityScheme": {
                    "description": "OAuth 2.0 client credentials for A2A invocation and task endpoints.",
                    "tokenUrl": base_url + "/oauth/token",
                    "scopes": {
                        configured_oauth_scope(): "Invoke A2A skills and task lifecycle endpoints."
                    },
                }
            }
        }
    return {
        "name": APP_NAME,
        "description": "A stateful A2A test agent backed by Google Gemini with selectable Basic or OAuth 2.0 authentication.",
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
        "securitySchemes": security_schemes,
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


@app.post("/oauth/token")
async def oauth_token(request: Request) -> JSONResponse:
    client_id, client_secret, scope, grant_type = await parse_client_credentials_request(request)
    if grant_type != "client_credentials":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_grant_type")
    if not secrets.compare_digest(client_id, configured_oauth_client_id()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_client")
    if not secrets.compare_digest(client_secret, configured_oauth_client_secret()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_client")
    requested_scope = scope or configured_oauth_scope()
    allowed_scope = configured_oauth_scope()
    if requested_scope != allowed_scope:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_scope")
    ttl_seconds = configured_oauth_token_ttl_seconds()
    return JSONResponse(
        {
            "access_token": create_oauth_access_token(client_id, ttl_seconds),
            "token_type": "Bearer",
            "expires_in": ttl_seconds,
            "scope": allowed_scope,
        }
    )


@app.post("/")
async def jsonrpc_invoke(request: Request, _: str = Depends(require_auth)):
    payload = await request.json()
    request_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return jsonrpc_error(request_id, -32600, "Invalid JSON-RPC request")
    method = normalize_jsonrpc_method(payload.get("method"))
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        return jsonrpc_error(request_id, -32602, "JSON-RPC params must be an object")
    try:
        if method == "SendMessage":
            return jsonrpc_result(request_id, handle_send_message(params))
        if method == "SendStreamingMessage":
            return StreamingResponse(
                jsonrpc_wrap_sse_stream(request_id, stream_send_message(params)),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        if method == "GetTask":
            return jsonrpc_result(request_id, get_task_payload(required_task_id(params)))
        if method == "ListTasks":
            return jsonrpc_result(request_id, {"tasks": list_tasks_payload(optional_context_id(params))})
        if method == "CancelTask":
            return jsonrpc_result(request_id, cancel_task_payload(required_task_id(params)))
        if method == "SubscribeToTask":
            task_id = required_task_id(params)
            task = TASKS.get(task_id)
            if task is None:
                return jsonrpc_sse_error(request_id, -32004, "Task not found")
            if is_terminal_task(task):
                return jsonrpc_sse_error(request_id, -32005, "Task is already terminal")
            return StreamingResponse(
                jsonrpc_wrap_sse_stream(request_id, stream_task_subscription(task_id)),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return jsonrpc_error(request_id, -32601, "Method not found")
    except HTTPException as exc:
        return jsonrpc_error(request_id, -32000, str(exc.detail))
    except Exception as exc:
        return jsonrpc_error(request_id, -32000, str(exc))


@app.post("/message:send")
async def http_json_send_message(request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    payload = await request.json()
    return handle_send_message(payload)


@app.post("/message:stream")
async def http_json_stream_message(request: Request, _: str = Depends(require_auth)) -> StreamingResponse:
    payload = await request.json()
    return StreamingResponse(
        stream_send_message(payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/tasks/{task_id}")
def get_task(task_id: str, _: str = Depends(require_auth)) -> Dict[str, Any]:
    return get_task_payload(task_id)


@app.get("/tasks")
def list_tasks(contextId: Optional[str] = None, _: str = Depends(require_auth)) -> List[Dict[str, Any]]:
    return list_tasks_payload(contextId)


@app.post("/tasks/{task_id}:cancel")
def cancel_task(task_id: str, _: str = Depends(require_auth)) -> Dict[str, Any]:
    return cancel_task_payload(task_id)


@app.post("/tasks/{task_id}:subscribe")
async def subscribe_task(task_id: str, _: str = Depends(require_auth)) -> StreamingResponse:
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


def jsonrpc_result(request_id: Any, result: Any) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


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


def jsonrpc_sse_error(request_id: Any, code: int, message: str) -> StreamingResponse:
    async def error_stream():
        yield sse_data(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": code,
                    "message": message,
                },
            }
        )

    return StreamingResponse(
        error_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def parse_client_credentials_request(request: Request) -> tuple[str, str, str, str]:
    scheme, credentials = split_authorization_header(request.headers.get("Authorization"))
    body = await request.body()
    form = urllib.parse.parse_qs(body.decode("utf-8")) if body else {}
    client_id = first_form_value(form, "client_id")
    client_secret = first_form_value(form, "client_secret")
    if scheme == "basic" and credentials:
        try:
            decoded = base64.b64decode(credentials).decode("utf-8")
        except Exception:
            decoded = ""
        basic_client_id, separator, basic_client_secret = decoded.partition(":")
        if separator:
            client_id = urllib.parse.unquote(basic_client_id)
            client_secret = urllib.parse.unquote(basic_client_secret)
    return (
        client_id,
        client_secret,
        first_form_value(form, "scope"),
        first_form_value(form, "grant_type") or "client_credentials",
    )


def first_form_value(form: Dict[str, List[str]], key: str) -> str:
    values = form.get(key) or []
    return values[0] if values else ""


def create_oauth_access_token(subject: str, ttl_seconds: int) -> str:
    expires_at = int(time.time()) + ttl_seconds
    nonce = secrets.token_urlsafe(12)
    payload = "%s:%s:%s" % (subject, expires_at, nonce)
    signature = hmac.new(
        oauth_signing_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return "%s.%s" % (
        base64url_encode(payload.encode("utf-8")),
        base64url_encode(signature),
    )


def validate_oauth_access_token(token: str) -> Optional[str]:
    payload_part, separator, signature_part = token.partition(".")
    if not separator:
        return None
    try:
        payload_bytes = base64url_decode(payload_part)
        supplied_signature = base64url_decode(signature_part)
    except Exception:
        return None
    expected_signature = hmac.new(
        oauth_signing_secret().encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return None
    try:
        payload = payload_bytes.decode("utf-8")
        subject, expires_at, _nonce = payload.split(":", 2)
        if int(expires_at) < int(time.time()):
            return None
        return subject
    except Exception:
        return None


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def normalize_jsonrpc_method(method: Any) -> str:
    aliases = {
        "message/send": "SendMessage",
        "message:send": "SendMessage",
        "SendMessage": "SendMessage",
        "sendMessage": "SendMessage",
        "message/stream": "SendStreamingMessage",
        "message:stream": "SendStreamingMessage",
        "SendStreamingMessage": "SendStreamingMessage",
        "sendStreamingMessage": "SendStreamingMessage",
        "tasks/get": "GetTask",
        "GetTask": "GetTask",
        "getTask": "GetTask",
        "tasks/list": "ListTasks",
        "ListTasks": "ListTasks",
        "listTasks": "ListTasks",
        "tasks/cancel": "CancelTask",
        "CancelTask": "CancelTask",
        "cancelTask": "CancelTask",
        "tasks/subscribe": "SubscribeToTask",
        "SubscribeToTask": "SubscribeToTask",
        "subscribeToTask": "SubscribeToTask",
    }
    return aliases.get(str(method), "")


def required_task_id(params: Dict[str, Any]) -> str:
    task_id = (
        params.get("id")
        or params.get("taskId")
        or params.get("task_id")
        or (params.get("task") or {}).get("id")
    )
    if not task_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task id is required")
    return str(task_id)


def optional_context_id(params: Dict[str, Any]) -> Optional[str]:
    context_id = params.get("contextId") or params.get("context_id")
    if not context_id and isinstance(params.get("filter"), dict):
        context_id = params["filter"].get("contextId") or params["filter"].get("context_id")
    return str(context_id) if context_id else None


def get_task_payload(task_id: str) -> Dict[str, Any]:
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def list_tasks_payload(context_id: Optional[str] = None) -> List[Dict[str, Any]]:
    tasks = list(TASKS.values())
    if context_id:
        tasks = [task for task in tasks if task.get("contextId") == context_id]
    return tasks


def cancel_task_payload(task_id: str) -> Dict[str, Any]:
    task = get_task_payload(task_id)
    task["status"] = {
        "state": "TASK_STATE_CANCELED",
        "timestamp": utc_now(),
        "message": response_message("Task canceled.", {"contextId": task.get("contextId"), "taskId": task_id}),
    }
    task["updatedAt"] = utc_now()
    return task


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


async def jsonrpc_wrap_sse_stream(request_id: Any, a2a_stream):
    async for chunk in a2a_stream:
        for line in str(chunk).splitlines():
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if not data or data == "[DONE]":
                continue
            try:
                result = json.loads(data)
            except json.JSONDecodeError:
                result = {"message": {"parts": [{"text": data}]}}
            yield sse_data(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result,
                }
            )


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
