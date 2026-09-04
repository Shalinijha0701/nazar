create extension if not exists pgcrypto;

create table public.watchlists (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 80),
  created_at timestamptz not null default now()
);

create table public.watchlist_items (
  id uuid primary key default gen_random_uuid(),
  watchlist_id uuid not null references public.watchlists(id) on delete cascade,
  symbol text not null check (symbol = upper(symbol)),
  company_name text not null,
  sector_index text not null,
  created_at timestamptz not null default now(),
  unique (watchlist_id, symbol)
);

create table public.review_watermarks (
  watchlist_id uuid primary key references public.watchlists(id) on delete cascade,
  reviewed_through timestamptz not null,
  version integer not null default 1 check (version > 0),
  updated_at timestamptz not null default now()
);

create table public.personal_rules (
  id uuid primary key default gen_random_uuid(),
  watchlist_item_id uuid not null references public.watchlist_items(id) on delete cascade,
  rule_type text not null check (rule_type in ('price_above', 'price_below', 'volume_pace')),
  threshold numeric not null check (threshold > 0),
  armed boolean not null default true,
  created_at timestamptz not null default now(),
  unique (watchlist_item_id, rule_type, threshold)
);

create table public.market_candles (
  symbol text not null,
  interval_start timestamptz not null,
  interval text not null default '1m' check (interval in ('1m', '5m', '15m', '30m', '1d')),
  open numeric not null check (open > 0),
  high numeric not null check (high > 0),
  low numeric not null check (low > 0),
  close numeric not null check (close > 0),
  volume bigint not null check (volume >= 0),
  source text not null,
  received_at timestamptz not null default now(),
  primary key (symbol, interval_start, interval),
  check (high >= greatest(open, low, close)),
  check (low <= least(open, high, close))
);

create table public.market_timeline (
  interval_start timestamptz primary key,
  nifty50 numeric,
  nifty_it numeric,
  nifty_bank numeric,
  nifty_pharma numeric,
  nifty_fmcg numeric,
  nifty_auto numeric,
  source text not null,
  received_at timestamptz not null default now()
);

create table public.stock_distributions (
  symbol text not null,
  horizon_minutes integer not null check (horizon_minutes in (15, 60, 240, 375, 750, 1875)),
  distribution_type text not null,
  sector_index_used text,
  percentile_breakpoints jsonb not null,
  observation_count integer not null check (observation_count >= 0),
  lookback_start timestamptz,
  lookback_end timestamptz,
  session_offset_minutes integer,
  method_version text not null default 'v1',
  adjustment_version text,
  computed_at timestamptz not null default now(),
  primary key (symbol, horizon_minutes, distribution_type)
);

create table public.path_events (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  event_type text not null check (event_type in ('upward_excursion', 'downward_excursion', 'peak_to_trough', 'trough_to_peak')),
  occurred_at timestamptz not null,
  magnitude numeric not null check (magnitude >= 0),
  percentile numeric not null check (percentile between 0 and 100),
  confirmed_from_fresh_data boolean not null default true,
  evidence jsonb not null default '{}'::jsonb
);

create table public.corporate_actions (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  ex_date date not null,
  action_type text not null check (action_type in ('split', 'bonus', 'dividend', 'rights', 'merger', 'demerger', 'symbol_change')),
  adjustment_factor numeric check (adjustment_factor is null or adjustment_factor > 0),
  notes text,
  unique (symbol, ex_date, action_type)
);

create index watchlists_owner_idx on public.watchlists(owner_id);
create index watchlist_items_watchlist_idx on public.watchlist_items(watchlist_id);
create index personal_rules_item_idx on public.personal_rules(watchlist_item_id) where armed;
create index market_candles_symbol_time_idx on public.market_candles(symbol, interval_start desc);
create index path_events_symbol_time_idx on public.path_events(symbol, occurred_at desc);
create index corporate_actions_symbol_date_idx on public.corporate_actions(symbol, ex_date desc);

create or replace function public.acknowledge_watchlist(
  target_watchlist_id uuid,
  acknowledged_through timestamptz
) returns timestamptz
language plpgsql
security invoker
set search_path = ''
as $$
declare
  final_watermark timestamptz;
begin
  insert into public.review_watermarks (watchlist_id, reviewed_through)
  values (target_watchlist_id, acknowledged_through)
  on conflict (watchlist_id) do update
    set reviewed_through = greatest(
      public.review_watermarks.reviewed_through,
      excluded.reviewed_through
    ),
    version = public.review_watermarks.version + 1,
    updated_at = now()
  returning reviewed_through into final_watermark;

  return final_watermark;
end;
$$;

alter table public.watchlists enable row level security;
alter table public.watchlist_items enable row level security;
alter table public.review_watermarks enable row level security;
alter table public.personal_rules enable row level security;
alter table public.market_candles enable row level security;
alter table public.market_timeline enable row level security;
alter table public.stock_distributions enable row level security;
alter table public.path_events enable row level security;
alter table public.corporate_actions enable row level security;

create policy "owners manage watchlists" on public.watchlists
  for all to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy "owners manage watchlist items" on public.watchlist_items
  for all to authenticated
  using (exists (
    select 1 from public.watchlists w
    where w.id = watchlist_id and w.owner_id = (select auth.uid())
  ))
  with check (exists (
    select 1 from public.watchlists w
    where w.id = watchlist_id and w.owner_id = (select auth.uid())
  ));

create policy "owners manage review watermarks" on public.review_watermarks
  for all to authenticated
  using (exists (
    select 1 from public.watchlists w
    where w.id = watchlist_id and w.owner_id = (select auth.uid())
  ))
  with check (exists (
    select 1 from public.watchlists w
    where w.id = watchlist_id and w.owner_id = (select auth.uid())
  ));

create policy "owners manage personal rules" on public.personal_rules
  for all to authenticated
  using (exists (
    select 1
    from public.watchlist_items wi
    join public.watchlists w on w.id = wi.watchlist_id
    where wi.id = watchlist_item_id and w.owner_id = (select auth.uid())
  ))
  with check (exists (
    select 1
    from public.watchlist_items wi
    join public.watchlists w on w.id = wi.watchlist_id
    where wi.id = watchlist_item_id and w.owner_id = (select auth.uid())
  ));

revoke all on public.market_candles from anon, authenticated;
revoke all on public.market_timeline from anon, authenticated;
revoke all on public.stock_distributions from anon, authenticated;
revoke all on public.path_events from anon, authenticated;
revoke all on public.corporate_actions from anon, authenticated;

revoke execute on function public.acknowledge_watchlist(uuid, timestamptz) from public, anon;
grant execute on function public.acknowledge_watchlist(uuid, timestamptz) to authenticated, service_role;
