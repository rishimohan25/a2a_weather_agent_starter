# A2A Gemini LLM Agent

A small FastAPI A2A test agent backed by Google Gemini. It has a public Agent Card, selectable auth modes, and stateful task endpoints for gateway task lifecycle testing.

## Endpoints

- `GET /health`
- `GET /.well-known/agent-card.json`
- `GET /.well-known/openid-configuration` for OIDC/OAuth discovery testing
- `GET /oauth/authorize` for OAuth 2.0 authorization-code-with-PKCE callback testing
- `POST /oauth/token` for OAuth 2.0 client credentials or authorization-code token issuance
- `POST /` for JSON-RPC methods
- `POST /message:send` for HTTP+JSON style `SendMessageRequest`
- `POST /message:stream` for HTTP+JSON SSE streaming
- `GET /tasks/{taskId}` for task polling
- `GET /tasks?contextId=<contextId>` for task listing
- `POST /tasks/{taskId}:cancel` for task cancel
- `POST /tasks/{taskId}:subscribe` for SSE subscription to a non-terminal task

The Agent Card and health endpoint are public. Invoke and task endpoints require the auth mode configured by `A2A_AUTH_MODE`.

## Supported Auth Modes

Set `A2A_AUTH_MODE` to one of these values:

| Mode | Agent Card scheme | Invocation credential |
| --- | --- | --- |
| `all` | All supported test schemes | Any configured supported credential |
| `none` | No security requirement | No auth header or parameter |
| `basic` | `httpAuthSecurityScheme`, `Basic` | `Authorization: Basic ...` |
| `bearer_token` | `httpAuthSecurityScheme`, `Bearer` | `Authorization: Bearer <token>` |
| `api_key_header` | `apiKeySecurityScheme`, `header` | Header named by `A2A_API_KEY_NAME` |
| `api_key_query` | `apiKeySecurityScheme`, `query` | Query parameter named by `A2A_API_KEY_NAME` |
| `api_key_cookie` | `apiKeySecurityScheme`, `cookie` | Cookie named by `A2A_API_KEY_NAME` |
| `oauth2` | OAuth 2.0 client credentials flow | Bearer token from `/oauth/token` |
| `oauth2_authorization_code_pkce` | OAuth 2.0 authorization code + PKCE | Bearer token from `/oauth/token` |
| `oauth2_device_code` | OAuth 2.0 device code flow | Bearer token from `/oauth/token` |
| `oidc` | OpenID Connect discovery | Static bearer token for this test fixture |
| `mtls` | Mutual TLS | `X-Client-Cert-Fingerprint` header for Render testing |

`mtls` is a Render-compatible simulation. Render terminates TLS before the FastAPI app, so the app cannot validate a real client TLS certificate directly.
Deprecated OAuth implicit and password flows are not implemented.

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
export A2A_BASIC_USERNAME='<your-basic-username>'
export A2A_BASIC_PASSWORD='<your-basic-password>'
export PUBLIC_BASE_URL='http://localhost:8080'
uvicorn main:app --host 0.0.0.0 --port 8080
```

For no-auth local testing:

```bash
export A2A_AUTH_MODE='none'
```

For bearer-token local testing:

```bash
export A2A_AUTH_MODE='bearer_token'
export A2A_BEARER_TOKEN='<your-bearer-token>'
```

For API key local testing:

```bash
export A2A_AUTH_MODE='api_key_header'
export A2A_API_KEY_NAME='X-API-Key'
export A2A_API_KEY_VALUE='<your-api-key>'
```

Use `api_key_query` or `api_key_cookie` for query parameter or cookie based API key testing.

For OAuth 2.0 local testing:

```bash
export A2A_AUTH_MODE='oauth2'
export A2A_OAUTH_CLIENT_ID='a2a_client'
export A2A_OAUTH_CLIENT_SECRET='<your-client-secret>'
export A2A_OAUTH_SCOPE='a2a.invoke'
export A2A_OAUTH_TOKEN_SIGNING_SECRET='change-this-signing-secret'
```

For 3-legged OAuth 2.0 callback validation with PKCE:

```bash
export A2A_AUTH_MODE='oauth2_authorization_code_pkce'
export A2A_OAUTH_CLIENT_ID='a2a_client'
export A2A_OAUTH_SCOPE='a2a.invoke'
export A2A_OAUTH_TOKEN_SIGNING_SECRET='change-this-signing-secret'
export A2A_OAUTH_ALLOWED_REDIRECT_URIS='http://localhost:8080/v2/mcpGateway/auth/callback,http://localhost:8080/v2/mcpGateway/contentIntelligence/auth/callback'
export A2A_OAUTH_CODE_TTL_SECONDS='300'
```

For OIDC Agent Card discovery testing:

```bash
export A2A_AUTH_MODE='oidc'
export A2A_BEARER_TOKEN='<your-bearer-token>'
export A2A_OIDC_DISCOVERY_URL='https://<your-render-service>.onrender.com/.well-known/openid-configuration'
```

For OAuth 2.0 device-code flow testing:

```bash
export A2A_AUTH_MODE='oauth2_device_code'
export A2A_OAUTH_CLIENT_ID='a2a_client'
export A2A_OAUTH_SCOPE='a2a.invoke'
export A2A_OAUTH_TOKEN_SIGNING_SECRET='change-this-signing-secret'
export A2A_OAUTH_DEVICE_CODE_TTL_SECONDS='600'
```

For mTLS Agent Card testing on Render:

```bash
export A2A_AUTH_MODE='mtls'
export A2A_MTLS_CLIENT_CERT_FINGERPRINT='<your-client-cert-fingerprint>'
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
A2A_BASIC_USERNAME=<your-basic-username>
A2A_BASIC_PASSWORD=<your-basic-password>
```

Do not put `GOOGLE_API_KEY` in the Agent Card or connector metadata.

To make the Agent Card advertise every supported test auth scheme at once, use:

```text
A2A_AUTH_MODE=all
A2A_BASIC_USERNAME=<your-basic-username>
A2A_BASIC_PASSWORD=<your-basic-password>
A2A_BEARER_TOKEN=<your-bearer-token>
A2A_API_KEY_NAME=X-API-Key
A2A_API_KEY_VALUE=<your-api-key>
A2A_OAUTH_CLIENT_ID=a2a_client
A2A_OAUTH_CLIENT_SECRET=<your-client-secret>
A2A_OAUTH_SCOPE=a2a.invoke
A2A_OAUTH_TOKEN_SIGNING_SECRET=<long-random-signing-secret>
A2A_OAUTH_ALLOWED_REDIRECT_URIS=https://<gateway-host>/v2/mcpGateway/auth/callback,https://<gateway-host>/v2/mcpGateway/contentIntelligence/auth/callback
A2A_MTLS_CLIENT_CERT_FINGERPRINT=<your-client-cert-fingerprint>
```

In `all` mode the Agent Card includes Basic, Bearer, API key header/query/cookie, OAuth client credentials, OAuth authorization code with PKCE, OAuth device code, OIDC, and mTLS schemes. The invoke endpoints accept any one of the configured credentials.

### Render Auth Mode Configuration

Use one `A2A_AUTH_MODE` per deployment when testing connector auth mapping.

```text
# no auth
A2A_AUTH_MODE=none

# bearer token
A2A_AUTH_MODE=bearer_token
A2A_BEARER_TOKEN=<your-bearer-token>

# API key in header/query/cookie
A2A_AUTH_MODE=api_key_header
A2A_API_KEY_NAME=X-API-Key
A2A_API_KEY_VALUE=<your-api-key>

# OIDC discovery, with static bearer enforcement in this test fixture
A2A_AUTH_MODE=oidc
A2A_BEARER_TOKEN=<your-bearer-token>
A2A_OIDC_DISCOVERY_URL=https://<your-render-service>.onrender.com/.well-known/openid-configuration

# OAuth 2.0 device code
A2A_AUTH_MODE=oauth2_device_code
A2A_OAUTH_CLIENT_ID=a2a_client
A2A_OAUTH_SCOPE=a2a.invoke
A2A_OAUTH_TOKEN_SIGNING_SECRET=<long-random-signing-secret>
A2A_OAUTH_DEVICE_CODE_TTL_SECONDS=600

# mTLS Agent Card scheme, simulated behind Render
A2A_AUTH_MODE=mtls
A2A_MTLS_CLIENT_CERT_FINGERPRINT=<your-client-cert-fingerprint>
```

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

### Render OAuth 2.0 Authorization Code With PKCE Configuration

To test 3-legged OAuth callback validation, set these Render environment variables:

```text
PUBLIC_BASE_URL=https://<your-render-service>.onrender.com
GOOGLE_API_KEY=<your-google-api-key>
GEMINI_MODEL=gemini-3.5-flash
A2A_AUTH_MODE=oauth2_authorization_code_pkce
A2A_OAUTH_CLIENT_ID=a2a_client
A2A_OAUTH_SCOPE=a2a.invoke
A2A_OAUTH_TOKEN_SIGNING_SECRET=<long-random-signing-secret>
A2A_OAUTH_TOKEN_TTL_SECONDS=3600
A2A_OAUTH_CODE_TTL_SECONDS=300
A2A_OAUTH_ALLOWED_REDIRECT_URIS=https://<gateway-host>/v2/mcpGateway/auth/callback,https://<gateway-host>/v2/mcpGateway/contentIntelligence/auth/callback
```

When `A2A_AUTH_MODE=oauth2_authorization_code_pkce`, the public Agent Card advertises:

```text
authorizationUrl=https://<your-render-service>.onrender.com/oauth/authorize
tokenUrl=https://<your-render-service>.onrender.com/oauth/token
scope=a2a.invoke
```

In the connector UI/config, use an OAuth authorization-code PKCE profile. The gateway should generate the callback URL and PKCE verifier/challenge:

```json
{
  "authentication": {
    "selectedAuthProfile": "oauth2_authorization_code_pkce",
    "authorizationUrl": "https://<your-render-service>.onrender.com/oauth/authorize",
    "tokenUri": "https://<your-render-service>.onrender.com/oauth/token",
    "clientId": "a2a_client",
    "oauthScopes": "a2a.invoke"
  }
}
```

The test agent validates the callback URL by exact string match against `A2A_OAUTH_ALLOWED_REDIRECT_URIS`. Add the gateway callback URL used by your environment before starting the Render service.

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

Fetch an OAuth 2.0 authorization-code token manually with PKCE:

```bash
export CODE_VERIFIER='test-verifier-1234567890'
CODE_CHALLENGE=$(python -c 'import base64,hashlib,os; v=os.environ["CODE_VERIFIER"].encode("ascii"); print(base64.urlsafe_b64encode(hashlib.sha256(v).digest()).decode("ascii").rstrip("="))')

curl -iG 'https://<your-render-service>.onrender.com/oauth/authorize' \
  --data-urlencode 'response_type=code' \
  --data-urlencode 'client_id=a2a_client' \
  --data-urlencode 'redirect_uri=https://<gateway-host>/v2/mcpGateway/auth/callback' \
  --data-urlencode 'scope=a2a.invoke' \
  --data-urlencode 'state=manual-state-1' \
  --data-urlencode "code_challenge=$CODE_CHALLENGE" \
  --data-urlencode 'code_challenge_method=S256'

TOKEN=$(curl -s -X POST 'https://<your-render-service>.onrender.com/oauth/token' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=authorization_code' \
  --data-urlencode 'client_id=a2a_client' \
  --data-urlencode 'redirect_uri=https://<gateway-host>/v2/mcpGateway/auth/callback' \
  --data-urlencode 'code=<code-from-redirect>' \
  --data-urlencode "code_verifier=$CODE_VERIFIER" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

Fetch an OAuth 2.0 device-code token:

```bash
DEVICE_CODE=$(curl -s -X POST 'https://<your-render-service>.onrender.com/oauth/device_authorize' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'client_id=a2a_client' \
  --data-urlencode 'scope=a2a.invoke' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["device_code"])')

TOKEN=$(curl -s -X POST 'https://<your-render-service>.onrender.com/oauth/token' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=urn:ietf:params:oauth:grant-type:device_code' \
  --data-urlencode 'client_id=a2a_client' \
  --data-urlencode "device_code=$DEVICE_CODE" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

For OAuth mode, replace each `--user '<your-basic-username>:<your-basic-password>'` example below with:

```bash
--header "Authorization: Bearer $TOKEN"
```

For bearer-token or OIDC mode, use:

```bash
--header "Authorization: Bearer <your-bearer-token>"
```

For API key header mode, use:

```bash
--header "X-API-Key: <your-api-key>"
```

For API key query mode, append the configured query parameter:

```bash
?X-API-Key=<your-api-key>
```

For API key cookie mode, use:

```bash
--cookie "X-API-Key=<your-api-key>"
```

For mTLS simulation mode on Render, use:

```bash
--header "X-Client-Cert-Fingerprint: <your-client-cert-fingerprint>"
```

Create a Gemini-backed task:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/message:send' \
  --user '<your-basic-username>:<your-basic-password>' \
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
  --user '<your-basic-username>:<your-basic-password>' \
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
  --user '<your-basic-username>:<your-basic-password>' \
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
  --user '<your-basic-username>:<your-basic-password>' \
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
  --user '<your-basic-username>:<your-basic-password>' \
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
  --user '<your-basic-username>:<your-basic-password>' \
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
  --user '<your-basic-username>:<your-basic-password>'
```

Subscribe to a non-terminal task and complete it:

```bash
curl -N -X POST 'https://<your-render-service>.onrender.com/tasks/<task-id>:subscribe' \
  --user '<your-basic-username>:<your-basic-password>' \
  --header 'Accept: text/event-stream'
```

Poll a task through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user '<your-basic-username>:<your-basic-password>' \
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
  --user '<your-basic-username>:<your-basic-password>' \
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
  --user '<your-basic-username>:<your-basic-password>'
```

List tasks through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user '<your-basic-username>:<your-basic-password>' \
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
  --user '<your-basic-username>:<your-basic-password>' \
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
  --user '<your-basic-username>:<your-basic-password>'
```

Cancel a task through JSON-RPC:

```bash
curl -X POST 'https://<your-render-service>.onrender.com/' \
  --user '<your-basic-username>:<your-basic-password>' \
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
    "username": "<your-basic-username>",
    "password": "<your-basic-password>"
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
