from datetime import date, time

import pytest
from pydantic import ValidationError

from app.itinerary import _validate_plan, optimize_day_route
from app.models import (
    Accommodation,
    ItineraryDay,
    ItineraryPlan,
    ItineraryStop,
    StopKind,
    TravelStyle,
    TripInput,
)


def stop(title: str, hour: int, longitude: float, kind: StopKind = StopKind.attraction) -> ItineraryStop:
    return ItineraryStop(
        time=time(hour, 0),
        kind=kind,
        title=title,
        description=f"Explore {title} and its surroundings.",
        location=title,
        latitude=0,
        longitude=longitude,
        duration_minutes=60,
        estimated_cost=20,
    )


def test_trip_input_rejects_reversed_dates() -> None:
    with pytest.raises(ValidationError, match="End date must be on or after the start date"):
        TripInput(
            destination="Kyoto",
            start_date=date(2026, 6, 4),
            end_date=date(2026, 6, 3),
            budget=1000,
            interests=["food"],
        )


def test_trip_input_caps_duration_for_reliable_generation() -> None:
    with pytest.raises(ValidationError, match="at most 14 days"):
        TripInput(
            destination="Kyoto",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 16),
            budget=1000,
            interests=["food"],
        )


def test_route_optimization_reorders_nearby_stops_and_keeps_times() -> None:
    day = ItineraryDay(
        day_number=1,
        date=date(2026, 6, 3),
        theme="A day around town",
        stops=[stop("Start", 9, 0), stop("Far stop", 10, 0.02), stop("Nearby stop", 11, 0.001)],
        accommodation=Accommodation(
            name="Town House", neighborhood="Old Town", nightly_cost=120, notes="Quiet and central."
        ),
        transportation=["Walk between stops."],
        estimated_cost=80,
    )

    optimized = optimize_day_route(day)

    assert [item.title for item in optimized.stops] == ["Start", "Nearby stop", "Far stop"]
    assert [item.time for item in optimized.stops] == [time(9), time(10), time(11)]


def test_plan_validation_requires_exact_dates_budget_and_dining() -> None:
    request = TripInput(
        destination="Kyoto",
        start_date=date(2026, 6, 3),
        end_date=date(2026, 6, 3),
        budget=100,
        interests=["food"],
        travel_style=TravelStyle.relaxed,
    )
    plan = ItineraryPlan(
        title="A gentle Kyoto day",
        summary="A relaxed day around Kyoto with time for the things you enjoy.",
        total_estimated_cost=110,
        currency="USD",
        days=[
            ItineraryDay(
                day_number=1,
                date=date(2026, 6, 3),
                theme="Old town and tea",
                stops=[stop("Garden walk", 9, 0), stop("Tea house", 12, 0, StopKind.dining)],
                accommodation=Accommodation(
                    name="Town House",
                    neighborhood="Old Town",
                    nightly_cost=120,
                    notes="A convenient place to rest.",
                ),
                transportation=["Walk"],
                estimated_cost=110,
            )
        ],
    )

    with pytest.raises(ValueError, match="exceeds the budget"):
        _validate_plan(plan, request)
