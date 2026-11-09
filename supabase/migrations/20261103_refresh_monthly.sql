-- FarmIntel: keep the monthly averages current from the daily rows.
--
-- The daily GitHub Action writes real AGMARKNET observations into
-- public.mandi_prices every morning. Those rows are the source of truth, so the
-- monthly series is derived from them here instead of re-scraping AGMARKNET's
-- monthly report.
--
-- Two guards, mirrored in backend/price_store.monthly_from_daily():
--   * a month only produces a row once it has p_min_days distinct observed days
--     (a 3-day "monthly average" would be an invented number);
--   * an average published by AGMARKNET (source 'agmarknet_monthly') is never
--     overwritten, so imported history stays exactly as it was.
--
-- Called by the daily workflow with the service key:
--   POST /rest/v1/rpc/refresh_monthly_from_daily  {"p_min_days": 10}

create or replace function public.refresh_monthly_from_daily(p_min_days integer default 10)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  touched integer;
begin
  with agg as (
    select state,
           district,
           commodity,
           extract(year  from date)::int as y,
           extract(month from date)::int as m,
           avg(modal_price)             as price,
           count(distinct date)         as days
      from public.mandi_prices
     where modal_price is not null
       and modal_price > 0
       -- current and previous month: the only ones that can still change
       and date >= (date_trunc('month', current_date) - interval '1 month')::date
     group by 1, 2, 3, 4, 5
    having count(distinct date) >= greatest(1, coalesce(p_min_days, 10))
  )
  insert into public.mandi_monthly
    (state, district, commodity, year, month, price, source, fetched_at)
  select state, district, commodity, y, m, round(price, 2), 'derived_daily', now()
    from agg
  on conflict (state, district, commodity, year, month) do update
    set price      = excluded.price,
        source     = excluded.source,
        fetched_at = now()
    -- never replace a real AGMARKNET monthly average with a derived one
    where public.mandi_monthly.source = 'derived_daily';

  get diagnostics touched = row_count;
  return touched;
end;
$$;

-- server-side only: the browser must not be able to recompute the price tables
revoke all on function public.refresh_monthly_from_daily(integer) from public;
revoke all on function public.refresh_monthly_from_daily(integer) from anon, authenticated;
grant execute on function public.refresh_monthly_from_daily(integer) to service_role;
