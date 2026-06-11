import os
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

APP_NAME = "Weather A2A Agent"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")

def build_agent_card() -> dict[str, Any]:
    return {
        "name": APP_NAME,
        "description": "A tiny public weather agent for A2A discovery tests.",
        "version": "1.0.0",
        "default_input_modes": ["text/plain", "application/json"],
        "default_output_modes": ["text/plain", "application/json"],
        "capabilities": {
            "streaming": False,
            "extended_agent_card": False,
        },
        "supported_interfaces": [
            {
                "protocol_binding": "JSONRPC",
                "url": PUBLIC_BASE_URL,
            }
        ],
        "skills": [
            {
                "id": "weather_lookup",
                "name": "Weather Lookup",
                "description": "Returns current weather and a short forecast for a city.",
                "tags": ["weather", "forecast", "temperature"],
                "examples": ["weather in Bengaluru", "what is the weather in Tokyo?"],
                "input_modes": ["text/plain", "application/json"],
                "output_modes": ["text/plain", "application/json"],
            }
        ],
    }

app = FastAPI(title=APP_NAME)

@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    return (
        f"{APP_NAME} is running. "
        "Fetch the agent card at /.well-known/agent-card.json "
        "or try /weather?city=London"
    )

@app.get("/.well-known/agent-card.json")
async def agent_card() -> JSONResponse:
    return JSONResponse(build_agent_card())

@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "time": datetime.utcnow().isoformat() + "Z"}

@app.get("/weather")
async def weather(city: str = Query(..., min_length=1)) -> JSONResponse:
    async with httpx.AsyncClient(timeout=20) as client:
        geo = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
        )
        geo.raise_for_status()
        geo_data = geo.json()
        results = geo_data.get("results") or []
        if not results:
            raise HTTPException(status_code=404, detail=f"City not found: {city}")

        place = results[0]
        lat = place["latitude"]
        lon = place["longitude"]

        forecast = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "timezone": "auto",
            },
        )
        forecast.raise_for_status()
        forecast_data = forecast.json()

    payload = {
        "city": city,
        "location": {
            "name": place.get("name"),
            "country": place.get("country"),
            "admin1": place.get("admin1"),
            "latitude": lat,
            "longitude": lon,
        },
        "current": forecast_data.get("current", {}),
        "daily": forecast_data.get("daily", {}),
        "source": "Open-Meteo",
    }
    return JSONResponse(payload)