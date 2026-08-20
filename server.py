"""
SportyBet Multi-Market Scout — Local API Proxy + Tracking Server
Run this before opening index.html.
It proxies ESPN requests to avoid CORS blocking in the browser, and
persists every AI pick + its eventual result to a local SQLite database
so real accuracy can be measured over time.

Usage: python server.py
Then open http://localhost:8888 in your browser.
"""
import http.server
import urllib.request
import json
import ssl
import os
import sqlite3
from datetime import datetime, timezone

PORT = 8888
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(AGENT_DIR, 'predictions.db')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

RESOLVED_STATUSES = ('WON', 'LOST')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_date TEXT NOT NULL,
            scan_logged_at TEXT NOT NULL,
            league TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            market TEXT NOT NULL,
            display TEXT NOT NULL,
            confidence TEXT,
            odds REAL,
            bet_type TEXT,
            espn_slug TEXT,
            home_espn_id TEXT,
            away_espn_id TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            actual_home INTEGER,
            actual_away INTEGER,
            resolved_at TEXT,
            UNIQUE(match_date, home_team, away_team, market, display)
        )
    ''')
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def upsert_pick(conn, row):
    """Insert a new pick, or — if it already exists and is still PENDING —
    update it with a newly-known result. Never overwrite an already
    resolved (WON/LOST) row, and never downgrade a resolved row back to
    PENDING."""
    existing = conn.execute(
        'SELECT id, status FROM predictions WHERE match_date=? AND home_team=? AND away_team=? AND market=? AND display=?',
        (row['match_date'], row['home_team'], row['away_team'], row['market'], row['display'])
    ).fetchone()

    if existing is None:
        conn.execute('''
            INSERT INTO predictions
            (match_date, scan_logged_at, league, home_team, away_team, market, display,
             confidence, odds, bet_type, espn_slug, home_espn_id, away_espn_id,
             status, actual_home, actual_away, resolved_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            row['match_date'], now_iso(), row.get('league'), row['home_team'], row['away_team'],
            row['market'], row['display'], row.get('confidence'), row.get('odds'), row.get('bet_type'),
            row.get('espn_slug'), row.get('home_espn_id'), row.get('away_espn_id'),
            row.get('status', 'PENDING'), row.get('actual_home'), row.get('actual_away'),
            now_iso() if row.get('status') in RESOLVED_STATUSES else None
        ))
        return 'inserted'

    if existing['status'] == 'PENDING' and row.get('status') in RESOLVED_STATUSES:
        conn.execute('''
            UPDATE predictions SET status=?, actual_home=?, actual_away=?, resolved_at=?
            WHERE id=?
        ''', (row['status'], row.get('actual_home'), row.get('actual_away'), now_iso(), existing['id']))
        return 'updated'

    return 'skipped'


def build_stats():
    conn = get_db()
    rows = conn.execute('SELECT * FROM predictions').fetchall()
    conn.close()

    def summarize(items):
        total = len(items)
        won = sum(1 for r in items if r['status'] == 'WON')
        lost = sum(1 for r in items if r['status'] == 'LOST')
        pending = sum(1 for r in items if r['status'] not in RESOLVED_STATUSES)
        resolved = won + lost
        win_rate = round(won / resolved * 100, 1) if resolved else None

        staked = 0
        returned = 0
        for r in items:
            if r['status'] in RESOLVED_STATUSES and r['odds']:
                staked += 1
                if r['status'] == 'WON':
                    returned += r['odds']
        roi = round((returned - staked) / staked * 100, 1) if staked else None

        return {
            'total': total, 'won': won, 'lost': lost, 'pending': pending,
            'resolved': resolved, 'win_rate': win_rate, 'roi_pct': roi,
            'staked_count': staked
        }

    overall = summarize(rows)

    def group_by(key):
        groups = {}
        for r in rows:
            k = r[key] or 'Unknown'
            groups.setdefault(k, []).append(r)
        return {k: summarize(v) for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))}

    return {
        'overall': overall,
        'by_market': group_by('market'),
        'by_confidence': group_by('confidence'),
        'by_league': group_by('league'),
    }


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=AGENT_DIR, **kwargs)

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        from urllib.parse import urlparse
        path = urlparse(self.path).path

        if path == '/api/log-picks':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length) or b'{}')
                matches = body.get('matches', [])
                conn = get_db()
                inserted = 0
                updated = 0
                for m in matches:
                    for p in m.get('picks', []):
                        row = {
                            'match_date': m.get('match_date'),
                            'league': m.get('league'),
                            'home_team': m.get('home_team'),
                            'away_team': m.get('away_team'),
                            'espn_slug': m.get('espn_slug'),
                            'home_espn_id': m.get('home_espn_id'),
                            'away_espn_id': m.get('away_espn_id'),
                            'market': p.get('market'),
                            'display': p.get('display'),
                            'confidence': p.get('conf'),
                            'odds': p.get('odds'),
                            'bet_type': p.get('betType'),
                            'status': p.get('status') or 'PENDING',
                            'actual_home': m.get('actual_home'),
                            'actual_away': m.get('actual_away'),
                        }
                        if not row['match_date'] or not row['home_team'] or not row['market'] or not row['display']:
                            continue
                        result = upsert_pick(conn, row)
                        if result == 'inserted':
                            inserted += 1
                        elif result == 'updated':
                            updated += 1
                conn.commit()
                conn.close()
                self._send_json({'inserted': inserted, 'updated': updated})
            except Exception as e:
                self._send_json({'error': str(e)}, 500)
            return

        if path == '/api/update-pick':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length) or b'{}')
                pid = body.get('id')
                status = body.get('status')
                if not pid or status not in RESOLVED_STATUSES:
                    self._send_json({'error': 'id and a resolved status are required'}, 400)
                    return
                conn = get_db()
                conn.execute('''
                    UPDATE predictions SET status=?, actual_home=?, actual_away=?, resolved_at=?
                    WHERE id=? AND status='PENDING'
                ''', (status, body.get('actual_home'), body.get('actual_away'), now_iso(), pid))
                changed = conn.total_changes
                conn.commit()
                conn.close()
                self._send_json({'updated': changed})
            except Exception as e:
                self._send_json({'error': str(e)}, 500)
            return

        self._send_json({'error': 'Not found'}, 404)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/stats':
            try:
                self._send_json(build_stats())
            except Exception as e:
                self._send_json({'error': str(e)}, 500)
            return

        if path == '/api/predictions':
            try:
                qsd = parse_qs(parsed.query)
                clauses = []
                params = []
                for field in ('status', 'market', 'confidence', 'league'):
                    if field in qsd:
                        clauses.append(f"{field}=?")
                        params.append(qsd[field][0])
                if 'date_from' in qsd:
                    clauses.append("match_date>=?")
                    params.append(qsd['date_from'][0])
                if 'date_to' in qsd:
                    clauses.append("match_date<=?")
                    params.append(qsd['date_to'][0])
                where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
                limit = int(qsd.get('limit', ['500'])[0])
                conn = get_db()
                rows = conn.execute(
                    f'SELECT * FROM predictions {where} ORDER BY match_date DESC LIMIT ?',
                    params + [limit]
                ).fetchall()
                conn.close()
                self._send_json([dict(r) for r in rows])
            except Exception as e:
                self._send_json({'error': str(e)}, 500)
            return

        # Proxy ESPN Search API calls (check this first to avoid prefix collision with /espn/)
        if self.path.startswith('/espn-search/'):
            query_path = self.path[13:]
            espn_url = f"https://site.web.api.espn.com/apis/search/v2{query_path}"
            try:
                with open('server_debug.log', 'a') as f:
                    f.write(f"Path: {self.path}\nURL: {espn_url}\n")
                req = urllib.request.Request(espn_url)
                req.add_header('User-Agent', 'Mozilla/5.0')
                r = urllib.request.urlopen(req, timeout=15, context=ctx)
                data = r.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e), 'traceback': tb}).encode())
            return

        # Proxy ESPN main API calls
        if self.path.startswith('/espn/'):
            espn_path = self.path[6:]  # Remove '/espn/'
            espn_url = f'https://site.api.espn.com/apis/site/v2/sports/{espn_path}'
            try:
                # Log debug info
                with open('server_debug.log', 'a') as f:
                    f.write(f"Path: {self.path}\nURL: {espn_url}\n")
                req = urllib.request.Request(espn_url)
                req.add_header('User-Agent', 'Mozilla/5.0')
                r = urllib.request.urlopen(req, timeout=15, context=ctx)
                data = r.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e), 'traceback': tb}).encode())
            return

        # Serve static files (index.html etc.)
        super().do_GET()

    def log_message(self, format, *args):
        # Cleaner logging
        msg = format % args
        if '/espn/' in msg:
            print(f"  [ESPN Proxy] {msg}")
        elif '/api/' in msg:
            print(f"  [Tracking API] {msg}")
        elif '200' in msg or '304' in msg:
            pass  # Suppress static file logs
        else:
            print(f"  [Server] {msg}")


if __name__ == '__main__':
    init_db()
    print(f"""
====================================================
  SportyBet Multi-Market Scout -- Local Server
====================================================

  Server running at: http://localhost:{PORT}

  Open this URL in your browser to use the agent.
  ESPN form data will load through this local proxy
  (no CORS issues).

  Every pick is now logged to predictions.db so real
  accuracy can be tracked in the "Track Record" tab.

  Press Ctrl+C to stop.
====================================================
""")
    # ThreadingHTTPServer, not HTTPServer: the plain version handles one
    # request at a time and blocks everything else behind a slow/idle
    # connection (e.g. a browser tab left open) -- a real problem once more
    # than one thing talks to this server at once (the UI polling ESPN/odds
    # while the admin-publish button also fires, multiple browser tabs, etc).
    server = http.server.ThreadingHTTPServer(('', PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
