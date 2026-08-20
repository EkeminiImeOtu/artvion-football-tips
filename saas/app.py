"""
Artvion Football Tips -- the public subscription product.

Free tier: FREE_DAILY_LIMIT highest-confidence predictions from the latest
published scan. Subscribers: everything. Predictions are published by an
admin-only endpoint that the existing (already-tested) browser scanner in
../index.html posts to -- this app never talks to the Odds API or ESPN
itself, it only serves what's already been generated and stored.

Run: uvicorn app:app --reload --port 8000
Requires env vars for billing to work: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
STRIPE_PRICE_ID. See .env.example. ADMIN_TOKEN protects the publish/resolve
endpoints -- set it to something random before exposing this publicly.
"""
import os
import secrets
from datetime import datetime, date
from urllib.parse import urlparse

import psycopg2.extras

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Response, Depends, Header, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auth
import billing
import sports_data
from db import get_db, init_db, now_iso, is_active_subscriber

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FREE_DAILY_LIMIT = int(os.environ.get('FREE_DAILY_LIMIT', '3'))
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN')  # required to publish/resolve picks
SESSION_COOKIE = 'session'
# Origins allowed to call /api/admin/* from a browser (the existing scanner
# runs on its own origin/port). The bearer token is the real security
# boundary here, not CORS -- this just lets the browser make the call at all.
ADMIN_CORS_ORIGINS = os.environ.get('ADMIN_CORS_ORIGINS', 'http://localhost:8888').split(',')

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ADMIN_CORS_ORIGINS,
    allow_methods=['POST', 'GET'],
    allow_headers=['authorization', 'content-type'],
)
app.mount('/static', StaticFiles(directory=os.path.join(APP_DIR, 'static')), name='static')
templates = Jinja2Templates(directory=os.path.join(APP_DIR, 'templates'))


@app.on_event('startup')
def _startup():
    init_db()
    if not ADMIN_TOKEN:
        print("WARNING: ADMIN_TOKEN is not set -- publish/resolve endpoints are disabled until it is.")
    if not billing.billing_configured():
        print("NOTE: Stripe is not configured (STRIPE_SECRET_KEY / STRIPE_PRICE_ID) -- checkout will error until it is.")


# ---------- auth helpers ----------

def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    return auth.get_user_from_session(token)


def require_same_origin(request: Request):
    """Lightweight CSRF guard for cookie-authenticated POSTs: reject cross-site submits."""
    origin = request.headers.get('origin') or request.headers.get('referer')
    if not origin:
        return  # allow same-origin form posts without an Origin header (older browsers)
    host = urlparse(origin).netloc
    expected = urlparse(billing.PUBLIC_BASE_URL).netloc
    if host and expected and host != expected:
        raise HTTPException(status_code=403, detail="Cross-site request rejected.")


def require_admin(authorization: str = Header(default=None)):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Admin endpoints are disabled: ADMIN_TOKEN not configured.")
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization[len('Bearer '):]
    if not secrets.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid admin token.")


# ---------- public pages ----------

@app.get('/', response_class=HTMLResponse)
def landing(request: Request):
    fixtures = sports_data.get_live_scores()[:5]
    news = sports_data.get_news(4)
    _, picks = _fetch_latest_picks()
    return templates.TemplateResponse(request, 'landing.html', {
        'user': current_user(request), 'fixtures': fixtures, 'news': news, 'picks': picks[:3],
    })


@app.get('/pricing', response_class=HTMLResponse)
def pricing(request: Request):
    return templates.TemplateResponse(request, 'pricing.html', {
        'user': current_user(request), 'free_limit': FREE_DAILY_LIMIT,
    })


# ---------- auth pages ----------

@app.get('/signup', response_class=HTMLResponse)
def signup_form(request: Request, next: str = '/dashboard'):
    return templates.TemplateResponse(request, 'signup.html', {'user': None, 'error': None, 'next': next})


@app.post('/signup')
def signup_submit(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form('/dashboard')):
    email = email.strip().lower()
    if len(password) < 8:
        return templates.TemplateResponse(request, 'signup.html', {
            'user': None, 'next': next,
            'error': 'Password must be at least 8 characters.'
        }, status_code=400)
    user_id, error = auth.create_user(email, password)
    if error:
        return templates.TemplateResponse(request, 'signup.html', {
            'user': None, 'next': next, 'error': error
        }, status_code=400)
    token = auth.create_session(user_id)
    resp = RedirectResponse(url=next or '/dashboard', status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite='lax', max_age=30 * 86400)
    return resp


@app.get('/login', response_class=HTMLResponse)
def login_form(request: Request, next: str = '/dashboard'):
    return templates.TemplateResponse(request, 'login.html', {'user': None, 'error': None, 'next': next})


@app.post('/login')
def login_submit(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form('/dashboard')):
    user_id = auth.authenticate(email.strip().lower(), password)
    if not user_id:
        return templates.TemplateResponse(request, 'login.html', {
            'user': None, 'next': next, 'error': 'Incorrect email or password.'
        }, status_code=400)
    token = auth.create_session(user_id)
    resp = RedirectResponse(url=next or '/dashboard', status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite='lax', max_age=30 * 86400)
    return resp


@app.post('/logout')
def logout(request: Request, _: None = Depends(require_same_origin)):
    auth.destroy_session(request.cookies.get(SESSION_COOKIE))
    resp = RedirectResponse(url='/', status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ---------- public predictions (no account, no paywall -- everything open) ----------

def _confidence_sort_key(conf):
    return {'high': 0, 'medium': 1, 'low': 2}.get(conf, 3)


def _fetch_latest_picks():
    conn = get_db()
    try:
        latest = conn.execute("SELECT MAX(scan_date) AS d FROM predictions").fetchone()
        scan_date = latest['d'] if latest else None
        rows = []
        if scan_date:
            rows = conn.execute(
                "SELECT * FROM predictions WHERE scan_date=? AND match_date >= ? ORDER BY match_date ASC",
                (scan_date, date.today().isoformat())
            ).fetchall()
    finally:
        conn.close()
    rows = sorted(rows, key=lambda r: _confidence_sort_key(r['confidence']))
    picks = []
    for r in rows:
        try:
            match_date_fmt = datetime.fromisoformat(r['match_date'].replace('Z', '+00:00')).strftime('%a %d %b')
        except Exception:
            match_date_fmt = r['match_date']
        picks.append({**dict(r), 'match_date_fmt': match_date_fmt})
    return scan_date, picks


@app.get('/predictions', response_class=HTMLResponse)
def predictions_page(request: Request):
    scan_date, picks = _fetch_latest_picks()
    return templates.TemplateResponse(request, 'predictions.html', {'scan_date': scan_date, 'picks': picks})


@app.get('/live-scores', response_class=HTMLResponse)
def live_scores_page(request: Request):
    fixtures = sports_data.get_live_scores()
    return templates.TemplateResponse(request, 'live_scores.html', {'fixtures': fixtures})


@app.get('/news', response_class=HTMLResponse)
def news_page(request: Request):
    articles = sports_data.get_news(20)
    return templates.TemplateResponse(request, 'news.html', {'articles': articles})


# ---------- dashboard: dormant for now (kept for when accounts/billing come back) ----------

@app.get('/dashboard', response_class=HTMLResponse)
def dashboard(request: Request, checkout: str = None):
    user = current_user(request)
    if not user:
        return RedirectResponse(url='/login?next=/dashboard', status_code=303)

    conn = get_db()
    try:
        subscribed = is_active_subscriber(conn, user['id'])
        latest = conn.execute("SELECT MAX(scan_date) AS d FROM predictions").fetchone()
        scan_date = latest['d'] if latest else None
        rows = []
        if scan_date:
            rows = conn.execute(
                "SELECT * FROM predictions WHERE scan_date=? AND match_date >= ? ORDER BY match_date ASC",
                (scan_date, date.today().isoformat())
            ).fetchall()
    finally:
        conn.close()

    rows = sorted(rows, key=lambda r: _confidence_sort_key(r['confidence']))
    visible = rows if subscribed else rows[:FREE_DAILY_LIMIT]
    locked_count = 0 if subscribed else max(0, len(rows) - FREE_DAILY_LIMIT)

    picks = []
    for r in visible:
        try:
            match_date_fmt = datetime.fromisoformat(r['match_date'].replace('Z', '+00:00')).strftime('%a %d %b')
        except Exception:
            match_date_fmt = r['match_date']
        picks.append({**dict(r), 'match_date_fmt': match_date_fmt})

    return templates.TemplateResponse(request, 'dashboard.html', {
        'user': user, 'picks': picks, 'is_subscribed': subscribed,
        'locked_count': locked_count, 'free_limit': FREE_DAILY_LIMIT, 'scan_date': scan_date,
        'checkout_success': checkout == 'success',
    })


# ---------- billing ----------

@app.post('/billing/checkout')
def billing_checkout(request: Request, _: None = Depends(require_same_origin)):
    user = current_user(request)
    if not user:
        return RedirectResponse(url='/login?next=/pricing', status_code=303)
    try:
        url = billing.create_checkout_session(user['email'], user['id'], user.get('stripe_customer_id'))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return RedirectResponse(url=url, status_code=303)


@app.get('/billing/portal')
def billing_portal(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url='/login', status_code=303)
    if not user.get('stripe_customer_id'):
        return RedirectResponse(url='/pricing', status_code=303)
    try:
        url = billing.create_portal_session(user['stripe_customer_id'])
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return RedirectResponse(url=url, status_code=303)


@app.post('/billing/webhook')
async def billing_webhook(request: Request, stripe_signature: str = Header(default=None, alias='stripe-signature')):
    payload = await request.body()
    try:
        event = billing.verify_webhook(payload, stripe_signature)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook verification failed: {e}")

    conn = get_db()
    try:
        obj = event['data']['object']
        etype = event['type']

        if etype == 'checkout.session.completed':
            user_id = obj.get('client_reference_id')
            customer_id = obj.get('customer')
            if user_id and customer_id:
                conn.execute("UPDATE users SET stripe_customer_id=? WHERE id=?", (customer_id, int(user_id)))
                conn.commit()

        if etype in ('customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted'):
            customer_id = obj.get('customer')
            status = obj.get('status', 'inactive')
            period_end = obj.get('current_period_end')
            period_end_iso = datetime.utcfromtimestamp(period_end).isoformat() if period_end else None
            user_row = conn.execute("SELECT id FROM users WHERE stripe_customer_id=?", (customer_id,)).fetchone()
            if user_row:
                conn.execute('''
                    INSERT INTO subscriptions (user_id, stripe_subscription_id, status, current_period_end, updated_at)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        stripe_subscription_id=excluded.stripe_subscription_id,
                        status=excluded.status,
                        current_period_end=excluded.current_period_end,
                        updated_at=excluded.updated_at
                ''', (user_row['id'], obj.get('id'), status, period_end_iso, now_iso()))
                conn.commit()
    finally:
        conn.close()

    return JSONResponse({'received': True})


# ---------- public track record ----------

def _win_rate_str(won, resolved):
    if resolved == 0:
        return 'n/a'
    return f"{round(won / resolved * 100, 1)}%"


@app.get('/track-record', response_class=HTMLResponse)
def track_record(request: Request):
    conn = get_db()
    try:
        rows = conn.execute("SELECT market, status FROM predictions").fetchall()
    finally:
        conn.close()

    total = len(rows)
    won = sum(1 for r in rows if r['status'] == 'WON')
    lost = sum(1 for r in rows if r['status'] == 'LOST')
    resolved = won + lost
    pending = total - resolved
    overall = {'total': total, 'won': won, 'lost': lost, 'resolved': resolved, 'pending': pending,
               'win_rate_str': _win_rate_str(won, resolved)}

    by_market_map = {}
    for r in rows:
        g = by_market_map.setdefault(r['market'], {'total': 0, 'won': 0, 'lost': 0})
        g['total'] += 1
        if r['status'] == 'WON':
            g['won'] += 1
        elif r['status'] == 'LOST':
            g['lost'] += 1
    by_market = []
    for market, g in sorted(by_market_map.items(), key=lambda kv: -kv[1]['total']):
        resolved_m = g['won'] + g['lost']
        by_market.append({'market': market, 'total': g['total'], 'won': g['won'], 'lost': g['lost'],
                           'win_rate_str': _win_rate_str(g['won'], resolved_m)})

    return templates.TemplateResponse(request, 'track_record.html', {
        'user': current_user(request), 'overall': overall, 'by_market': by_market,
    })


# ---------- admin: publish + resolve (called by the existing scanner, not by end users) ----------

@app.post('/api/admin/publish')
async def admin_publish(request: Request, _: None = Depends(require_admin)):
    body = await request.json()
    matches = body.get('matches', [])
    scan_date = date.today().isoformat()
    published_at = now_iso()

    rows = []
    for m in matches:
        for p in m.get('picks', []):
            match_date = m.get('match_date')
            home_team = m.get('home_team')
            away_team = m.get('away_team')
            market = p.get('market')
            display = p.get('display')
            if not (match_date and home_team and away_team and market and display):
                continue
            rows.append((
                scan_date, match_date, m.get('league'), home_team, away_team, market, display,
                p.get('conf'), p.get('odds'), '; '.join(p.get('reasons', []) or []), 'PENDING', published_at
            ))

    conn = get_db()
    try:
        if rows:
            # A real scan can carry hundreds of picks -- one INSERT per row
            # over the network to a remote Postgres adds up to real delay.
            # execute_values sends them all in a single round-trip instead.
            cur = conn.raw_cursor()
            psycopg2.extras.execute_values(cur, '''
                INSERT INTO predictions
                (scan_date, match_date, league, home_team, away_team, market, display, confidence, odds, reasons, status, published_at)
                VALUES %s
                ON CONFLICT(match_date, home_team, away_team, market, display) DO UPDATE SET
                    scan_date=excluded.scan_date, confidence=excluded.confidence, odds=excluded.odds,
                    reasons=excluded.reasons, published_at=excluded.published_at
                WHERE predictions.status='PENDING'
            ''', rows)
        conn.commit()
    finally:
        conn.close()
    return {'ok': True, 'processed': len(rows), 'scan_date': scan_date}


@app.get('/api/admin/pending')
def admin_pending(_: None = Depends(require_admin)):
    """Past-dated PENDING predictions, for the scanner's 'resolve live site
    results' flow to pick up and grade against real final scores."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, home_team, away_team, match_date, market, display FROM predictions "
            "WHERE status='PENDING' AND match_date < ? ORDER BY match_date ASC LIMIT 2000",
            (now_iso(),)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.post('/api/admin/resolve')
async def admin_resolve(request: Request, _: None = Depends(require_admin)):
    body = await request.json()
    pid = body.get('id')
    status = body.get('status')
    if not pid or status not in ('WON', 'LOST'):
        raise HTTPException(status_code=400, detail="id and a resolved status (WON/LOST) are required.")
    conn = get_db()
    try:
        conn.execute(
            "UPDATE predictions SET status=?, actual_home=?, actual_away=?, resolved_at=? WHERE id=? AND status='PENDING'",
            (status, body.get('actual_home'), body.get('actual_away'), now_iso(), pid)
        )
        conn.commit()
    finally:
        conn.close()
    return {'ok': True}
