---
name: intraday-setup-scanner
description: Scan US stocks during market hours (mid-session) and after hours (post-market) for buy setups that cross defined thresholds, then notify the user. Use when asked to scan for setups, run the midday or post-market scan, or when fired by the scheduled scan task. Complements the after-close portfolio-additions skill; it alerts, it never places orders.
---

# Intraday & post-market setup scanner

Goal: catch setups that form *during* the session (and after hours) instead of
only after the close. Alert only when a threshold is crossed. Silence is the
default — no setup, no notification.

**Never place, modify or cancel orders.** This skill only reads data and alerts.
Present findings as setups that met rules, not as advice to buy.

## 1. Check the session first

Call `mcp__Alpaca_Paper_Trading__get_clock`.

| State | Mode |
|---|---|
| `is_open: true`, before 10:00 ET | Stop. First 30 min is noise; opening-range not set yet. |
| `is_open: true`, 10:00–15:45 ET | **Mid-market mode** (section 3) |
| Closed, 16:05–19:30 ET on a trading day | **Post-market mode** (section 4) |
| Anything else (weekend, holiday, overnight) | Stop, no output. |

Half days (e.g. day after Thanksgiving, Christmas Eve) close 13:00 ET — use
`next_close` from the clock, not a hard-coded 16:00.

## 2. Build the universe

1. **Watchlist** — read `watchlist.md` in this skill folder. These are always
   scanned. (Seed it with the tickers the after-close skill recommended; append
   its new picks each evening.)
2. **Discovery** — `mcp__Alpaca_Paper_Trading__get_most_active_stocks` (top 50,
   by volume) plus `mcp__Alpaca_Paper_Trading__get_market_movers` (top 25).
3. **Hard filters** (drop anything that fails — the raw movers list is mostly junk):
   - Price ≥ $5
   - Symbol is a common stock/ETF: drop tickers ending in `W`, `WS`, `U`, `R`
     (warrants, units, rights) and anything Alpaca marks non-tradable
   - Average daily volume ≥ 1,000,000 shares (FMP `quote` → `avgVolume` if present,
     else 20-day average from daily bars)
   - Market cap ≥ $1B for discovery names (watchlist names are exempt)

Cap the universe at ~40 symbols per run to keep it fast.

## 3. Mid-market mode — setups and thresholds

Data per symbol:
- **Price, day high/low, volume, prev close, 50/200-day avg**: `mcp__FMP__quote`
  (`endpoint: quote`). Use FMP volume — Alpaca's free feed is IEX-only and
  under-reports volume ~30x.
- **Intraday bars**: `mcp__Alpaca_Paper_Trading__get_stock_bars`,
  `timeframe: 5Min`, today only (for VWAP, opening range, RSI).
- **Daily bars**: `get_stock_bars`, `timeframe: 1Day`, `days: 60` (for prior
  day high/low, 20-day avg volume, 14-day RSI).

**Relative volume (RVOL)** = today's volume ÷ (20-day avg volume × fraction of
session elapsed). Compute fraction from minutes since 09:30 ÷ 390 (or ÷ session
length on half days).

A symbol **triggers** when it meets ALL rules of at least one setup:

| # | Setup | Rules (all required) |
|---|---|---|
| A | **Opening-range breakout** | Price > high of first 30 min (09:30–10:00) by ≥ 0.3% · RVOL ≥ 1.5 · price above VWAP · above 50-day avg |
| B | **Prior-day high break** | Price > yesterday's high by ≥ 0.5% · RVOL ≥ 1.5 · held above it for ≥ 2 consecutive 5-min closes |
| C | **Pullback to support in uptrend** | Price > 200-day avg · down ≥ 3% on day OR touched 50-day avg (±1%) · 5-min RSI(14) ≤ 30 then last 5-min bar closes up · not below today's low by > 0.5% |
| D | **VWAP reclaim after flush** | Fell ≥ 2% below VWAP earlier today · now back above VWAP for ≥ 2 consecutive 5-min closes · RVOL ≥ 1.2 |
| E | **Watchlist buy zone** | Watchlist ticker with a `buy_below` price in `watchlist.md` and price ≤ that level |

**Disqualifiers** (skip even if triggered):
- Earnings within the next 2 trading days (`mcp__FMP__calendar` earnings) — flag
  instead of alerting
- Gap > 15% on news-free day with RVOL > 10 (likely halt/pump risk)
- SPY down > 2% on the day → still alert, but prefix message with `RISK-OFF`

**Score** each trigger 1–5: +1 per setup matched beyond the first, +1 RVOL ≥ 3,
+1 on watchlist, +1 above both 50 and 200-day avg, −1 if SPY red > 1%.
Base score 2. Only notify on score ≥ 3 (tunable in `watchlist.md` → `min_score`).

## 4. Post-market mode

Use `mcp__FMP__quote` with `endpoint: aftermarket-quote` (and
`aftermarket-trade`) for watchlist names plus today's triggered names.

Trigger when:
- After-hours move ≥ +4% or ≤ −4% vs regular close **and** there is a same-day
  headline (`mcp__FMP__news`) — earnings beats/misses, guidance, M&A
- A watchlist name trades after hours at or below its `buy_below` level

Label all post-market alerts `AH` — liquidity is thin, spreads are wide, and
prices often reverse by the next open. Say so in the alert.

## 5. De-duplicate

Keep `alerts-log.md` in this skill folder (append-only, one line per alert:
`YYYY-MM-DD HH:MM ET | TICKER | setup | price | score`).
Do not alert the same ticker + setup twice on the same day unless price has
moved ≥ 2% further in the setup's direction since the last alert.

## 6. Notify

If ≥ 1 qualifying alert:
- Send **one** push notification (`PushNotification`), < 200 chars, highest
  score first, e.g.
  `Midday scan: NVDA ORB+PDH $142.10 RVOL 2.4 (5/5); AMD pullback-50d $118.30 (3/5)`
- Then write the full table in the reply / session output:

| Ticker | Setup(s) | Price | Trigger level | Invalidation (stop idea) | RVOL | Score | Note |

  Invalidation = for A/B: back below the broken level; for C: today's low;
  for D: back below VWAP; for E: user's own stop if given.

If no alerts: send nothing. Optionally write one line to the session:
`HH:MM ET scan — 0 setups met thresholds (N symbols checked).`

## 7. Rules of honesty

- Quote only numbers returned by tools in this run; never estimate a price.
- State the data timestamp on every alert.
- If a data call fails, say which symbols were skipped — don't silently drop them.
- These are rule matches, not recommendations. Position sizing and the decision
  to buy stay with the user.
