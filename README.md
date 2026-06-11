# Weather A2A Agent

This version fixes the card so it advertises the public Render host automatically.
It also accepts:
- `POST /`
- `POST /message:send`
- `POST /message/send`
- `POST /message:stream`
- `POST /message/stream`

## Render
Build command:
`pip install -r requirements.txt`

Start command:
`uvicorn main:app --host 0.0.0.0 --port $PORT`

## Test
Card:
`https://YOUR-SERVICE.onrender.com/.well-known/agent-card.json`

Invoke:
`curl -X POST https://YOUR-SERVICE.onrender.com/message:send -H 'Content-Type: application/json' -d '{"message":{"parts":[{"text":"weather in Bengaluru"}]}}'`