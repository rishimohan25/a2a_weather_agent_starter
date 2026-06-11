import re
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, TaskState

APP_NAME = "Weather A2A Agent"
PUBLIC_BASE_URL = "http://localhost:8000"


def extract_city(query: str) -> Optional[str]:
    if not query:
        return None

    patterns = [
        r"weather in ([A-Za-z][A-Za-z\s,.-]{1,80})",
        r"forecast for ([A-Za-z][A-Za-z\s,.-]{1,80})",
        r"in ([A-Za-z][A-Za-z\s,.-]{1,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            city = match.group(1).strip(" ?!.,")
            if city:
                return city
    return None


def build_agent_card() -> AgentCard:
    skill = AgentSkill(
        id="weather_lookup",
        name="Weather Lookup",
        description="Returns current weather and a short forecast for a city.",
        tags=["weather", "forecast", "temperature"],
        examples=["weather in Bengaluru", "forecast for Tokyo"],
        input_modes=["text/plain", "application/json"],
        output_modes=["text/plain", "application/json"],
    )

    return AgentCard(
        name=APP_NAME,
        description="A tiny weather agent for A2A interoperability testing.",
        version="1.0.0",
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["text/plain", "application/json"],
        capabilities=AgentCapabilities(streaming=True, extended_agent_card=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=PUBLIC_BASE_URL,
            )
        ],
        skills=[skill],
    )


class WeatherAgentExecutor(AgentExecutor):
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:
            return

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=context.current_task.id,
            context_id=context.current_task.context_id,
        )
        await updater.cancel()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )

        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message("Checking the weather..."),
        )

        query = get_message_text(context.message) or ""
        city = extract_city(query)

        if not city:
            result = "Tell me a city, for example: 'weather in Bengaluru' or 'forecast for Tokyo'."
        else:
            result = await self.lookup_weather(city)

        await updater.add_artifact(
            parts=[new_text_part(text=result, media_type="text/plain")],
            name="response",
            last_chunk=True,
        )

        await updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message("Request completed."),
        )

    async def lookup_weather(self, city: str) -> str:
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

        weather_codes = {
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

        def code_text(code: Any) -> str:
            try:
                return weather_codes.get(int(code), f"Weather code {code}")
            except Exception:
                return f"Weather code {code}"

        temp = current.get("temperature_2m", "unknown")
        wind = current.get("wind_speed_10m", "unknown")
        current_text = code_text(current.get("weather_code"))
        day_max = (daily.get("temperature_2m_max") or [None])[0]
        day_min = (daily.get("temperature_2m_min") or [None])[0]
        daily_text = code_text((daily.get("weather_code") or [None])[0])

        return (
            f"{place.get('name')}, {place.get('country')}: "
            f"now {temp}°C, {current_text}, wind {wind} km/h. "
            f"Today: high {day_max}°C, low {day_min}°C, {daily_text}."
        )


def create_app() -> FastAPI:
    agent_card = build_agent_card()
    request_handler = DefaultRequestHandler(
        agent_executor=WeatherAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    app = FastAPI(title=APP_NAME)

    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(agent_card),
        jsonrpc_routes=create_jsonrpc_routes(request_handler, rpc_url="/"),
        rest_routes=create_rest_routes(
            request_handler,
            enable_v0_3_compat=True,
            path_prefix="",
        ),
    )

    @app.get("/", response_class=PlainTextResponse)
    async def root() -> str:
        return (
            f"{APP_NAME} is running. "
            "Use /.well-known/agent-card.json for discovery, "
            "POST / for JSON-RPC, or POST /message/send for REST compatibility."
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "time": datetime.utcnow().isoformat() + "Z"}

    return app


app = create_app()
