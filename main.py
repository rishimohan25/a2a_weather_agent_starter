import json
import os
import re
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

APP_NAME = "Weather A2A Agent"
APP_VERSION = "1.0.1"

app = FastAPI(title=APP_NAME)

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
}


def _public_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if not host:
        return str(request.base_url).rstrip("/")
    return f"{proto}://{host}".rstrip("/")


def _extract_city(text: str) -> Optional[str]:
    if not text:
        return None

    patterns = [
        r"weather in ([A-Za-z][A-Za-z\s,.\-']{1,80})",
        r"forecast for ([A-Za-z][A-Za-z\s,.\-']{1,80})",
        r"in ([A-Za-z][A-Za-z\s,.\-']{1,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            city = match.group(1).strip(" ?!.,")
            if city:
                return city
    return None


def _weather_code_text(code: Any) -> str:
    try:
        return WEATHER_CODES.get(int(code), f"Weather code {code}")
    except Exception:
        return f"Weather code {code}"


async def _lookup_weather(city: str) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        geo = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
        )
        geo.raise_for_status()
        geo_data = geo.json()
        results = geo_data.get("results") or []
        if not results:
            return f"I could not find a city named '{city}'."

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

    current = forecast_data.get("current", {})
    daily = forecast_data.get("daily", {})

    temp = current.get("temperature_2m", "unknown")
    wind = current.get("wind_speed_10m", "unknown")
    current_text = _weather_code_text(current.get("weather_code"))

    day_max = (daily.get("temperature_2m_max") or [None])[0]
    day_min = (daily.get("temperature_2m_min") or [None])[0]
    daily_text = _weather_code_text((daily.get("weather_code") or [None])[0])

    return (
        f"{place.get('name')}, {place.get('country')}: "
        f"now {temp}°C, {current_text}, wind {wind} km/h. "
        f"Today: high {day_max}°C, low {day_min}°C, {daily_text}."
    )


def _agent_card(request: Request) -> Dict[str, Any]:
    base_url = _public_base_url(request)
    return {
        "name": APP_NAME,
        "description": "A tiny weather agent for A2A interoperability testing.",
        "version": APP_VERSION,
        "capabilities": {
            "streaming": False,
            "extendedAgentCard": False,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "supportedInterfaces": [
            {
                "url": base_url,
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
            }
        ],
        "skills": [
            {
                "id": "weather_lookup",
                "name": "Weather Lookup",
                "description": "Returns current weather and a short forecast for a city.",
                "tags": ["weather", "forecast", "temperature"],
                "examples": ["weather in Bengaluru", "forecast for Tokyo"],
                "inputModes": ["text/plain", "application/json"],
                "outputModes": ["text/plain", "application/json"],
            }
        ],
    }


def _extract_text_from_body(body: Any) -> str:
    if isinstance(body, dict):
        if isinstance(body.get("message"), dict):
            message = body["message"]
            if isinstance(message.get("parts"), list):
                texts = []
                for part in message["parts"]:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        texts.append(part["text"])
                if texts:
                    return "\n".join(texts)
            for key in ("text", "content", "query", "prompt"):
                if isinstance(message.get(key), str):
                    return message[key]

        if isinstance(body.get("params"), dict):
            params = body["params"]
            if isinstance(params.get("message"), dict):
                nested = _extract_text_from_body({"message": params["message"]})
                if nested:
                    return nested
            for key in ("text", "content", "query", "prompt"):
                if isinstance(params.get(key), str):
                    return params[key]

        for key in ("text", "content", "query", "prompt"):
            if isinstance(body.get(key), str):
                return body[key]

    return ""


async def _build_reply(text: str) -> str:
    city = _extract_city(text)
    if not city:
        return "Tell me a city, for example: 'weather in Bengaluru' or 'forecast for Tokyo'."
    return await _lookup_weather(city)


def _jsonrpc_response(request_id: Any, reply_text: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "message": {
                "role": "ROLE_AGENT",
                "parts": [
                    {
                        "text": reply_text
                    }
                ]
            }
        }
    }


def _rest_response(reply_text: str) -> Dict[str, Any]:
    return {
        "message": {
            "role": "ROLE_AGENT",
            "parts": [
                {
                    "text": reply_text
                }
            ]
        }
    }


@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    return (
        f"{APP_NAME} is running. "
        "Use /.well-known/agent-card.json for discovery, "
        "POST / for JSON-RPC, or POST /message:send / POST /message/send for invoke testing."
    )


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/.well-known/agent-card.json")
async def agent_card(request: Request) -> JSONResponse:
    return JSONResponse(_agent_card(request))


async def _handle_invoke(request: Request) -> JSONResponse:
    body: Any = None
    try:
        body = await request.json()
    except Exception:
        body = {}

    text = _extract_text_from_body(body) if isinstance(body, dict) else ""
    reply = await _build_reply(text)

    is_jsonrpc = isinstance(body, dict) and body.get("jsonrpc") == "2.0" and "id" in body
    if is_jsonrpc:
        return JSONResponse(_jsonrpc_response(body.get("id"), reply))
    return JSONResponse(_rest_response(reply))


@app.post("/")
async def post_root(request: Request) -> JSONResponse:
    return await _handle_invoke(request)


@app.post("/message:send")
async def message_send_colon(request: Request) -> JSONResponse:
    return await _handle_invoke(request)


@app.post("/message/send")
async def message_send_slash(request: Request) -> JSONResponse:
    return await _handle_invoke(request)


@app.post("/message:stream")
async def message_stream_colon(request: Request) -> JSONResponse:
    return await _handle_invoke(request)


@app.post("/message/stream")
async def message_stream_slash(request: Request) -> JSONResponse:
    return await _handle_invoke(request)