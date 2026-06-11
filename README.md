# Weather A2A Agent Starter

This is a small public weather-agent starter you can deploy to a free host.

## Endpoints

- `/.well-known/agent-card.json` — A2A agent card
- `/weather?city=London` — current weather lookup
- `/health` — simple health check

## Deploy on Render

1. Create a new GitHub repo and add these files.
2. Create a new Render Web Service from that repo.
3. Use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Set `PUBLIC_BASE_URL` to your Render URL once the service is created.
5. Your public Agent Card will be at:
   `https://YOUR-SERVICE.onrender.com/.well-known/agent-card.json`

Render documents free web services and static sites, and its quickstart says no payment is required for the first deploy flow. Cloudflare Workers also has a Free plan if you prefer edge hosting.