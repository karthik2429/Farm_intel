-- Marketplace: real farmer listings.
-- Run this file in your Supabase project's SQL editor
-- (Dashboard → SQL Editor → paste → Run), then reload the app.

create table if not exists public.marketplace_listings (
  id uuid primary key default gen_random_uuid(),
  product text not null,
  quantity text not null,
  price numeric(12,2) not null check (price > 0),
  unit text not null default 'kg' check (unit in ('kg', 'quintal')),
  category text not null default 'Other',
  description text,
  district text,
  seller text not null,
  phone text not null,
  created_by uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now()
);

create index if not exists marketplace_listings_recent_idx
  on public.marketplace_listings (created_at desc);

alter table public.marketplace_listings enable row level security;

-- Everyone browsing the app can see listings (recruiters, buyers, farmers)
create policy "listings are publicly readable"
  on public.marketplace_listings
  for select
  to anon, authenticated
  using (true);

-- Only signed-in farmers can post, and the row knows whose listing it is
create policy "signed-in farmers can post their own listings"
  on public.marketplace_listings
  for insert
  to authenticated
  with check ((select auth.uid()) = created_by);
