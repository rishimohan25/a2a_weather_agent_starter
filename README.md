# Weather A2A Server

This version exposes:
- `/.well-known/agent-card.json`
- `POST /` JSON-RPC
- `POST /message/send` REST compatibility
- `/health`

Render settings:
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

After deploy, set:
- `PUBLIC_BASE_URL=https://<your-service>.onrender.com`

Test:
- `curl https://<your-service>.onrender.com/.well-known/agent-card.json`
- send your A2A client's JSON-RPC request to `POST /`
- send v0.3-style REST calls to `POST /message/send`
