-- =============================================================================
-- AgroSmart AI — profiles, personalisation and per-user data (Phase 2)
--
-- Paste this whole file into the Supabase SQL editor (or `supabase db push`).
-- Every table is protected by Row Level Security: a signed-in user can only
-- read and write rows where the row id is their own auth.uid().
-- =============================================================================

-- ---------------------------------------------------------------- profiles ---
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  name text,
  email text,
  phone text,
  language text not null default 'en'
    check (language in ('en','hi','kn','te','ta','ml','mr','gu','bn','pa','or')),
  state text,
  district text,
  village text,
  lat double precision,
  lng double precision,
  land_size numeric,
  land_unit text default 'acres',
  irrigation text,
  farming_type text,
  season_focus text,
  onboarding_complete boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
  for select using (auth.uid() = id);

drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own" on public.profiles
  for insert with check (auth.uid() = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists "profiles_delete_own" on public.profiles;
create policy "profiles_delete_own" on public.profiles
  for delete using (auth.uid() = id);

-- Auto-create a profile row the first time someone signs up, so the client can
-- always upsert into an existing row.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, name, email)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', ''),
    new.email
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- keep updated_at fresh
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at
  before update on public.profiles
  for each row execute function public.touch_updated_at();

-- --------------------------------------------------------------- user_crops ---
create table if not exists public.user_crops (
  user_id uuid not null references auth.users(id) on delete cascade,
  crop text not null,
  is_primary boolean not null default false,
  created_at timestamptz not null default now(),
  primary key (user_id, crop)
);

alter table public.user_crops enable row level security;

drop policy if exists "user_crops_all_own" on public.user_crops;
create policy "user_crops_all_own" on public.user_crops
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create index if not exists user_crops_user_idx on public.user_crops (user_id);

-- ------------------------------------------------------ soil_health_cards ---
create table if not exists public.soil_health_cards (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  n numeric,
  p numeric,
  k numeric,
  ph numeric,
  ec numeric,
  oc numeric,
  file_url text,
  test_date date,
  created_at timestamptz not null default now()
);

alter table public.soil_health_cards enable row level security;

drop policy if exists "soil_cards_all_own" on public.soil_health_cards;
create policy "soil_cards_all_own" on public.soil_health_cards
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create index if not exists soil_cards_user_idx on public.soil_health_cards (user_id);

-- ------------------------------------------------------------ price_alerts ---
create table if not exists public.price_alerts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  crop text not null,
  market text,
  target_price numeric not null,
  direction text not null default 'above' check (direction in ('above','below')),
  active boolean not null default true,
  created_at timestamptz not null default now()
);

alter table public.price_alerts enable row level security;

drop policy if exists "price_alerts_all_own" on public.price_alerts;
create policy "price_alerts_all_own" on public.price_alerts
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create index if not exists price_alerts_user_idx on public.price_alerts (user_id);

-- ------------------------------------------------------------ chat_history ---
create table if not exists public.chat_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('user','assistant','system')),
  content text not null,
  lang text not null default 'en',
  created_at timestamptz not null default now()
);

alter table public.chat_history enable row level security;

drop policy if exists "chat_history_all_own" on public.chat_history;
create policy "chat_history_all_own" on public.chat_history
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create index if not exists chat_history_user_idx
  on public.chat_history (user_id, created_at desc);

-- ------------------------------------------------------------- saved_queries --
create table if not exists public.saved_queries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  label text not null,
  query jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.saved_queries enable row level security;

drop policy if exists "saved_queries_all_own" on public.saved_queries;
create policy "saved_queries_all_own" on public.saved_queries
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ------------------------------------------------------------- marketplace ---
-- Marketplace is not part of the product any more. Drop the table if an older
-- migration created it (safe to re-run).
drop table if exists public.marketplace_listings cascade;

-- -------------------------------------------------------- storage: soil cards --
insert into storage.buckets (id, name, public)
values ('soil-cards', 'soil-cards', false)
on conflict (id) do nothing;

drop policy if exists "soil_cards_read_own" on storage.objects;
create policy "soil_cards_read_own" on storage.objects
  for select using (
    bucket_id = 'soil-cards'
    and auth.uid()::text = (storage.foldername(name))[1]
  );

drop policy if exists "soil_cards_write_own" on storage.objects;
create policy "soil_cards_write_own" on storage.objects
  for insert with check (
    bucket_id = 'soil-cards'
    and auth.uid()::text = (storage.foldername(name))[1]
  );

drop policy if exists "soil_cards_update_own" on storage.objects;
create policy "soil_cards_update_own" on storage.objects
  for update using (
    bucket_id = 'soil-cards'
    and auth.uid()::text = (storage.foldername(name))[1]
  );

drop policy if exists "soil_cards_delete_own" on storage.objects;
create policy "soil_cards_delete_own" on storage.objects
  for delete using (
    bucket_id = 'soil-cards'
    and auth.uid()::text = (storage.foldername(name))[1]
  );
