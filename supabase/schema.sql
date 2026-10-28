create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null unique,
  display_name text,
  created_at timestamptz not null default now()
);

create table if not exists public.trips (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  destination text not null,
  start_date date not null,
  end_date date not null,
  budget numeric(12, 2) not null check (budget > 0),
  currency char(3) not null default 'USD',
  interests text[] not null default '{}',
  travel_style text not null check (travel_style in ('relaxed', 'balanced', 'packed')),
  group_size integer not null check (group_size between 1 and 30),
  total_estimated_cost numeric(12, 2) not null default 0,
  summary text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (end_date >= start_date)
);

create table if not exists public.itinerary_days (
  trip_id uuid not null references public.trips(id) on delete cascade,
  day_number integer not null check (day_number > 0),
  date date not null,
  content jsonb not null,
  primary key (trip_id, day_number),
  unique (trip_id, date)
);

create table if not exists public.shared_trip_members (
  trip_id uuid not null references public.trips(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  role text not null check (role in ('editor', 'viewer')),
  created_at timestamptz not null default now(),
  primary key (trip_id, user_id)
);

create index if not exists trips_user_updated_idx on public.trips (user_id, updated_at desc);
create index if not exists shared_trip_members_user_idx on public.shared_trip_members (user_id);

create or replace function public.touch_trip_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function public.is_trip_owner(target_trip_id uuid)
returns boolean language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.trips as trip
    where trip.id = target_trip_id and trip.user_id = (select auth.uid())
  )
$$;

create or replace function public.is_trip_member(target_trip_id uuid)
returns boolean language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.shared_trip_members as member
    where member.trip_id = target_trip_id and member.user_id = (select auth.uid())
  )
$$;

create or replace function public.can_edit_trip(target_trip_id uuid)
returns boolean language sql stable security definer set search_path = ''
as $$
  select public.is_trip_owner(target_trip_id)
    or exists (
      select 1 from public.shared_trip_members as member
      where member.trip_id = target_trip_id
        and member.user_id = (select auth.uid())
        and member.role = 'editor'
    )
$$;

revoke all on function public.is_trip_owner(uuid) from public, anon;
revoke all on function public.is_trip_member(uuid) from public, anon;
revoke all on function public.can_edit_trip(uuid) from public, anon;
grant execute on function public.is_trip_owner(uuid) to authenticated, service_role;
grant execute on function public.is_trip_member(uuid) to authenticated, service_role;
grant execute on function public.can_edit_trip(uuid) to authenticated, service_role;

drop trigger if exists trips_touch_updated_at on public.trips;
create trigger trips_touch_updated_at before update on public.trips
for each row execute function public.touch_trip_updated_at();

create or replace function public.prevent_trip_owner_change()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  if new.user_id <> old.user_id then
    raise exception 'Trip owner cannot be changed';
  end if;
  return new;
end;
$$;

drop trigger if exists trips_prevent_owner_change on public.trips;
create trigger trips_prevent_owner_change before update of user_id on public.trips
for each row execute function public.prevent_trip_owner_change();

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  insert into public.profiles (id, email, display_name)
  values (
    new.id,
    lower(new.email),
    coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1))
  )
  on conflict (id) do update set email = excluded.email;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert or update of email on auth.users
for each row execute function public.handle_new_user();

insert into public.profiles (id, email, display_name)
select
  users.id,
  lower(users.email),
  coalesce(users.raw_user_meta_data ->> 'display_name', split_part(users.email, '@', 1))
from auth.users as users
where users.email is not null
on conflict (id) do update set email = excluded.email;

create or replace function public.create_trip_with_days(trip_data jsonb, days_data jsonb)
returns uuid language plpgsql security definer set search_path = ''
as $$
declare
  new_trip_id uuid;
  day_entry jsonb;
begin
  insert into public.trips (
    user_id, title, destination, start_date, end_date, budget, currency, interests,
    travel_style, group_size, total_estimated_cost, summary
  ) values (
    (trip_data ->> 'user_id')::uuid,
    trip_data ->> 'title',
    trip_data ->> 'destination',
    (trip_data ->> 'start_date')::date,
    (trip_data ->> 'end_date')::date,
    (trip_data ->> 'budget')::numeric,
    trip_data ->> 'currency',
    array(select jsonb_array_elements_text(trip_data -> 'interests')),
    trip_data ->> 'travel_style',
    (trip_data ->> 'group_size')::integer,
    (trip_data ->> 'total_estimated_cost')::numeric,
    trip_data ->> 'summary'
  ) returning id into new_trip_id;

  for day_entry in select value from jsonb_array_elements(days_data)
  loop
    insert into public.itinerary_days (trip_id, day_number, date, content)
    values (
      new_trip_id,
      (day_entry ->> 'day_number')::integer,
      (day_entry ->> 'date')::date,
      day_entry - 'day_number' - 'date'
    );
  end loop;
  return new_trip_id;
end;
$$;

create or replace function public.replace_trip_plan(
  target_trip_id uuid,
  plan_data jsonb,
  days_data jsonb
)
returns void language plpgsql security definer set search_path = ''
as $$
declare
  day_entry jsonb;
begin
  update public.trips
  set title = plan_data ->> 'title',
      summary = plan_data ->> 'summary',
      total_estimated_cost = (plan_data ->> 'total_estimated_cost')::numeric
  where id = target_trip_id;
  if not found then
    raise exception 'Trip not found';
  end if;

  for day_entry in select value from jsonb_array_elements(days_data)
  loop
    insert into public.itinerary_days (trip_id, day_number, date, content)
    values (
      target_trip_id,
      (day_entry ->> 'day_number')::integer,
      (day_entry ->> 'date')::date,
      day_entry - 'day_number' - 'date'
    )
    on conflict (trip_id, day_number) do update
    set date = excluded.date, content = excluded.content;
  end loop;
end;
$$;

create or replace function public.save_trip_day(
  target_trip_id uuid,
  day_data jsonb,
  new_total_estimated_cost numeric
)
returns void language plpgsql security definer set search_path = ''
as $$
begin
  insert into public.itinerary_days (trip_id, day_number, date, content)
  values (
    target_trip_id,
    (day_data ->> 'day_number')::integer,
    (day_data ->> 'date')::date,
    day_data - 'day_number' - 'date'
  )
  on conflict (trip_id, day_number) do update
  set date = excluded.date, content = excluded.content;
  update public.trips
  set total_estimated_cost = new_total_estimated_cost
  where id = target_trip_id;
end;
$$;

revoke all on function public.create_trip_with_days(jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.create_trip_with_days(jsonb, jsonb) to service_role;
revoke all on function public.replace_trip_plan(uuid, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.replace_trip_plan(uuid, jsonb, jsonb) to service_role;
revoke all on function public.save_trip_day(uuid, jsonb, numeric) from public, anon, authenticated;
grant execute on function public.save_trip_day(uuid, jsonb, numeric) to service_role;

alter table public.profiles enable row level security;
alter table public.trips enable row level security;
alter table public.itinerary_days enable row level security;
alter table public.shared_trip_members enable row level security;

drop policy if exists "Profiles can be read by their owner" on public.profiles;
create policy "Profiles can be read by their owner"
on public.profiles for select to authenticated
using (id = (select auth.uid()));
drop policy if exists "Owners and shared members can read trips" on public.trips;
create policy "Owners and shared members can read trips"
on public.trips for select to authenticated
using (user_id = (select auth.uid()) or public.is_trip_member(id));
drop policy if exists "Owners and editors can update trips" on public.trips;
create policy "Owners and editors can update trips"
on public.trips for update to authenticated
using (public.can_edit_trip(id))
with check (public.can_edit_trip(id));
drop policy if exists "Owners can create trips" on public.trips;
create policy "Owners can create trips"
on public.trips for insert to authenticated
with check (user_id = (select auth.uid()));
drop policy if exists "Owners can delete trips" on public.trips;
create policy "Owners can delete trips"
on public.trips for delete to authenticated
using (user_id = (select auth.uid()));

drop policy if exists "Trip members can read itinerary days" on public.itinerary_days;
create policy "Trip members can read itinerary days"
on public.itinerary_days for select to authenticated
using (public.is_trip_owner(trip_id) or public.is_trip_member(trip_id));
drop policy if exists "Owners and editors can change itinerary days" on public.itinerary_days;
create policy "Owners and editors can change itinerary days"
on public.itinerary_days for all to authenticated
using (public.can_edit_trip(trip_id))
with check (public.can_edit_trip(trip_id));

drop policy if exists "Members can see trip membership" on public.shared_trip_members;
create policy "Members can see trip membership"
on public.shared_trip_members for select to authenticated
using (user_id = (select auth.uid()) or public.is_trip_owner(trip_id));
drop policy if exists "Owners can manage trip membership" on public.shared_trip_members;
create policy "Owners can manage trip membership"
on public.shared_trip_members for all to authenticated
using (public.is_trip_owner(trip_id))
with check (public.is_trip_owner(trip_id));

grant usage on schema public to authenticated, service_role;
grant select on public.profiles to authenticated;
grant select, insert, update, delete on public.trips to authenticated;
grant select, insert, update, delete on public.itinerary_days to authenticated;
grant select, insert, update, delete on public.shared_trip_members to authenticated;
grant all on public.profiles, public.trips, public.itinerary_days, public.shared_trip_members to service_role;
