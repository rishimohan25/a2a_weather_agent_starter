# A2A Gemini LLM Agent

A small FastAPI A2A test agent backed by Google Gemini. It has a public Agent Card, Basic-auth protected invocation, and stateful task endpoints for gateway task lifecycle testing.

## Endpoints

- `GET /health`
- `GET /.well-known/agent-card.json`
- `POST /` for JSON-RPC methods
- `POST /message:send` for HTTP+JSON style `SendMessageRequest`
- `POST /message:stream` for HTTP+JSON SSE streaming
- `GET /tasks/{taskId}` for task polling
- `GET /tasks?contextId=<contextId>` for task listing
- `POST /tasks/{taskId}:cancel` for task cancel
- `POST /tasks/{taskId}:subscribe` for SSE subscription to a non-terminal task

The Agent Card and health endpoint are public. Invoke and task endpoints require HTTP Basic auth.

## JSON-RPC Methods

`POST /` supports these JSON-RPC method names:

- `SendMessage`
- `SendStreamingMessage`
- `GetTask`
- `ListTasks`
- `CancelTask`
- `SubscribeToTask`

For backward compatibility, `message/send` is also accepted as an alias for `SendMessage`.

## Skills

- `llm_chat`: general Gemini-backed response.
- `llm_summarize`: concise summary bullets.
- `llm_extract_actions`: action item extraction.

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GOOGLE_API_KEY='<your-google-api-key>'
export GEMINI_MODEL='gemini-3.5-flash'
export A2A_BASIC_USERNAME='username'
export A2A_BASIC_PASSWORD='Welcome@123'
export PUBLIC_BASE_URL='http://localhost:8080'
uvicorn main:app --host 0.0.0.0 --port 8080
```

## Render Deployment

Create a Render Web Service from a repository containing this folder.

- Runtime: Python 3
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`

Set environment variables:

```text
PUBLIC_BASE_URL=https://<your-render-service>.onrender.com
GOOGLE_API_KEY=<your-google-api-key>
GEMINI_MODEL=gemini-3.5-flash
A2A_BASIC_USERNAME=username
A2A_BASIC_PASSWORD=Welcome@123
```

Do not put `GOOGLE_API_KEY` in the Agent Card or connector metadata.

## Direct Curl Tests

Fetch the public Agent Card:

```bash
curl 'https://<your-render-service>.onrender.com/.well-known/agent-card.json'
```

Check health:

```bash
curl 'https://<your-render-service>.onrender.com/health'
```

Create a Gemini-backed task:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/message:send' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/a2a+json' \
  --data '{
    "metadata": {"skillId": "llm_chat"},
    "message": {
      "messageId": "msg-llm-1",
      "role": "ROLE_USER",
      "parts": [
        {"text": "Explain A2A task state in two short sentences."}
      ]
    }
  }'
```

Create the same task through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/json' \
  --data '{
    "jsonrpc": "2.0",
    "id": "jsonrpc-send-1",
    "method": "SendMessage",
    "params": {
      "metadata": {"skillId": "llm_chat"},
      "message": {
        "messageId": "msg-jsonrpc-1",
        "role": "ROLE_USER",
        "parts": [
          {"text": "Explain A2A JSON-RPC binding in two short sentences."}
        ]
      }
    }
  }'
```

Create a non-terminal async task:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/message:send' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/a2a+json' \
  --data '{
    "metadata": {"skillId": "llm_chat"},
    "message": {
      "messageId": "msg-llm-async-1",
      "role": "ROLE_USER",
      "parts": [
        {"text": "Get the latest info about Nvidia"}
      ]
    }
  }'
```

Create a non-terminal async task through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/json' \
  --data '{
    "jsonrpc": "2.0",
    "id": "jsonrpc-async-1",
    "method": "SendMessage",
    "params": {
      "metadata": {"skillId": "llm_chat"},
      "message": {
        "messageId": "msg-jsonrpc-async-1",
        "role": "ROLE_USER",
        "parts": [
          {"text": "Get the latest info about Nvidia"}
        ]
      }
    }
  }'
```

Create a streamed Gemini-backed task:

```bash
curl -N -X POST 'https://<your-render-service>.onrender.com/message:stream' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/a2a+json' \
  --header 'Accept: text/event-stream' \
  --data '{
    "metadata": {"skillId": "llm_chat"},
    "message": {
      "messageId": "msg-llm-stream-1",
      "role": "ROLE_USER",
      "parts": [
        {"text": "Explain A2A streaming in two short sentences."}
      ]
    }
  }'
```

Create a streamed Gemini-backed task through JSON-RPC:

```bash
curl -N -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/json' \
  --header 'Accept: text/event-stream' \
  --data '{
    "jsonrpc": "2.0",
    "id": "jsonrpc-stream-1",
    "method": "SendStreamingMessage",
    "params": {
      "metadata": {"skillId": "llm_chat"},
      "message": {
        "messageId": "msg-jsonrpc-stream-1",
        "role": "ROLE_USER",
        "parts": [
          {"text": "Explain A2A streaming in two short sentences."}
        ]
      }
    }
  }'
```

Use the returned `task.id` and `task.contextId` for task lifecycle calls:

```bash
curl 'https://<your-render-service>.onrender.com/tasks/<task-id>' \
  --user 'username:Welcome@123'
```

Subscribe to a non-terminal task and complete it:

```bash
curl -N -X POST 'https://<your-render-service>.onrender.com/tasks/<task-id>:subscribe' \
  --user 'username:Welcome@123' \
  --header 'Accept: text/event-stream'
```

Poll a task through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/json' \
  --data '{
    "jsonrpc": "2.0",
    "id": "jsonrpc-get-1",
    "method": "GetTask",
    "params": {
      "id": "<task-id>"
    }
  }'
```

Subscribe to a non-terminal task through JSON-RPC:

```bash
curl -N -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/json' \
  --header 'Accept: text/event-stream' \
  --data '{
    "jsonrpc": "2.0",
    "id": "jsonrpc-subscribe-1",
    "method": "SubscribeToTask",
    "params": {
      "id": "<task-id>"
    }
  }'
```

```bash
curl 'https://<your-render-service>.onrender.com/tasks?contextId=<context-id>' \
  --user 'username:Welcome@123'
```

List tasks through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/json' \
  --data '{
    "jsonrpc": "2.0",
    "id": "jsonrpc-list-1",
    "method": "ListTasks",
    "params": {
      "contextId": "<context-id>"
    }
  }'
```

```bash
curl -X POST 'https://<your-render-service>.onrender.com/message:send' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/a2a+json' \
  --data '{
    "metadata": {"skillId": "llm_chat"},
    "message": {
      "messageId": "msg-llm-2",
      "role": "ROLE_USER",
      "taskId": "<task-id>",
      "contextId": "<context-id>",
      "parts": [
        {"text": "Continue the same answer with one practical example."}
      ]
    }
  }'
```

```bash
curl -X POST 'https://<your-render-service>.onrender.com/tasks/<task-id>:cancel' \
  --user 'username:Welcome@123'
```

Cancel a task through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'username:Welcome@123' \
  --header 'Content-Type: application/json' \
  --data '{
    "jsonrpc": "2.0",
    "id": "jsonrpc-cancel-1",
    "method": "CancelTask",
    "params": {
      "id": "<task-id>"
    }
  }'
```

## Gateway Test Flow

Generate connector runtime metadata from the Agent Card and make sure it includes:

- connector protocol: `A2A`
- use `connector.a2a.protocolBinding=HTTP+JSON` to test the HTTP+JSON paths
- use `connector.a2a.protocolBinding=JSONRPC` to test the JSON-RPC paths through `POST /`
- `connector.a2a.statefulTasks=true`
- for HTTP+JSON metadata, use REST-style paths such as `/message:send`, `/message:stream`, `/tasks/{taskId}`, `/tasks`, `/tasks/{taskId}:cancel`, and `/tasks/{taskId}:subscribe`
- for JSON-RPC metadata, use the selected interface URL as `service.baseUrl`, set operation `path` to empty, and map operation inputs into the JSON body; the gateway wraps the body as JSON-RPC `params`
- `a2a.skill.message.send` maps to `POST /message:send` or JSON-RPC `SendMessage`
- `a2a.skill.message.stream` maps to `POST /message:stream` or JSON-RPC `SendStreamingMessage`
- `a2a.task.get` maps to `GET /tasks/{taskId}` or JSON-RPC `GetTask`
- `a2a.task.subscribe` maps to `POST /tasks/{taskId}:subscribe` or JSON-RPC `SubscribeToTask`
- `a2a.task.list` maps to `GET /tasks` or JSON-RPC `ListTasks`
- `a2a.task.cancel` maps to `POST /tasks/{taskId}:cancel` or JSON-RPC `CancelTask`
- `a2a.task.continue` maps to `POST /message:send` or JSON-RPC `SendMessage`

Store auth in connector config or vault:

```json
{
  "service": {
    "baseUrl": "https://<your-render-service>.onrender.com"
  },
  "authentication": {
    "selectedAuthProfile": "basic_profile",
    "username": "username",
    "password": "Welcome@123"
  }
}
```

Then test through the gateway MCP endpoint:

1. `initialize`
2. `tools/list`
3. call the LLM skill tool
4. call the generated get task tool with `{}` to verify active task state
5. call the generated get task tool with `{"subscribe": true}` to subscribe until completion
6. call the generated list task tool with `{}`
7. call the generated continue task tool with only `text`
8. call the generated cancel task tool with `{}`

The important distributed-cache check is step 4: after a skill call creates a task, the gateway should be able to call get/list/continue/cancel without the caller passing `taskId`, because the active task is stored by MCP session.
