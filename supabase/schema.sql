create extension if not exists pgcrypto;

create table public.watchlists (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null default 'My watchlist',
  created_at timestamptz not null default now()
);

create table public.watchlist_items (
  id uuid primary key default gen_random_uuid(),
  watchlist_id uuid not null references public.watchlists(id) on delete cascade,
  symbol text not null,
  company_name text not null,
  sector_index text not null,
  created_at timestamptz not null default now(),
  unique (watchlist_id, symbol)
);

create table public.review_watermarks (
  watchlist_id uuid primary key references public.watchlists(id) on delete cascade,
  reviewed_through timestamptz not null,
  version integer not null default 1,
  updated_at timestamptz not null default now()
);

create table public.personal_rules (
  id uuid primary key default gen_random_uuid(),
  watchlist_item_id uuid not null references public.watchlist_items(id) on delete cascade,
  rule_type text not null check (rule_type in ('price_above', 'price_below', 'volume_pace')),
  threshold numeric not null,
  armed boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.market_candles (
  symbol text not null,
  interval_start timestamptz not null,
  interval text not null default '1m',
  open numeric not null,
  high numeric not null,
  low numeric not null,
  close numeric not null,
  volume bigint not null check (volume >= 0),
  source text not null,
  received_at timestamptz not null default now(),
  primary key (symbol, interval_start, interval)
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
  horizon_minutes integer not null,
  distribution_type text not null,
  sector_index_used text,
  percentile_breakpoints jsonb not null,
  observation_count integer not null,
  computed_at timestamptz not null,
  primary key (symbol, horizon_minutes, distribution_type)
);

create table public.path_events (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  event_type text not null,
  occurred_at timestamptz not null,
  magnitude numeric not null,
  percentile numeric not null check (percentile between 0 and 100),
  confirmed_from_fresh_data boolean not null default true,
  evidence jsonb not null default '{}'::jsonb
);

create table public.corporate_actions (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  ex_date date not null,
  action_type text not null,
  adjustment_factor numeric,
  notes text,
  unique (symbol, ex_date, action_type)
);

create index watchlist_items_watchlist_idx on public.watchlist_items(watchlist_id);
create index market_candles_symbol_time_idx on public.market_candles(symbol, interval_start desc);
create index path_events_symbol_time_idx on public.path_events(symbol, occurred_at desc);

create or replace function public.acknowledge_watchlist(
  target_watchlist_id uuid,
  acknowledged_through timestamptz
) returns timestamptz
language plpgsql
security invoker
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

create policy "owners manage watchlists" on public.watchlists
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

create policy "owners manage watchlist items" on public.watchlist_items
  using (exists (select 1 from public.watchlists w where w.id = watchlist_id and w.owner_id = auth.uid()))
  with check (exists (select 1 from public.watchlists w where w.id = watchlist_id and w.owner_id = auth.uid()));

create policy "owners manage review watermarks" on public.review_watermarks
  using (exists (select 1 from public.watchlists w where w.id = watchlist_id and w.owner_id = auth.uid()))
  with check (exists (select 1 from public.watchlists w where w.id = watchlist_id and w.owner_id = auth.uid()));

create policy "owners manage personal rules" on public.personal_rules
  using (exists (
    select 1 from public.watchlist_items wi
    join public.watchlists w on w.id = wi.watchlist_id
    where wi.id = watchlist_item_id and w.owner_id = auth.uid()
  ))
  with check (exists (
    select 1 from public.watchlist_items wi
    join public.watchlists w on w.id = wi.watchlist_id
    where wi.id = watchlist_item_id and w.owner_id = auth.uid()
  ));
