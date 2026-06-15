# A2A Basic Auth Interop Agent

A small FastAPI A2A test agent with a public Agent Card, Basic-auth protected invocation, three deterministic skills, and in-memory task lifecycle endpoints.

## Endpoints

- `GET /health`
- `GET /.well-known/agent-card.json`
- `POST /` for JSON-RPC `message/send`
- `POST /message:send` for HTTP+JSON style `SendMessageRequest`
- `GET /tasks/{taskId}` for task polling
- `GET /tasks?contextId=<contextId>` for task listing
- `POST /tasks/{taskId}:cancel` for task cancel

The Agent Card and health endpoint are public. Invoke and task endpoints require HTTP Basic auth.

## Skills

- `weather_lookup`: deterministic weather for Bengaluru, Tokyo, and Chicago.
- `calculator`: evaluates simple arithmetic using `+`, `-`, `*`, `/`, and parentheses.
- `text_transform`: uppercase, lowercase, title case, or reverse.

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export A2A_BASIC_USERNAME=a2a_user
export A2A_BASIC_PASSWORD=Welcome1
export PUBLIC_BASE_URL=http://localhost:8080
uvicorn main:app --host 0.0.0.0 --port 8080
```

## Render Deployment

Create a Render Web Service from the repository containing these files.

- Runtime: Python 3
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`

Set environment variables:

```text
PUBLIC_BASE_URL=https://<your-render-service>.onrender.com
A2A_BASIC_USERNAME=<your-user>
A2A_BASIC_PASSWORD=<your-password>
```

## Curl Tests

Fetch the public Agent Card:

```bash
curl 'https://<your-render-service>.onrender.com/.well-known/agent-card.json'
```

Verify invoke requires auth:

```bash
curl -i -X POST 'https://<your-render-service>.onrender.com/' \
  --header 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"messageId":"m-1","role":"ROLE_USER","parts":[{"text":"weather in Bengaluru"}]}}}'
```

Call the weather skill:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user '<your-user>:<your-password>' \
  --header 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"metadata":{"skillId":"weather_lookup"},"message":{"messageId":"m-1","role":"ROLE_USER","parts":[{"text":"weather in Bengaluru"}]}}}'
```

Call the HTTP+JSON send endpoint and create a task:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/message:send' \
  --user '<your-user>:<your-password>' \
  --header 'Content-Type: application/a2a+json' \
  --data '{"metadata":{"skillId":"weather_lookup"},"message":{"messageId":"m-http-1","role":"ROLE_USER","parts":[{"text":"weather in Bengaluru"}]}}'
```

Continue an existing task by sending `taskId` and `contextId` from a previous response:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/message:send' \
  --user '<your-user>:<your-password>' \
  --header 'Content-Type: application/a2a+json' \
  --data '{"message":{"messageId":"m-http-2","role":"ROLE_USER","taskId":"<task-id>","contextId":"<context-id>","parts":[{"text":"forecast for Tokyo"}]}}'
```

Get a task:

```bash
curl 'https://<your-render-service>.onrender.com/tasks/<task-id>' \
  --user '<your-user>:<your-password>'
```

List tasks for a context:

```bash
curl 'https://<your-render-service>.onrender.com/tasks?contextId=<context-id>' \
  --user '<your-user>:<your-password>'
```

Cancel a task:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/tasks/<task-id>:cancel' \
  --user '<your-user>:<your-password>'
```

Call the calculator skill:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user '<your-user>:<your-password>' \
  --header 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"2","method":"message/send","params":{"metadata":{"skillId":"calculator"},"message":{"messageId":"m-2","role":"ROLE_USER","parts":[{"text":"calculate 12 * (4 + 2)"}]}}}'
```

Call the text transform skill:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user '<your-user>:<your-password>' \
  --header 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"3","method":"message/send","params":{"metadata":{"skillId":"text_transform"},"message":{"messageId":"m-3","role":"ROLE_USER","parts":[{"text":"uppercase hello agent"}]}}}'
```

## Connector Gateway Notes

The Agent Card advertises Basic auth through `securitySchemes` and `securityRequirements`.

Runtime metadata should map this to an auth profile similar to:

```json
{
  "id": "basic_profile",
  "displayName": "Basic Authentication",
  "authType": "basic",
  "tokenSource": "stored",
  "inputBindings": {
    "username": "${authentication.username}",
    "password": "${authentication.password}"
  }
}
```

Store the actual values in connector config or vault:

```json
{
  "service": {
    "baseUrl": "https://<your-render-service>.onrender.com"
  },
  "authentication": {
    "selectedAuthProfile": "basic_profile",
    "username": "<your-user>",
    "password": "<your-password>"
  }
}
```

Do not store the username/password in the Agent Card or connector runtime metadata.

For stateful gateway testing, generate metadata with `connector.a2a.statefulTasks=true` and lifecycle operations for:

- `a2a.skill.message.send`: `POST /message:send`
- `a2a.task.get`: `GET /tasks/{taskId}`
- `a2a.task.list`: `GET /tasks`
- `a2a.task.cancel`: `POST /tasks/{taskId}:cancel`
- `a2a.task.continue`: `POST /message:send`

The gateway should store only task identifiers and status by MCP session. It should not persist the full message history returned by this test agent.
