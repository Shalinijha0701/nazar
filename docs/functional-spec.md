# Nazar signal specification

Nazar answers three independent questions for the interval between a user's
`reviewed_through` watermark and an evaluation cutoff. It never merges the
answers into a weighted score.

## Shared definitions

- `t0`: the user's `reviewed_through` timestamp.
- `t1`: the latest timestamp for which both the stock and its sector have a
  fresh, complete candle.
- `h`: completed exchange trading minutes between `t0` and `t1`. Weekends,
  holidays, and closed-session minutes do not count.
- Supported horizon buckets are 15, 60, 240, 375, 750, and 1,875 trading
  minutes.

### Horizon selection

Use the smallest supported bucket greater than or equal to `h`. This ceiling
rule is deliberately conservative: a move observed over a shorter interval is
compared with a distribution that had at least as much time to move. If
`h < 15`, statistical signals are withheld. If `h > 1,875`, statistical
signals cover the trailing five sessions and the response is labelled
`partial_coverage`; personal rules still inspect the full available interval.

Historical observations use the same trading-time horizon and pool valid
session-start offsets. At least 120 observations are required; 252 is
preferred. Rolling windows may overlap in the MVP, so the percentile is
descriptive rather than an independent-sample probability.

## 1. Personal rule

### Price rule

For a `crosses_above` rule with threshold `q`, trigger when the last fresh
price before `t0` is below `q` and any fresh candle high in `(t0, t1]` is at
least `q`. `crosses_below` is symmetric and uses candle lows. A triggered rule
records the first matching minute and is not emitted again until acknowledged
and re-armed on the opposite side.

### Volume-pace rule

For minute `m`, let `V(m)` be cumulative session volume and let `M(m)` be the
median cumulative volume at the same session minute over the previous 20 valid
sessions. `pace(m) = V(m) / M(m)`. Trigger when pace crosses the user's chosen
multiple from below. If `M(m)` is zero or fewer than 20 sessions exist, the
rule is unavailable rather than guessed.

## 2. Sector surprise

For horizon `b`:

```
x_now = stock_return(t0,t1) - sector_return(t0,t1)
median_x = median(x_1 ... x_N)
d_now = abs(x_now - median_x)
d_j = abs(x_j - median_x)
percentile = 100 * count(d_j <= d_now) / N
```

Trigger when `percentile >= 95`. Direction is `above_sector` when
`x_now - median_x > 0`, otherwise `below_sector`. The UI always shows `N` and
the lookback dates. The percentile describes rarity, not a forecast.

## 3. Path event

Using minute OHLC candles and baseline price `p0`:

- Upward excursion: `max(high / p0 - 1)`.
- Downward excursion: `max(1 - low / p0)`.
- Peak-to-trough reversal: maximum `(earlier_high - later_low) / earlier_high`.
- Trough-to-peak reversal: maximum `(later_high - earlier_low) / earlier_low`.

Each non-negative magnitude is ranked against its own historical distribution
for the selected horizon and session-start offset. Emit the single highest
percentile event at or above 95, preserving its minute timestamp and direction.

## Data quality and corporate actions

- No new signal is computed from stale candles. A previously confirmed event
  remains visible with its original time under `data_unavailable`.
- Outside exchange hours, the expected session close is `market_closed`, not
  stale.
- Split and bonus factors adjust pre-action prices and matching user price
  thresholds. If adjustment is incomplete, statistical signals are paused.
- Ex-dividend, rights, merger, demerger, and symbol-change intervals show a
  corporate-action badge and pause sector/path statistics for the MVP.
- A personal price crossing may still be shown during a corporate action, but
  the corporate-action context must be displayed beside it.

## Golden cases

1. **Price crossing:** baseline 99, threshold 100 `crosses_above`, candle highs
   `[99.8, 100.2]` -> emit one personal rule at the second candle.
2. **Volume pace:** historical same-minute median 1,000,000; current cumulative
   volume 1,850,000; threshold 1.8x; previous minute 1.76x -> emit volume rule
   with pace 1.85x.
3. **Sector surprise:** stock +2.4%, sector +0.4%, historical median relative
   return +0.1%; 116 of 120 absolute deviations are <= 1.9% -> percentile
   96.67, emit `above_sector`.
4. **Path reversal:** baseline 1,000, high 1,060 at 11:42, later low 1,008;
   peak-to-trough reversal 4.91%; 117 of 120 historical reversals are smaller
   or equal -> percentile 97.5, emit reversal even though close is near flat.
5. **Provider outage:** a reversal was confirmed at 11:42 from fresh candles;
   feed becomes stale at 12:10 -> keep the confirmed event in
   `data_unavailable`, generate no later signals, and do not rank the stock in
   the live attention group.

## Catch-up API contract

`GET /api/watchlists/me/catchup` derives the user from the bearer token. The
response keeps unavailable items outside the attention ranking even when they
contain a previously confirmed event.

```json
{
  "watchlist_id": "primary",
  "source": "replay",
  "reviewed_through": "2026-09-04T05:45:00Z",
  "evaluated_through": "2026-09-04T08:30:00Z",
  "trading_minutes": 165,
  "horizon_minutes": 240,
  "coverage": "full",
  "counts": {
    "attention": 3,
    "normal": 5,
    "data_unavailable": 2
  },
  "attention": [
    {
      "item_id": "primary:RELIANCE",
      "symbol": "RELIANCE",
      "company_name": "Reliance Industries",
      "sector_index": "NIFTY50",
      "current_price": 2847.9,
      "baseline_price": 2789.2,
      "change_since_review_percent": 2.1,
      "data_state": "fresh",
      "last_updated_at": "2026-09-04T08:30:00Z",
      "narrative": "Reliance separated from the broad market and retained most of its move.",
      "chart": [{ "timestamp": "2026-09-04T05:45:00Z", "price": 2789.2 }],
      "signals": [
        {
          "kind": "sector_surprise",
          "label": "97.6th percentile relative to sector",
          "occurred_at": "2026-09-04T08:30:00Z",
          "percentile": 97.6,
          "observation_count": 252,
          "direction": "above_sector",
          "evidence": { "horizon_minutes": 240 }
        }
      ]
    }
  ],
  "normal": [],
  "data_unavailable": []
}
```

## Remaining explicit MVP limits

- Holiday data depends on the provider's exchange calendar.
- Five-session statistical coverage is the maximum catch-up horizon.
- Corporate-action coverage is provider-dependent and not inferred from price.
- Historical windows may overlap; the percentile is descriptive, not a formal
  independent-sample probability.
