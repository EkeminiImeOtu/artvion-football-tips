"""
Live scores (ESPN, free, no key) and football news (BBC Sport RSS, free, no
key) with a short in-memory cache so a burst of visitors doesn't hammer
either upstream source on every page load.
"""
import json
import re
import ssl
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Same league set the predictions/backtest already cover (see backtest.py's
# MAIN_LEAGUES/EXTRA_LEAGUES) -- live-scores was previously limited to just
# the 6 biggest European leagues, so on days when the action was elsewhere
# (MLS, Brasileirao, Super Lig, etc.) the page looked empty even though
# matches -- including ones we'd predicted -- were actually being played.
MAJOR_LEAGUES = [
    ('eng.1', 'Premier League'),
    ('esp.1', 'La Liga'),
    ('ita.1', 'Serie A'),
    ('ger.1', 'Bundesliga'),
    ('fra.1', 'Ligue 1'),
    ('uefa.champions', 'Champions League'),
    ('eng.2', 'Championship'),
    ('sco.1', 'Premiership (Scotland)'),
    ('ned.1', 'Eredivisie'),
    ('bel.1', 'Pro League (Belgium)'),
    ('por.1', 'Primeira Liga'),
    ('tur.1', 'Super Lig'),
    ('gre.1', 'Super League (Greece)'),
    ('arg.1', 'Liga Profesional (Argentina)'),
    ('aut.1', 'Bundesliga (Austria)'),
    ('bra.1', 'Brasileirao'),
    ('den.1', 'Superliga (Denmark)'),
    ('mex.1', 'Liga MX'),
    ('nor.1', 'Eliteserien'),
    ('pol.1', 'Ekstraklasa'),
    ('swe.1', 'Allsvenskan'),
    ('usa.1', 'MLS'),
]

NEWS_FEED_URL = 'https://feeds.bbci.co.uk/sport/football/rss.xml'

CACHE_TTL_SCORES = 60
CACHE_TTL_NEWS = 600
_cache = {}


def _cached(key, ttl, loader):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = loader()
    _cache[key] = (now, value)
    return value


def _fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        return r.read()


def _load_league_fixtures(slug, league_name):
    fixtures = []
    try:
        data = json.loads(_fetch(f'https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard'))
    except Exception:
        return fixtures
    for ev in data.get('events', []):
        try:
            comp = ev['competitions'][0]
            competitors = comp['competitors']
            home = next(c for c in competitors if c.get('homeAway') == 'home')
            away = next(c for c in competitors if c.get('homeAway') == 'away')
            status = comp['status']['type']
            fixtures.append({
                'league': league_name,
                'home_name': home['team']['displayName'],
                'away_name': away['team']['displayName'],
                'home_logo': home['team'].get('logo'),
                'away_logo': away['team'].get('logo'),
                'home_score': home.get('score'),
                'away_score': away.get('score'),
                'detail': status.get('shortDetail', status.get('description', '')),
                'is_live': status.get('state') == 'in',
                'is_final': bool(status.get('completed')),
            })
        except (KeyError, StopIteration):
            continue
    return fixtures


def _load_live_scores():
    # Fetched in parallel -- MAJOR_LEAGUES covers 21 leagues now (matching
    # the predictions' own league coverage), and doing that serially would
    # make a cold-cache page load noticeably slow. Capped at 6 concurrent
    # requests rather than one thread per league (21) -- Render's free tier
    # is resource-constrained (shared CPU, 512MB RAM), and firing off 21
    # simultaneous outbound HTTPS/SSL connections risked stalling the whole
    # instance rather than actually speeding things up.
    fixtures = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(lambda pair: _load_league_fixtures(*pair), MAJOR_LEAGUES):
            fixtures.extend(result)

    # Group by league (in MAJOR_LEAGUES order) so the page can show one
    # header per league instead of the same league's name repeating every
    # time fixtures from different leagues interleave; live matches surface
    # first within each league's own block.
    league_order = {name: i for i, (_, name) in enumerate(MAJOR_LEAGUES)}

    def sort_key(f):
        status_rank = 0 if f['is_live'] else 1 if not f['is_final'] else 2
        return (league_order.get(f['league'], len(league_order)), status_rank)
    fixtures.sort(key=sort_key)
    return fixtures


def get_live_scores():
    return _cached('live_scores', CACHE_TTL_SCORES, _load_live_scores)


def _load_news(limit=12):
    try:
        raw = _fetch(NEWS_FEED_URL)
        root = ET.fromstring(raw)
    except Exception:
        return []
    items = []
    media_ns = '{http://search.yahoo.com/mrss/}'
    for item in root.findall('.//item')[:limit]:
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        description = (item.findtext('description') or '').strip()
        pub_raw = item.findtext('pubDate') or ''
        thumb = item.find(f'{media_ns}thumbnail')
        image_url = thumb.get('url') if thumb is not None else None
        # BBC's RSS thumbnails are small (240px); ask for a bigger crop from
        # the same CDN path instead of stretching a tiny image up.
        if image_url:
            image_url = image_url.replace('/standard/240/', '/standard/480/')
        try:
            pub_fmt = parsedate_to_datetime(pub_raw).strftime('%d %b, %H:%M')
        except Exception:
            pub_fmt = ''
        if title and link:
            items.append({
                'title': title, 'link': link, 'pub_date': pub_fmt,
                'image': image_url, 'description': description,
            })
    return items


def get_news(limit=12):
    return _cached('news', CACHE_TTL_NEWS, lambda: _load_news(limit))


# ============ Linking predictions to live fixtures ============
# The Odds API (source of prediction team names) and ESPN (source of live
# scores) don't always spell a team the same way. Worse than accents or
# punctuation, common nicknames drop whole syllables from the middle of a
# word ("Man City" -> "Manchester City", "Nottm Forest" -> "Nottingham
# Forest"), which plain substring matching can't catch. Word-level token
# matching (with a small alias table for the common short forms) handles
# this: a match requires every token of the shorter name to appear in the
# longer name, so "Real Madrid" still won't collide with "Real Sociedad".
_TEAM_TOKEN_ALIASES = {
    'man': 'manchester', 'utd': 'united', 'spurs': 'tottenham',
    'wolves': 'wolverhampton', 'inter': 'internazionale', 'barca': 'barcelona',
    'psg': 'paris', 'munchen': 'munich', 'nottm': 'nottingham',
    'athletic': 'ath', 'atletico': 'atl',
}
_TEAM_TOKEN_STOPWORDS = {'fc', 'cf', 'afc', 'cd', 'sd', 'ud', 'the'}


def _strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def _team_tokens(name):
    n = _strip_accents((name or '').lower())
    n = re.sub(r'[^a-z0-9\s]', ' ', n)
    tokens = set()
    for t in n.split():
        if t in _TEAM_TOKEN_STOPWORDS:
            continue
        tokens.add(_TEAM_TOKEN_ALIASES.get(t, t))
    return tokens


def _teams_match(a, b):
    ta, tb = _team_tokens(a), _team_tokens(b)
    if not ta or not tb:
        return False
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return shorter.issubset(longer)


def find_live_fixture(home_team, away_team, fixtures):
    for f in fixtures:
        if _teams_match(home_team, f['home_name']) and _teams_match(away_team, f['away_name']):
            return f
    return None
