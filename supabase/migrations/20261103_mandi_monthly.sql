-- FarmIntel: shared monthly mandi averages (AGMARKNET district-wise
-- month analysis report).
--
-- These are the published monthly averages pulled by
-- backend/agmarknet_monthly.py and used for district/state price forecasts when
-- the daily feed is thin. Same shape as the local SQLite `mandi_monthly` table
-- so rows push without transformation.
--
-- Write access is service-role only; the browser may read.

create table if not exists public.mandi_monthly (
  id          bigserial primary key,
  state       text    not null,
  district    text    not null,
  commodity   text    not null,
  year        integer not null check (year between 2000 and 2100),
  month       integer not null check (month between 1 and 12),
  price       numeric not null check (price >= 0),
  source      text    not null default 'agmarknet_monthly',
  fetched_at  timestamptz not null default now(),
  unique (state, district, commodity, year, month)
);

create index if not exists mandi_monthly_lookup_idx
  on public.mandi_monthly (commodity, district, year, month);

create index if not exists mandi_monthly_state_idx
  on public.mandi_monthly (state, commodity, year, month);

alter table public.mandi_monthly enable row level security;

drop policy if exists "mandi_monthly_public_read" on public.mandi_monthly;
create policy "mandi_monthly_public_read"
  on public.mandi_monthly for select
  using (true);

grant select on public.mandi_monthly to anon, authenticated;
