import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from postgrest.exceptions import APIError
from supabase import AuthApiError, AuthRetryableError
from supabase_auth.types import Session as SupabaseSession
from supabase_auth.types import User as SupabaseUser

from app.config import Settings, get_settings
from app.images import search_image
from app.itinerary import AIServiceError, generate_plan
from app.models import (
    AuthCredentials,
    AuthResponse,
    DayUpdate,
    GenerateTripRequest,
    ItineraryPlan,
    RefreshRequest,
    RegenerateRequest,
    ShareRequest,
    TripResponse,
    TripUpdate,
)
from app.store import (
    StoreError,
    auth_client,
    create_trip,
    db_client,
    delete_trip,
    get_trip,
    list_members,
    list_trips,
    remove_member,
    require_editor,
    save_day,
    save_plan,
    share_trip,
    update_trip,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Wayfarer API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _raise_store_error(exc: StoreError) -> None:
    if exc.args and exc.args[0] == "Trip not found.":
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if exc.args and exc.args[0] == "This shared trip is view-only.":
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if exc.args and exc.args[0] == "No account exists for that email yet.":
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=503, detail=str(exc)) from exc


def current_user(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        response = auth_client(settings).auth.get_user(token)
    except AuthApiError as exc:
        raise HTTPException(status_code=401, detail="Your session expired. Please sign in again.") from exc
    except AuthRetryableError as exc:
        raise HTTPException(status_code=503, detail="Supabase authentication is temporarily unavailable.") from exc
    except StoreError as exc:
        raise HTTPException(status_code=503, detail="Supabase authentication is not configured.") from exc
    if response.user is None:
        raise HTTPException(status_code=401, detail="Your session is invalid. Please sign in again.")
    return {"id": response.user.id, "email": response.user.email}


def _auth_response(user: SupabaseUser, session: SupabaseSession | None) -> AuthResponse:
    return AuthResponse(
        user={"id": user.id, "email": user.email},
        session=session.model_dump(mode="json") if session else None,
    )


User = Annotated[dict, Depends(current_user)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _db(settings: Settings):
    try:
        return db_client(settings)
    except StoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _get_trip(settings: Settings, trip_id: UUID, user: dict) -> TripResponse:
    try:
        return get_trip(_db(settings), trip_id, UUID(str(user["id"])))
    except StoreError as exc:
        _raise_store_error(exc)
    except APIError as exc:
        logger.exception("Trip lookup failed")
        raise HTTPException(status_code=503, detail="This trip could not be loaded.") from exc


def _generate_or_raise(settings: Settings, request: GenerateTripRequest, refinement: str = "",
                       existing: ItineraryPlan | None = None) -> ItineraryPlan:
    try:
        return generate_plan(settings, request, refinement, existing)
    except AIServiceError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.rate_limited else None
        raise HTTPException(
            status_code=429 if exc.rate_limited else 502,
            detail=str(exc),
            headers=headers,
        ) from exc


@app.post("/api/auth/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(credentials: AuthCredentials, settings: SettingsDep) -> AuthResponse:
    try:
        db_client(settings).auth.admin.create_user(
            {
                "email": str(credentials.email),
                "password": credentials.password,
                "email_confirm": True,
            }
        )
        result = auth_client(settings).auth.sign_in_with_password(
            {"email": str(credentials.email), "password": credentials.password}
        )
    except AuthApiError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except AuthRetryableError as exc:
        raise HTTPException(status_code=503, detail="Supabase authentication is temporarily unavailable.") from exc
    except StoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result.user is None or result.session is None:
        raise HTTPException(status_code=502, detail="Supabase did not return an active session.")
    return _auth_response(result.user, result.session)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(credentials: AuthCredentials, settings: SettingsDep) -> AuthResponse:
    try:
        result = auth_client(settings).auth.sign_in_with_password(
            {"email": str(credentials.email), "password": credentials.password}
        )
    except AuthApiError as exc:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.") from exc
    except AuthRetryableError as exc:
        raise HTTPException(status_code=503, detail="Supabase authentication is temporarily unavailable.") from exc
    except StoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result.user is None or result.session is None:
        raise HTTPException(status_code=502, detail="Supabase did not return an active session.")
    return _auth_response(result.user, result.session)


@app.post("/api/auth/refresh", response_model=AuthResponse)
def refresh_session(request: RefreshRequest, settings: SettingsDep) -> AuthResponse:
    try:
        result = auth_client(settings).auth.refresh_session(request.refresh_token)
    except AuthApiError as exc:
        raise HTTPException(status_code=401, detail="Your session expired. Please sign in again.") from exc
    except AuthRetryableError as exc:
        raise HTTPException(status_code=503, detail="Supabase authentication is temporarily unavailable.") from exc
    except StoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result.user is None or result.session is None:
        raise HTTPException(status_code=401, detail="Your session expired. Please sign in again.")
    return _auth_response(result.user, result.session)


@app.get("/api/auth/me")
def me(user: User) -> dict:
    return user


@app.get("/api/images")
async def images(q: str, settings: SettingsDep, user: User) -> Response:
    if not q.strip() or len(q) > 160:
        raise HTTPException(status_code=422, detail="Image search text must be 1-160 characters.")
    image = await search_image(settings, q)
    if image is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    content, media_type = image
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/api/trips", response_model=list[TripResponse])
def trips(settings: SettingsDep, user: User) -> list[TripResponse]:
    try:
        return list_trips(_db(settings), UUID(str(user["id"])))
    except APIError as exc:
        logger.exception("Trip list query failed")
        raise HTTPException(status_code=503, detail="Trips could not be loaded.") from exc


@app.post("/api/trips/generate", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def generate_trip(request: GenerateTripRequest, settings: SettingsDep, user: User) -> TripResponse:
    plan = _generate_or_raise(settings, request, request.refinement)
    try:
        return create_trip(_db(settings), UUID(str(user["id"])), request, plan)
    except APIError as exc:
        logger.exception("Trip creation failed")
        raise HTTPException(status_code=503, detail="The itinerary was generated but could not be saved.") from exc
    except StoreError as exc:
        _raise_store_error(exc)


@app.get("/api/trips/{trip_id}", response_model=TripResponse)
def trip_detail(trip_id: UUID, settings: SettingsDep, user: User) -> TripResponse:
    return _get_trip(settings, trip_id, user)


@app.patch("/api/trips/{trip_id}", response_model=TripResponse)
def edit_trip(trip_id: UUID, changes: TripUpdate, settings: SettingsDep, user: User) -> TripResponse:
    trip = _get_trip(settings, trip_id, user)
    try:
        require_editor(trip)
        update_data = changes.model_dump(exclude_unset=True, exclude_none=True)
        if update_data.get("budget", trip.budget) < trip.total_estimated_cost:
            raise HTTPException(
                status_code=422,
                detail="The budget cannot be lower than the current itinerary estimate.",
            )
        return update_trip(_db(settings), trip, update_data, UUID(str(user["id"])))
    except StoreError as exc:
        _raise_store_error(exc)
    except APIError as exc:
        logger.exception("Trip update failed")
        raise HTTPException(status_code=503, detail="Trip details could not be saved.") from exc


def _as_input(trip: TripResponse) -> GenerateTripRequest:
    return GenerateTripRequest(
        destination=trip.destination,
        start_date=trip.start_date,
        end_date=trip.end_date,
        budget=trip.budget,
        currency=trip.currency,
        interests=trip.interests,
        travel_style=trip.travel_style,
        group_size=trip.group_size,
    )


@app.post("/api/trips/{trip_id}/regenerate", response_model=TripResponse)
def regenerate_trip(
    trip_id: UUID,
    request: RegenerateRequest,
    settings: SettingsDep,
    user: User,
) -> TripResponse:
    trip = _get_trip(settings, trip_id, user)
    try:
        require_editor(trip)
    except StoreError as exc:
        _raise_store_error(exc)
    existing = ItineraryPlan(
        title=trip.title,
        summary=trip.summary,
        total_estimated_cost=trip.total_estimated_cost,
        currency=trip.currency,
        days=trip.days,
    )
    plan = _generate_or_raise(settings, _as_input(trip), request.refinement, existing)
    try:
        return save_plan(_db(settings), trip, plan, UUID(str(user["id"])))
    except APIError as exc:
        logger.exception("Trip regeneration save failed")
        raise HTTPException(status_code=503, detail="The itinerary was regenerated but could not be saved.") from exc


@app.post("/api/trips/{trip_id}/days/{day_number}/regenerate", response_model=TripResponse)
def regenerate_day(
    trip_id: UUID,
    day_number: int,
    request: RegenerateRequest,
    settings: SettingsDep,
    user: User,
) -> TripResponse:
    trip = _get_trip(settings, trip_id, user)
    try:
        require_editor(trip)
    except StoreError as exc:
        _raise_store_error(exc)
    if day_number < 1 or day_number > len(trip.days):
        raise HTTPException(status_code=404, detail="Itinerary day not found.")
    day = trip.days[day_number - 1]
    remaining_budget = trip.budget - (trip.total_estimated_cost - day.estimated_cost)
    if remaining_budget <= 0:
        raise HTTPException(
            status_code=422,
            detail="There is no remaining budget for a new plan for this day.",
        )
    day_input = GenerateTripRequest(
        destination=trip.destination,
        start_date=day.date,
        end_date=day.date,
        budget=remaining_budget,
        currency=trip.currency,
        interests=trip.interests,
        travel_style=trip.travel_style,
        group_size=trip.group_size,
        refinement=f"Focus only on this trip day. {request.refinement}",
    )
    single_day = _generate_or_raise(settings, day_input, day_input.refinement)
    replacement = single_day.days[0].model_copy(update={"day_number": day_number})
    plan = ItineraryPlan(
        title=trip.title,
        summary=trip.summary,
        total_estimated_cost=trip.total_estimated_cost - day.estimated_cost + replacement.estimated_cost,
        currency=trip.currency,
        days=[replacement if item.day_number == day_number else item for item in trip.days],
    )
    try:
        return save_plan(_db(settings), trip, plan, UUID(str(user["id"])))
    except APIError as exc:
        logger.exception("Day regeneration save failed")
        raise HTTPException(status_code=503, detail="The day was regenerated but could not be saved.") from exc


@app.put("/api/trips/{trip_id}/days/{day_number}", response_model=TripResponse)
def edit_day(
    trip_id: UUID,
    day_number: int,
    request: DayUpdate,
    settings: SettingsDep,
    user: User,
) -> TripResponse:
    trip = _get_trip(settings, trip_id, user)
    try:
        require_editor(trip)
    except StoreError as exc:
        _raise_store_error(exc)
    if request.day.day_number != day_number or day_number > len(trip.days):
        raise HTTPException(status_code=422, detail="The submitted day number does not match this itinerary day.")
    if request.day.date != trip.days[day_number - 1].date:
        raise HTTPException(status_code=422, detail="An edited day must keep its original travel date.")
    updated_total = trip.total_estimated_cost - trip.days[day_number - 1].estimated_cost + request.day.estimated_cost
    if updated_total > trip.budget:
        raise HTTPException(status_code=422, detail="The edited day would exceed the trip budget.")
    try:
        return save_day(_db(settings), trip, request.day.model_dump(mode="json"), UUID(str(user["id"])))
    except APIError as exc:
        logger.exception("Day edit failed")
        raise HTTPException(status_code=503, detail="The itinerary day could not be saved.") from exc


@app.delete("/api/trips/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_trip(trip_id: UUID, settings: SettingsDep, user: User) -> Response:
    trip = _get_trip(settings, trip_id, user)
    try:
        require_editor(trip)
        if trip.role != "owner":
            raise HTTPException(status_code=403, detail="Only the trip owner can delete a trip.")
        delete_trip(_db(settings), trip_id)
    except StoreError as exc:
        _raise_store_error(exc)
    except APIError as exc:
        logger.exception("Trip deletion failed")
        raise HTTPException(status_code=503, detail="The trip could not be deleted.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/trips/{trip_id}/members")
def members(trip_id: UUID, settings: SettingsDep, user: User) -> list[dict]:
    _get_trip(settings, trip_id, user)
    try:
        return list_members(_db(settings), trip_id)
    except APIError as exc:
        logger.exception("Trip members query failed")
        raise HTTPException(status_code=503, detail="Trip members could not be loaded.") from exc


@app.post("/api/trips/{trip_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(
    trip_id: UUID,
    request: ShareRequest,
    settings: SettingsDep,
    user: User,
) -> dict:
    trip = _get_trip(settings, trip_id, user)
    if trip.role != "owner":
        raise HTTPException(status_code=403, detail="Only the trip owner can invite collaborators.")
    try:
        return share_trip(_db(settings), trip_id, str(request.email), request.role)
    except StoreError as exc:
        _raise_store_error(exc)
    except APIError as exc:
        logger.exception("Trip sharing failed")
        raise HTTPException(status_code=503, detail="The collaborator could not be added.") from exc


@app.delete("/api/trips/{trip_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_trip_member(
    trip_id: UUID,
    member_id: UUID,
    settings: SettingsDep,
    user: User,
) -> Response:
    trip = _get_trip(settings, trip_id, user)
    if trip.role != "owner":
        raise HTTPException(status_code=403, detail="Only the trip owner can remove collaborators.")
    try:
        remove_member(_db(settings), trip_id, member_id)
    except APIError as exc:
        logger.exception("Trip member removal failed")
        raise HTTPException(status_code=503, detail="The collaborator could not be removed.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
