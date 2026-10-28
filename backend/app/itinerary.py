import json
import logging
import math
from datetime import timedelta
from typing import Any

from groq import APIConnectionError, APIStatusError, Groq, RateLimitError
from pydantic import ValidationError

from app.config import Settings
from app.models import ItineraryDay, ItineraryPlan, TripInput

logger = logging.getLogger(__name__)


class AIServiceError(Exception):
    def __init__(self, message: str, *, rate_limited: bool = False, retry_after: int = 30) -> None:
        super().__init__(message)
        self.rate_limited = rate_limited
        self.retry_after = retry_after


SYSTEM_PROMPT = """You are a practical travel planner. Return only one JSON object matching the requested schema.
Plan a safe, geographically sensible itinerary. All estimated costs are total costs for the entire group and in the requested currency.
Use valid 24-hour HH:MM times. Stops must be in chronological order. Group nearby attractions between fixed meal stops.
Include at least one dining stop per day, realistic transit notes, and one accommodation suggestion per day.
Keep the sum of daily costs and the overall total at or below the total trip budget. Keep activities appropriate to group size,
dates, interests, and pacing. Do not invent precise coordinates when uncertain; use null for both latitude and longitude.
Return this exact shape:
{"title":"string","summary":"string","total_estimated_cost":0,"currency":"USD","days":[
{"day_number":1,"date":"YYYY-MM-DD","theme":"string","estimated_cost":0,
"stops":[{"time":"09:00","kind":"attraction|dining|experience","title":"string","description":"string",
"location":"string","latitude":null,"longitude":null,"duration_minutes":60,"estimated_cost":0}],
"accommodation":{"name":"string","neighborhood":"string","nightly_cost":0,"notes":"string"},
"transportation":["string"]}]}
"""


def _validate_plan(plan: ItineraryPlan, request: TripInput) -> None:
    expected_dates = [request.start_date + timedelta(days=offset) for offset in range(request.day_count)]
    actual_dates = [day.date for day in plan.days]
    if len(plan.days) != request.day_count or actual_dates != expected_dates:
        raise ValueError("The plan must include exactly one correctly dated entry for every trip day.")
    if [day.day_number for day in plan.days] != list(range(1, request.day_count + 1)):
        raise ValueError("Day numbers must be sequential and match the requested dates.")
    if plan.currency != request.currency:
        raise ValueError("The itinerary currency must match the requested currency.")
    if any(not any(stop.kind == "dining" for stop in day.stops) for day in plan.days):
        raise ValueError("Every day must include at least one dining stop.")
    if plan.total_estimated_cost > request.budget:
        raise ValueError("The total estimated cost exceeds the budget.")
    if not math.isclose(
        plan.total_estimated_cost,
        sum(day.estimated_cost for day in plan.days),
        rel_tol=0,
        abs_tol=0.5,
    ):
        raise ValueError("The overall estimated cost must match the sum of daily estimates.")
    if any(day.estimated_cost > request.budget for day in plan.days):
        raise ValueError("A day's estimated cost exceeds the total budget.")
    for day in plan.days:
        if [stop.time for stop in day.stops] != sorted(stop.time for stop in day.stops):
            raise ValueError(f"Stops on day {day.day_number} must be in chronological order.")


def _route_distance_km(first: Any, second: Any) -> float:
    latitude_1, longitude_1 = math.radians(first.latitude), math.radians(first.longitude)
    latitude_2, longitude_2 = math.radians(second.latitude), math.radians(second.longitude)
    latitude_delta = latitude_2 - latitude_1
    longitude_delta = longitude_2 - longitude_1
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_1) * math.cos(latitude_2) * math.sin(longitude_delta / 2) ** 2
    )
    return 6371 * 2 * math.asin(math.sqrt(haversine))


def optimize_day_route(day: ItineraryDay) -> ItineraryDay:
    """Reorder geocoded sightseeing within meal-time anchors; preserve the allocated time slots."""
    stops = list(day.stops)
    anchors = [index for index, stop in enumerate(stops) if stop.kind == "dining"]
    boundaries = [-1, *anchors, len(stops)]
    for start, end in zip(boundaries, boundaries[1:]):
        segment_indices = [
            index
            for index in range(start + 1, end)
            if stops[index].kind != "dining"
            and stops[index].latitude is not None
            and stops[index].longitude is not None
        ]
        if len(segment_indices) < 2:
            continue
        original_stops = list(stops)
        ordered_indices: list[int] = []
        remaining = set(segment_indices)
        current = original_stops[start] if start >= 0 else original_stops[min(remaining)]
        if start < 0:
            remaining.remove(min(remaining))
            ordered_indices.append(min(segment_indices))
        while remaining:
            nearest = min(remaining, key=lambda index: _route_distance_km(current, original_stops[index]))
            ordered_indices.append(nearest)
            remaining.remove(nearest)
            current = original_stops[nearest]
        for target, source in zip(segment_indices, ordered_indices):
            stops[target] = original_stops[source].model_copy(update={"time": day.stops[target].time})
    return day.model_copy(update={"stops": stops})


def _prompt(request: TripInput, refinement: str) -> str:
    interest_text = ", ".join(request.interests)
    return (
        f"Create a day-by-day trip plan for {request.destination} from {request.start_date} "
        f"through {request.end_date} ({request.day_count} days). Total group budget: "
        f"{request.budget:.2f} {request.currency}; group size: {request.group_size}; "
        f"travel style: {request.travel_style.value}; interests: {interest_text}. "
        f"Additional traveler guidance: {refinement or 'None'}."
    )


def generate_plan(
    settings: Settings,
    request: TripInput,
    refinement: str = "",
    existing_plan: ItineraryPlan | None = None,
) -> ItineraryPlan:
    if not settings.groq_api_key:
        raise AIServiceError("AI itinerary generation is not configured.")
    client = Groq(api_key=settings.groq_api_key, max_retries=0, timeout=40.0)
    user_prompt = _prompt(request, refinement)
    if existing_plan is not None:
        user_prompt += (
            "\nRevise this existing itinerary using the new guidance while preserving the original dates and budget. "
            "Existing itinerary JSON:\n" + existing_plan.model_dump_json()
        )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
    for attempt in range(2):
        try:
            completion = client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.4,
                max_tokens=6000,
            )
        except RateLimitError as exc:
            retry_header = exc.response.headers.get("retry-after", "")
            try:
                retry_after = max(1, math.ceil(float(retry_header)))
            except ValueError:
                retry_after = 30
            raise AIServiceError(
                "The AI planner is rate-limited. Please try again shortly.",
                rate_limited=True,
                retry_after=retry_after,
            ) from exc
        except (APIConnectionError, APIStatusError) as exc:
            logger.exception("Groq itinerary request failed")
            if isinstance(exc, APIStatusError) and exc.status_code == 404:
                message = "The configured Groq model is unavailable. Set GROQ_MODEL to an active model and restart the backend."
            elif isinstance(exc, APIStatusError) and exc.status_code == 401:
                message = "Groq rejected the API key. Check GROQ_API_KEY in backend/.env."
            elif isinstance(exc, APIStatusError) and exc.status_code == 400:
                message = "Groq rejected the model request. Check that GROQ_MODEL is active and supports JSON output."
            else:
                message = "The AI planner could not complete this request. Please try again."
            raise AIServiceError(message) from exc
        content = completion.choices[0].message.content or ""
        try:
            plan = ItineraryPlan.model_validate(json.loads(content))
            _validate_plan(plan, request)
            optimized_days = [optimize_day_route(day) for day in plan.days]
            return plan.model_copy(update={"days": optimized_days})
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            if attempt == 1:
                logger.warning("Groq returned invalid itinerary JSON after repair: %s", exc)
                raise AIServiceError("The AI planner returned an invalid itinerary. Please try again.") from exc
            messages.extend(
                [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "Repair the JSON to match the required schema exactly. Correct these validation errors: "
                            f"{exc}. Keep dates, budget, currency, and required dining stops valid. Return JSON only."
                        ),
                    },
                ]
            )
    raise AIServiceError("The AI planner could not complete this request.")


def plan_from_json(value: dict[str, Any]) -> ItineraryPlan:
    return ItineraryPlan.model_validate(value)
