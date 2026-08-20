"""
Historical backtest against free data from football-data.co.uk.

The live app can't get historical bookmaker odds for free (The Odds API's
free tier only serves live/upcoming markets), so this uses a different,
genuinely free source: football-data.co.uk publishes free CSVs per league
with real final scores *and* the closing odds bookmakers actually offered.

This script re-implements the same Poisson-probability + market-edge logic
used in index.html's analyzeMatch(), replays it match-by-match through
several seasons of real history (using only data that would have been known
*before* each match -- no lookahead), grades every simulated pick against
the real final score, and reports the actual win rate / ROI.

Results are written to backtest_results.db -- a separate file from
predictions.db. This is a historical simulation, not part of your live
forward-tracked record, and the two are never mixed.

Usage: python backtest.py
"""
import os
import csv
import io
import math
import sqlite3
import time
from datetime import datetime
from urllib.request import urlopen, Request

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(AGENT_DIR, 'backtest_data')
DB_PATH = os.path.join(AGENT_DIR, 'backtest_results.db')
os.makedirs(CACHE_DIR, exist_ok=True)

# ============ League registry ============
# "Main" leagues: one CSV per season, e.g. mmz4281/2324/E0.csv
MAIN_LEAGUES = {
    'E0': 'Premier League (England)',
    'E1': 'Championship (England)',
    'SC0': 'Premiership (Scotland)',
    'D1': 'Bundesliga (Germany)',
    'I1': 'Serie A (Italy)',
    'SP1': 'La Liga (Spain)',
    'F1': 'Ligue 1 (France)',
    'N1': 'Eredivisie (Netherlands)',
    'B1': 'Pro League (Belgium)',
    'P1': 'Primeira Liga (Portugal)',
    'T1': 'Super Lig (Turkey)',
    'G1': 'Super League (Greece)',
}
SEASONS = ['2122', '2223', '2324', '2425', '2526']  # last 5 seasons

# "Extra" leagues: one CSV with every season, filtered by a Season column
EXTRA_LEAGUES = {
    'ARG': 'Liga Profesional (Argentina)',
    'AUT': 'Bundesliga (Austria)',
    'BRA': 'Brasileirao (Brazil)',
    'DNK': 'Superliga (Denmark)',
    'MEX': 'Liga MX (Mexico)',
    'NOR': 'Eliteserien (Norway)',
    'POL': 'Ekstraklasa (Poland)',
    'SWE': 'Allsvenskan (Sweden)',
    'USA': 'MLS (USA)',
}
EXTRA_MIN_YEAR = 2021

MIN_PRIOR_GAMES = 3  # skip early-season matches where "last 6 form" would be near-empty

# ============ Fetch + cache ============

def fetch(url, cache_name):
    cache_path = os.path.join(CACHE_DIR, cache_name)
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return f.read()
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urlopen(req, timeout=20).read()
        with open(cache_path, 'wb') as f:
            f.write(data)
        return data
    except Exception as e:
        print(f"    ! failed to fetch {url}: {e}")
        return None


def parse_float(v):
    try:
        if v is None or v == '':
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def load_main_league(code, name):
    matches = []
    for season in SEASONS:
        url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
        raw = fetch(url, f"{code}_{season}.csv")
        if not raw:
            continue
        text = raw.decode('latin-1', errors='replace')
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                date = datetime.strptime(row['Date'].strip(), '%d/%m/%Y')
            except Exception:
                continue
            home, away = row.get('HomeTeam'), row.get('AwayTeam')
            fthg, ftag = parse_float(row.get('FTHG')), parse_float(row.get('FTAG'))
            if not home or not away or fthg is None or ftag is None:
                continue
            h_odds = parse_float(row.get('AvgH')) or parse_float(row.get('B365H'))
            d_odds = parse_float(row.get('AvgD')) or parse_float(row.get('B365D'))
            a_odds = parse_float(row.get('AvgA')) or parse_float(row.get('B365A'))
            over25 = parse_float(row.get('Avg>2.5')) or parse_float(row.get('B365>2.5'))
            under25 = parse_float(row.get('Avg<2.5')) or parse_float(row.get('B365<2.5'))
            matches.append({
                'league': name, 'date': date, 'home': home, 'away': away,
                'fthg': fthg, 'ftag': ftag,
                'h_odds': h_odds, 'd_odds': d_odds, 'a_odds': a_odds,
                'over25': over25, 'under25': under25,
            })
    matches.sort(key=lambda m: m['date'])
    return matches


def load_extra_league(code, name):
    url = f"https://www.football-data.co.uk/new/{code}.csv"
    raw = fetch(url, f"{code}_all.csv")
    if not raw:
        return []
    text = raw.decode('latin-1', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    matches = []
    for row in reader:
        try:
            season_year = int(str(row.get('Season', '0'))[:4])
        except Exception:
            continue
        if season_year < EXTRA_MIN_YEAR:
            continue
        try:
            date = datetime.strptime(row['Date'].strip(), '%d/%m/%Y')
        except Exception:
            continue
        home, away = row.get('Home'), row.get('Away')
        hg, ag = parse_float(row.get('HG')), parse_float(row.get('AG'))
        if not home or not away or hg is None or ag is None:
            continue
        h_odds = (parse_float(row.get('AvgCH')) or parse_float(row.get('AvgH'))
                  or parse_float(row.get('B365CH')) or parse_float(row.get('B365H')))
        d_odds = (parse_float(row.get('AvgCD')) or parse_float(row.get('AvgD'))
                  or parse_float(row.get('B365CD')) or parse_float(row.get('B365D')))
        a_odds = (parse_float(row.get('AvgCA')) or parse_float(row.get('AvgA'))
                  or parse_float(row.get('B365CA')) or parse_float(row.get('B365A')))
        matches.append({
            'league': name, 'date': date, 'home': home, 'away': away,
            'fthg': hg, 'ftag': ag,
            'h_odds': h_odds, 'd_odds': d_odds, 'a_odds': a_odds,
            'over25': None, 'under25': None,
        })
    matches.sort(key=lambda m: m['date'])
    return matches


# ============ Probability engine (mirrors index.html's Poisson model) ============
MAX_GOALS_GRID = 8


def poisson_prob(lam, k):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def devig_3way(h, d, a):
    if not h or not a:
        return None
    raw_h = 1 / h
    raw_d = 1 / d if d else 0
    raw_a = 1 / a
    overround = raw_h + raw_d + raw_a
    if overround <= 0:
        return None
    return {'home': raw_h / overround, 'draw': raw_d / overround, 'away': raw_a / overround}


def devig_2way(side_odds, other_odds):
    if not side_odds:
        return None
    if other_odds:
        raw_side = 1 / side_odds
        raw_other = 1 / other_odds
        return raw_side / (raw_side + raw_other)
    return min(0.98, (1 / side_odds) / 1.06)


def derive_match_probabilities(home_form, away_form):
    lambda_home = max(0.15, (home_form['avgScored'] + away_form['avgConceded']) / 2)
    lambda_away = max(0.15, (away_form['avgScored'] + home_form['avgConceded']) / 2)

    home_dist = [poisson_prob(lambda_home, k) for k in range(MAX_GOALS_GRID + 1)]
    away_dist = [poisson_prob(lambda_away, k) for k in range(MAX_GOALS_GRID + 1)]
    matrix = [[home_dist[i] * away_dist[j] for j in range(MAX_GOALS_GRID + 1)] for i in range(MAX_GOALS_GRID + 1)]

    p_home_win = p_draw = p_away_win = 0.0
    p_over15 = p_over25 = p_over35 = p_btts = p_gg_over25 = 0.0
    p_home_over05 = p_home_over15 = p_home_over25 = 0.0
    p_away_over05 = p_away_over15 = p_away_over25 = 0.0

    for i in range(MAX_GOALS_GRID + 1):
        for j in range(MAX_GOALS_GRID + 1):
            p = matrix[i][j]
            if i > j:
                p_home_win += p
            elif i == j:
                p_draw += p
            else:
                p_away_win += p
            if i + j >= 2:
                p_over15 += p
            if i + j >= 3:
                p_over25 += p
            if i + j >= 4:
                p_over35 += p
            if i >= 1 and j >= 1:
                p_btts += p
                if i + j >= 3:
                    p_gg_over25 += p
            if i >= 1:
                p_home_over05 += p
            if i >= 2:
                p_home_over15 += p
            if i >= 3:
                p_home_over25 += p
            if j >= 1:
                p_away_over05 += p
            if j >= 2:
                p_away_over15 += p
            if j >= 3:
                p_away_over25 += p

    def handicap_cover_prob(line, dog_is_home):
        p = 0.0
        for i in range(MAX_GOALS_GRID + 1):
            for j in range(MAX_GOALS_GRID + 1):
                dog_score = i if dog_is_home else j
                fav_score = j if dog_is_home else i
                if dog_score + line > fav_score:
                    p += matrix[i][j]
        return p

    return {
        'lambda_home': lambda_home, 'lambda_away': lambda_away,
        'p_home_win': p_home_win, 'p_draw': p_draw, 'p_away_win': p_away_win,
        'p_over15': p_over15, 'p_over25': p_over25, 'p_over35': p_over35,
        'p_btts': p_btts, 'p_gg_over25': p_gg_over25,
        'p_home_over05': p_home_over05, 'p_home_over15': p_home_over15, 'p_home_over25': p_home_over25,
        'p_away_over05': p_away_over05, 'p_away_over15': p_away_over15, 'p_away_over25': p_away_over25,
        'handicap_cover_prob': handicap_cover_prob,
    }


EDGE_HIGH, EDGE_MEDIUM, EDGE_LOW = 0.10, 0.06, 0.03
PROB_HIGH, PROB_MEDIUM, PROB_LOW = 0.75, 0.65, 0.55
DC_HIGH, DC_MED, DC_LOW = 0.82, 0.75, 0.68
MIN_ODDS = 1.20


def edge_conf(edge):
    return 'high' if edge >= EDGE_HIGH else 'medium' if edge >= EDGE_MEDIUM else 'low'


def prob_conf(p):
    return 'high' if p >= PROB_HIGH else 'medium' if p >= PROB_MEDIUM else 'low'


def dc_conf(p):
    return 'high' if p >= DC_HIGH else 'medium' if p >= DC_MED else 'low'


# ============ Rolling form (last 6 games, no lookahead) ============

def form_from_games(games):
    if not games:
        return None
    last6 = games[-6:]
    scored = sum(g['scored'] for g in last6)
    conceded = sum(g['conceded'] for g in last6)
    clean_sheets = sum(1 for g in last6 if g['conceded'] == 0)
    games_scored = sum(1 for g in last6 if g['scored'] > 0)
    wins = sum(1 for g in last6 if g['scored'] > g['conceded'])
    m = len(last6)
    return {
        'played': m, 'avgScored': scored / m, 'avgConceded': conceded / m,
        'cleanSheets': clean_sheets, 'scoringRate': games_scored / m, 'winRate': wins / m,
    }


# ============ Pick generation + grading (mirrors analyzeMatch's hasForm branch) ============

def generate_picks(m, home_form, away_form):
    # Gated on the model's OWN calibrated probability, not on beating the
    # market -- a backtest run showed "model beats de-vigged market odds"
    # picks performed WORST where the claimed edge was biggest (21% actual
    # win rate on 20+pt "edges" vs 59% where the model deferred to the
    # market), the signature of noise, not skill, from a shallow 6-game
    # form window. The raw probability was reasonably calibrated on its own,
    # so that's what gates picks now.
    picks = []
    hg, ag = m['fthg'], m['ftag']
    mp = derive_match_probabilities(home_form, away_form)
    mkt3 = devig_3way(m['h_odds'], m['d_odds'], m['a_odds'])

    # Match Winner
    for team, odds, p_model, is_home in [
        (m['home'], m['h_odds'], mp['p_home_win'], True),
        (m['away'], m['a_odds'], mp['p_away_win'], False),
    ]:
        if odds is None or odds < MIN_ODDS:
            continue
        if p_model >= PROB_LOW:
            won = (hg > ag) if is_home else (ag > hg)
            picks.append({'market': 'Match Winner', 'conf': prob_conf(p_model), 'odds': odds, 'won': won})

    # Draw is deliberately excluded: backtesting showed independent-Poisson
    # draw probability barely discriminates (actual draw rate stayed ~21-26%
    # across the whole 0.20-0.30+ predicted range) -- a known weakness of
    # this model family without a Dixon-Coles-style low-score correction.

    # Over 2.5 Total Goals
    if m['over25'] and m['over25'] >= MIN_ODDS and mp['p_over25'] >= PROB_MEDIUM:
        picks.append({'market': 'Over 2.5 Total Goals', 'conf': prob_conf(mp['p_over25']), 'odds': m['over25'], 'won': (hg + ag) >= 3})

    # Both Teams to Score (no odds column available -- probability bar only)
    if mp['p_btts'] >= PROB_MEDIUM:
        picks.append({'market': 'Both Teams to Score', 'conf': prob_conf(mp['p_btts']), 'odds': None, 'won': hg >= 1 and ag >= 1})

    # GG & Over 2.5 and Team Over 2.5 Goals are deliberately excluded: a full
    # 21-league run showed neither clears a usable bar at any confidence
    # tier (GG & Over 2.5 medium-tier actual 52.2% vs nominal >=65%; Team
    # Over 2.5 low-tier actual 48.4% vs nominal >=55%, and it almost never
    # reaches a higher tier at all). Likely cause: treating BTTS/Over-2.5 as
    # independent overstates their joint probability, and a single team
    # scoring 3+ is too rare an event for a 6-game rolling average to price.

    # Handicap -- same big-favorite/big-underdog gate as the live app
    if m['h_odds'] and m['a_odds']:
        if m['h_odds'] <= m['a_odds']:
            fav_odds, dog_odds, dog_is_home = m['h_odds'], m['a_odds'], False
        else:
            fav_odds, dog_odds, dog_is_home = m['a_odds'], m['h_odds'], True
        if fav_odds <= 1.35 and dog_odds >= 5.00:
            chosen = None
            for line in (3.0, 3.5, 4.0):
                p = mp['handicap_cover_prob'](line, dog_is_home)
                if p >= 0.90:
                    chosen = (line, p)
                    break
            if not chosen:
                chosen = (4.0, mp['handicap_cover_prob'](4.0, dog_is_home))
            line, p = chosen
            conf = 'high' if p >= 0.95 else 'medium' if p >= 0.90 else 'low'
            dog_score = hg if dog_is_home else ag
            fav_score = ag if dog_is_home else hg
            won = (dog_score + line) > fav_score
            picks.append({'market': 'Handicap', 'conf': conf, 'odds': None, 'won': won})

    # Team Over 1.5 Goals (probability bar only). Team Over 2.5 excluded -- see note above.
    for p15, scored in [
        (mp['p_home_over15'], hg),
        (mp['p_away_over15'], ag),
    ]:
        if p15 >= PROB_MEDIUM:
            picks.append({'market': 'Team Over 1.5 Goals', 'conf': prob_conf(p15), 'odds': None, 'won': scored >= 2})

    # Double Chance
    p1x, px2, p12 = mp['p_home_win'] + mp['p_draw'], mp['p_away_win'] + mp['p_draw'], 1 - mp['p_draw']
    if p1x >= DC_LOW:
        picks.append({'market': 'Double Chance 1X', 'conf': dc_conf(p1x), 'odds': None, 'won': hg >= ag})
    if px2 >= DC_LOW:
        picks.append({'market': 'Double Chance X2', 'conf': dc_conf(px2), 'odds': None, 'won': ag >= hg})
    if p12 >= DC_LOW:
        picks.append({'market': 'Double Chance 12', 'conf': dc_conf(p12), 'odds': None, 'won': hg != ag})

    # Team to Score (Over 0.5) (probability bar only)
    for p05, scored in [(mp['p_home_over05'], hg), (mp['p_away_over05'], ag)]:
        if p05 >= PROB_HIGH:
            picks.append({'market': 'Team to Score (Over 0.5)', 'conf': prob_conf(p05), 'odds': None, 'won': scored >= 1})

    return picks


def run_backtest_for_league(matches, league_name):
    team_games = {}
    all_picks = []
    for m in matches:
        hf_games = team_games.get(m['home'], [])
        af_games = team_games.get(m['away'], [])
        if len(hf_games) >= MIN_PRIOR_GAMES and len(af_games) >= MIN_PRIOR_GAMES:
            home_form = form_from_games(hf_games)
            away_form = form_from_games(af_games)
            for p in generate_picks(m, home_form, away_form):
                p['league'] = league_name
                p['date'] = m['date']
                all_picks.append(p)
        # Update AFTER generating picks so a match never informs its own prediction.
        team_games.setdefault(m['home'], []).append({'scored': m['fthg'], 'conceded': m['ftag']})
        team_games.setdefault(m['away'], []).append({'scored': m['ftag'], 'conceded': m['fthg']})
    return all_picks


# ============ Aggregation + report ============

def summarize(picks):
    total = len(picks)
    won = sum(1 for p in picks if p['won'])
    lost = total - won
    win_rate = round(won / total * 100, 1) if total else None
    staked = sum(1 for p in picks if p['odds'])
    returned = sum(p['odds'] for p in picks if p['odds'] and p['won'])
    roi = round((returned - staked) / staked * 100, 1) if staked else None
    return {'total': total, 'won': won, 'lost': lost, 'win_rate': win_rate, 'roi_pct': roi, 'staked_count': staked}


def group_by(picks, key):
    groups = {}
    for p in picks:
        groups.setdefault(p[key], []).append(p)
    return dict(sorted(((k, summarize(v)) for k, v in groups.items()), key=lambda kv: -kv[1]['total']))


def print_table(title, groups):
    print(f"\n{title}")
    print("-" * len(title))
    for name, s in groups.items():
        wr = f"{s['win_rate']}%" if s['win_rate'] is not None else "n/a"
        roi = f"{s['roi_pct']}%" if s['roi_pct'] is not None else "n/a"
        print(f"  {name[:34]:<34} {s['total']:>5} picks  W{s['won']:>4} L{s['lost']:>4}  win {wr:>6}  ROI {roi:>7}")


def main():
    start = time.time()
    all_picks = []

    print("Downloading + processing MAIN leagues (top-flight, last 5 seasons)...")
    for code, name in MAIN_LEAGUES.items():
        matches = load_main_league(code, name)
        picks = run_backtest_for_league(matches, name)
        print(f"  {name:<30} {len(matches):>5} matches -> {len(picks):>5} simulated picks")
        all_picks.extend(picks)
        time.sleep(0.2)

    print("\nDownloading + processing EXTRA leagues (since {})...".format(EXTRA_MIN_YEAR))
    for code, name in EXTRA_LEAGUES.items():
        matches = load_extra_league(code, name)
        picks = run_backtest_for_league(matches, name)
        print(f"  {name:<30} {len(matches):>5} matches -> {len(picks):>5} simulated picks")
        all_picks.extend(picks)
        time.sleep(0.2)

    conn = sqlite3.connect(DB_PATH)
    conn.execute('DROP TABLE IF EXISTS backtest_picks')
    conn.execute('''CREATE TABLE backtest_picks (
        league TEXT, date TEXT, market TEXT, conf TEXT, odds REAL, won INTEGER
    )''')
    conn.executemany(
        'INSERT INTO backtest_picks VALUES (?,?,?,?,?,?)',
        [(p['league'], p['date'].strftime('%Y-%m-%d'), p['market'], p['conf'], p['odds'], int(p['won'])) for p in all_picks]
    )
    conn.commit()
    conn.close()

    overall = summarize(all_picks)
    elapsed = time.time() - start

    print("\n" + "=" * 70)
    print("  HISTORICAL BACKTEST -- ALL LEAGUES")
    print("=" * 70)
    print(f"  Total simulated picks : {overall['total']}")
    print(f"  Won / Lost            : {overall['won']} / {overall['lost']}")
    wr = f"{overall['win_rate']}%" if overall['win_rate'] is not None else "n/a"
    print(f"  Win rate              : {wr}")
    roi = f"{overall['roi_pct']}%" if overall['roi_pct'] is not None else "n/a"
    print(f"  ROI (flat 1u, priced picks only, vs. closing market odds): {roi} on {overall['staked_count']} picks")
    print(f"  Runtime               : {elapsed:.1f}s")

    print_table("BY MARKET", group_by(all_picks, 'market'))
    print_table("BY CONFIDENCE TIER", group_by(all_picks, 'conf'))
    print_table("BY LEAGUE", group_by(all_picks, 'league'))

    print(f"\nFull pick-level detail saved to {DB_PATH} (table: backtest_picks).")
    print("This is a separate file from predictions.db -- it is never mixed with your live track record.")


if __name__ == '__main__':
    main()
