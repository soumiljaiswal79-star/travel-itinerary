from typing import Any
from uuid import UUID

from supabase import Client, create_client

from app.config import Settings
from app.models import ItineraryPlan, TripInput, TripResponse


class StoreError(Exception):
    pass


def require_supabase(settings: Settings) -> None:
    if not settings.supabase_url or not settings.supabase_anon_key or not settings.supabase_service_role_key:
        raise StoreError("Supabase is not configured. Set its URL, anon key, and service-role key.")


def auth_client(settings: Settings) -> Client:
    require_supabase(settings)
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def db_client(settings: Settings) -> Client:
    require_supabase(settings)
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def create_trip(
    db: Client, user_id: UUID, request: TripInput, plan: ItineraryPlan
) -> TripResponse:
    trip_data = {
        "user_id": str(user_id),
        "title": plan.title,
        "destination": request.destination,
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "budget": request.budget,
        "currency": request.currency,
        "interests": request.interests,
        "travel_style": request.travel_style.value,
        "group_size": request.group_size,
        "total_estimated_cost": plan.total_estimated_cost,
        "summary": plan.summary,
    }
    result = db.rpc(
        "create_trip_with_days",
        {
            "trip_data": trip_data,
            "days_data": [day.model_dump(mode="json") for day in plan.days],
        },
    ).execute()
    if not result.data:
        raise StoreError("The trip was generated but could not be saved.")
    return get_trip(db, UUID(str(result.data)), user_id)


def list_trips(db: Client, user_id: UUID) -> list[TripResponse]:
    owned = db.table("trips").select("*").eq("user_id", str(user_id)).order("updated_at", desc=True).execute()
    shared = (
        db.table("shared_trip_members")
        .select("trip_id, role, trips(*)")
        .eq("user_id", str(user_id))
        .execute()
    )
    trips: dict[str, TripResponse] = {}
    for row in owned.data:
        trips[row["id"]] = _to_response(db, row, "owner")
    for membership in shared.data:
        trip = membership.get("trips")
        if trip:
            trips[trip["id"]] = _to_response(db, trip, membership["role"])
    return sorted(trips.values(), key=lambda trip: trip.updated_at or "", reverse=True)


def _to_response(db: Client, row: dict[str, Any], role: str) -> TripResponse:
    day_rows = (
        db.table("itinerary_days")
        .select("day_number, date, content")
        .eq("trip_id", row["id"])
        .order("day_number")
        .execute()
    )
    days = [
        {"day_number": item["day_number"], "date": item["date"], **item["content"]}
        for item in day_rows.data
    ]
    return TripResponse(
        **{key: row[key] for key in (
            "id", "user_id", "title", "destination", "start_date", "end_date", "budget",
            "currency", "interests", "travel_style", "group_size", "total_estimated_cost",
            "summary", "created_at", "updated_at",
        )},
        days=days,
        role=role,
    )


def get_trip(db: Client, trip_id: UUID, user_id: UUID) -> TripResponse:
    response = db.table("trips").select("*").eq("id", str(trip_id)).maybe_single().execute()
    row = response.data
    if row is None:
        raise StoreError("Trip not found.")
    role = "owner" if row["user_id"] == str(user_id) else None
    if role is None:
        membership = (
            db.table("shared_trip_members")
            .select("role")
            .eq("trip_id", str(trip_id))
            .eq("user_id", str(user_id))
            .maybe_single()
            .execute()
        )
        if membership.data is None:
            raise StoreError("Trip not found.")
        role = membership.data["role"]
    return _to_response(db, row, role)


def require_editor(trip: TripResponse) -> None:
    if trip.role == "viewer":
        raise StoreError("This shared trip is view-only.")


def update_trip(db: Client, trip: TripResponse, changes: dict[str, Any], user_id: UUID) -> TripResponse:
    if changes:
        if "travel_style" in changes:
            changes["travel_style"] = changes["travel_style"].value
        db.table("trips").update(changes).eq("id", str(trip.id)).execute()
    return get_trip(db, trip.id, user_id)


def save_plan(db: Client, trip: TripResponse, plan: ItineraryPlan, user_id: UUID) -> TripResponse:
    db.rpc(
        "replace_trip_plan",
        {
            "target_trip_id": str(trip.id),
            "plan_data": {
                "title": plan.title,
                "summary": plan.summary,
                "total_estimated_cost": plan.total_estimated_cost,
            },
            "days_data": [day.model_dump(mode="json") for day in plan.days],
        },
    ).execute()
    return get_trip(db, trip.id, user_id)


def save_day(db: Client, trip: TripResponse, day_data: dict[str, Any], user_id: UUID) -> TripResponse:
    day = day_data
    updated_days = [
        item.model_dump(mode="json")
        for item in [*trip.days]
    ]
    updated_days = [item for item in updated_days if item["day_number"] != day["day_number"]]
    updated_days.append(day)
    total = sum(item["estimated_cost"] for item in updated_days)
    db.rpc(
        "save_trip_day",
        {"target_trip_id": str(trip.id), "day_data": day, "new_total_estimated_cost": total},
    ).execute()
    return get_trip(db, trip.id, user_id)


def delete_trip(db: Client, trip_id: UUID) -> None:
    db.table("trips").delete().eq("id", str(trip_id)).execute()


def share_trip(db: Client, trip_id: UUID, email: str, role: str) -> dict[str, Any]:
    user_id = None
    page = 1
    while user_id is None:
        users = db.auth.admin.list_users(page=page, per_page=1000)
        user = next((entry for entry in users if entry.email and entry.email.lower() == email.lower()), None)
        if user is not None:
            user_id = str(user.id)
            break
        if len(users) < 1000:
            break
        page += 1
    if user_id is None:
        raise StoreError("No account exists for that email yet.")
    result = (
        db.table("shared_trip_members")
        .upsert(
            {"trip_id": str(trip_id), "user_id": user_id, "role": role},
            on_conflict="trip_id,user_id",
        )
        .execute()
    )
    return result.data[0]


def remove_member(db: Client, trip_id: UUID, member_id: UUID) -> None:
    db.table("shared_trip_members").delete().eq("trip_id", str(trip_id)).eq("user_id", str(member_id)).execute()


def list_members(db: Client, trip_id: UUID) -> list[dict[str, Any]]:
    response = (
        db.table("shared_trip_members")
        .select("user_id, role, created_at, profiles(email, display_name)")
        .eq("trip_id", str(trip_id))
        .execute()
    )
    return response.data
