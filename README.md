# A2A Gemini LLM Agent

A small FastAPI A2A test agent backed by Google Gemini. It has a public Agent Card, selectable Basic or OAuth 2.0 protected invocation, and stateful task endpoints for gateway task lifecycle testing.

## Endpoints

- `GET /health`
- `GET /.well-known/agent-card.json`
- `POST /oauth/token` for OAuth 2.0 client credentials token issuance
- `POST /` for JSON-RPC methods
- `POST /message:send` for HTTP+JSON style `SendMessageRequest`
- `POST /message:stream` for HTTP+JSON SSE streaming
- `GET /tasks/{taskId}` for task polling
- `GET /tasks?contextId=<contextId>` for task listing
- `POST /tasks/{taskId}:cancel` for task cancel
- `POST /tasks/{taskId}:subscribe` for SSE subscription to a non-terminal task

The Agent Card and health endpoint are public. Invoke and task endpoints require the auth mode configured by `A2A_AUTH_MODE`.

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
export A2A_AUTH_MODE='basic'
export A2A_BASIC_USERNAME='rismohan'
export A2A_BASIC_PASSWORD='Welcome@123'
export PUBLIC_BASE_URL='http://localhost:8080'
uvicorn main:app --host 0.0.0.0 --port 8080
```

For OAuth 2.0 local testing:

```bash
export A2A_AUTH_MODE='oauth2'
export A2A_OAUTH_CLIENT_ID='a2a_client'
export A2A_OAUTH_CLIENT_SECRET='Welcome@123'
export A2A_OAUTH_SCOPE='a2a.invoke'
export A2A_OAUTH_TOKEN_SIGNING_SECRET='change-this-signing-secret'
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
A2A_AUTH_MODE=basic
A2A_BASIC_USERNAME=rismohan
A2A_BASIC_PASSWORD=Welcome@123
```

Do not put `GOOGLE_API_KEY` in the Agent Card or connector metadata.

### Render OAuth 2.0 Configuration

To test OAuth 2.0 instead of Basic auth, set these Render environment variables:

```text
PUBLIC_BASE_URL=https://<your-render-service>.onrender.com
GOOGLE_API_KEY=<your-google-api-key>
GEMINI_MODEL=gemini-3.5-flash
A2A_AUTH_MODE=oauth2
A2A_OAUTH_CLIENT_ID=a2a_client
A2A_OAUTH_CLIENT_SECRET=<your-client-secret>
A2A_OAUTH_SCOPE=a2a.invoke
A2A_OAUTH_TOKEN_SIGNING_SECRET=<long-random-signing-secret>
A2A_OAUTH_TOKEN_TTL_SECONDS=3600
```

Keep `A2A_OAUTH_CLIENT_SECRET`, `A2A_OAUTH_TOKEN_SIGNING_SECRET`, and `GOOGLE_API_KEY` as Render secret values.

When `A2A_AUTH_MODE=oauth2`, the public Agent Card advertises an OAuth 2.0 client-credentials security scheme with:

```text
tokenUrl=https://<your-render-service>.onrender.com/oauth/token
scope=a2a.invoke
```

In the connector UI/config, use an OAuth client-credentials profile:

```json
{
  "authentication": {
    "selectedAuthProfile": "oauth2_client_credentials",
    "tokenUri": "https://<your-render-service>.onrender.com/oauth/token",
    "clientId": "a2a_client",
    "clientSecret": "<your-client-secret>",
    "oauthScopes": "a2a.invoke"
  }
}
```

The gateway should fetch the token from `/oauth/token` and call the A2A invoke/task endpoints with:

```text
Authorization: Bearer <access_token>
```

## Direct Curl Tests

Fetch the public Agent Card:

```bash
curl 'https://<your-render-service>.onrender.com/.well-known/agent-card.json'
```

Check health:

```bash
curl 'https://<your-render-service>.onrender.com/health'
```

Fetch an OAuth 2.0 access token:

```bash
TOKEN=$(curl -s -X POST 'https://<your-render-service>.onrender.com/oauth/token' \
  --user 'a2a_client:<your-client-secret>' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data 'grant_type=client_credentials&scope=a2a.invoke' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

For OAuth mode, replace each `--user 'rismohan:Welcome@123'` example below with:

```bash
--header "Authorization: Bearer $TOKEN"
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

Create the same task through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'rismohan:Welcome@123' \
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
  --user 'rismohan:Welcome@123' \
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
  --user 'rismohan:Welcome@123' \
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
  --user 'rismohan:Welcome@123' \
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
  --user 'rismohan:Welcome@123' \
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
  --user 'rismohan:Welcome@123'
```

Subscribe to a non-terminal task and complete it:

```bash
curl -N -X POST 'https://<your-render-service>.onrender.com/tasks/<task-id>:subscribe' \
  --user 'rismohan:Welcome@123' \
  --header 'Accept: text/event-stream'
```

Poll a task through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'rismohan:Welcome@123' \
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
  --user 'rismohan:Welcome@123' \
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
  --user 'rismohan:Welcome@123'
```

List tasks through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'rismohan:Welcome@123' \
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
  --user 'rismohan:Welcome@123' \
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
  --user 'rismohan:Welcome@123'
```

Cancel a task through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user 'rismohan:Welcome@123' \
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
    "username": "rismohan",
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
