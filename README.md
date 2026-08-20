# ⚽ SportyBet Handicap Scout — AI Agent

## What This Does
Automatically scans **28 football leagues worldwide** and finds matches where:
- ✅ Favorite odds **≤ 1.35** on SportyBet Nigeria
- ✅ Underdog odds **≥ 5.00** on SportyBet Nigeria
- ✅ Asian Handicap market is available

## How to Run (2 Steps)

### Step 1 — Get a Free API Key
1. Go to **https://the-odds-api.com/**
2. Click "Get API Key" — the free plan gives **500 requests/month** (enough for ~17 full daily scans)
3. Copy your API key

### Step 2 — Open the Agent
1. Open the file: `sportybet-agent/index.html` in your browser (Chrome recommended)
2. Paste your API key in the top-right field
3. Pick a date
4. Click **Scan Now**

The agent will scan all 28 leagues and show you only the matches that qualify.

## Leagues Scanned
| League | Country |
|---|---|
| Premier League | England |
| EFL Championship | England |
| La Liga | Spain |
| Serie A | Italy |
| Ligue 1 | France |
| Bundesliga | Germany |
| Eredivisie | Netherlands |
| Primeira Liga | Portugal |
| Turkish Süper Lig | Turkey |
| Scottish Premiership | Scotland |
| Belgian Pro League | Belgium |
| Brasileirão | Brazil |
| Liga Profesional | Argentina |
| Ekstraklasa | Poland |
| Austrian Bundesliga | Austria |
| Super League Greece | Greece |
| Superliga Denmark | Denmark |
| Eliteserien | Norway |
| Allsvenskan | Sweden |
| Liga Chile | Chile |
| Liga Colombia | Colombia |
| Liga MX | Mexico |
| MLS | USA |
| Champions League | Europe |
| Europa League | Europe |
| DSTV Premiership | South Africa |
| NPFL | Nigeria |

## Notes
- The odds come from **The Odds API** (aggregated from major European bookmakers)
- These are used as **proxies** for SportyBet Nigeria pricing — always verify on sportybet.com/ng
- SportyBet Nigeria is not directly accessible via API, but their prices closely follow major bookmaker consensus
- Free tier: 500 requests/month. Each full scan uses ~28 API calls.

## Strategy Reminder
- Target handicap: **Underdog +3.0 / +3.5 / +4.0**
- These lines typically pay **1.45 – 1.90** when the favorite is ≤ 1.35
- The underdog does NOT need to win — they just need to not lose by 4+ goals
