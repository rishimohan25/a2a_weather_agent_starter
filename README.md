# A2A Gemini LLM Agent

A small FastAPI A2A test agent backed by Google Gemini. It has a public Agent Card, Basic-auth protected invocation, and stateful task endpoints for gateway task lifecycle testing.

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
export A2A_BASIC_USERNAME='test'
export A2A_BASIC_PASSWORD='password'
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
A2A_BASIC_USERNAME=test
A2A_BASIC_PASSWORD=password
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
  --user 'rismohan:Welcome@123' \
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

Use the returned `task.id` and `task.contextId` for task lifecycle calls:

```bash
curl 'https://<your-render-service>.onrender.com/tasks/<task-id>' \
  --user 'test:pasword'
```

```bash
curl 'https://<your-render-service>.onrender.com/tasks?contextId=<context-id>' \
  --user 'test:pasword'
```

```bash
curl -X POST 'https://<your-render-service>.onrender.com/message:send' \
  --user 'test:pasword' \
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
  --user 'test:pasword'
```

## Gateway Test Flow

Generate connector runtime metadata from the Agent Card and make sure it includes:

- connector protocol: `A2A`
- `connector.a2a.statefulTasks=true`
- `a2a.skill.message.send`: `POST /message:send`
- `a2a.task.get`: `GET /tasks/{taskId}`
- `a2a.task.list`: `GET /tasks`
- `a2a.task.cancel`: `POST /tasks/{taskId}:cancel`
- `a2a.task.continue`: `POST /message:send`

Store auth in connector config or vault:

```json
{
  "service": {
    "baseUrl": "https://<your-render-service>.onrender.com"
  },
  "authentication": {
    "selectedAuthProfile": "basic_profile",
    "username": "",
    "password": ""
  }
}
```

Then test through the gateway MCP endpoint:

1. `initialize`
2. `tools/list`
3. call the LLM skill tool
4. call the generated get task tool with `{}` to verify active task state
5. call the generated list task tool with `{}`
6. call the generated continue task tool with only `text`
7. call the generated cancel task tool with `{}`

The important distributed-cache check is step 4: after a skill call creates a task, the gateway should be able to call get/list/continue/cancel without the caller passing `taskId`, because the active task is stored by MCP session.
