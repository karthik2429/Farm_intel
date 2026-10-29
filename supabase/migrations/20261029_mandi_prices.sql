-- FarmIntel Phase 1: shared mandi price history in Supabase.
--
-- The daily GitHub Action ingests the AGMARKNET "Current Daily Price"
-- snapshot from api.data.gov.in and upserts it here with the service-role
-- key. Every machine's local SQLite backend store stays the fast read
-- cache; this table is the durable, shared record so real history keeps
-- accruing even when a dev machine is offline.

create table if not exists public.mandi_prices (
  id           bigserial primary key,
  date         date         not null,
  state        text         not null,
  district     text         not null,
  market       text         not null,
  commodity    text         not null,
  variety      text,
  min_price    numeric,
  max_price    numeric,
  modal_price  numeric      not null,
  source       text         not null default 'agmarknet_live',
  fetched_at   timestamptz  not null default now(),
  unique (date, state, district, market, commodity, variety)
);

create index if not exists mandi_prices_date_idx on public.mandi_prices (date);
create index if not exists mandi_prices_lookup_idx
  on public.mandi_prices (commodity, district, date);

alter table public.mandi_prices enable row level security;

-- Anyone signed in (or anon, for public price display) may read.
drop policy if exists "mandi_prices_public_read" on public.mandi_prices;
create policy "mandi_prices_public_read"
  on public.mandi_prices for select
  using (true);

-- No anon/authenticated write policies: only the service role
-- (daily ingest job, bypasses RLS) may insert or update.

grant select on public.mandi_prices to anon, authenticated;
