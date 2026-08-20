# Running Artvion Football Tips

Three separate processes, all local to this machine right now:

| Process | What it is | Port |
|---|---|---|
| `python server.py` (repo root) | Your personal scanner -- the one you paste your Odds API key into and run scans with | 8888 |
| `python -m uvicorn app:app` (in `saas/`) | The public site everyone else sees | 8000 |
| `cloudflared tunnel --url http://localhost:8000` | Makes the public site reachable from the internet | n/a |

None of these survive a reboot or this machine going to sleep. If the site goes
down, it's almost always because one of these three stopped running.

## Starting everything from scratch

```bash
# 1. Personal scanner (repo root)
cd /d/Zoom/sportybet-agent
python server.py

# 2. Public site (new terminal, saas/ folder)
cd /d/Zoom/sportybet-agent/saas
python -m uvicorn app:app --host 127.0.0.1 --port 8000
# (reads saas/.env automatically -- ADMIN_TOKEN etc. don't need to be passed by hand)

# 3. Public tunnel (new terminal)
"/c/Program Files (x86)/cloudflared/cloudflared.exe" tunnel --url http://localhost:8000
```

Step 3 prints a new `https://xxxx.trycloudflare.com` URL **every time you run
it** -- the free tier doesn't give you a stable address. If you restart the
tunnel, the live link changes and you'd need to share the new one.

## Publishing real predictions -- weekly, Sunday night

This is a **weekly** product, not daily: publish once on Sunday night,
covering the coming Monday-through-Sunday week. The site's copy ("This
week's predictions", "updated every Sunday night") assumes this cadence --
if that ever changes, the wording in predictions.html/landing.html/
pricing.html needs to change with it.

The public site never talks to the Odds API or ESPN itself -- it only shows
what's been published to it. Each Sunday night:

1. Open `http://localhost:8888` (the personal scanner).
2. Paste in your own Odds API key (never share this key or paste it anywhere
   else -- it's yours).
3. Set the date range to the coming Monday through Sunday, click **Scan + Analyse**.
4. Once it finishes, open **⚙️ Admin: Publish to Artvion Football Tips**,
   confirm the API URL is your real Render URL (e.g.
   `https://artvion-football-tips.onrender.com`) and the admin token field
   is filled in (it remembers both via your browser's local storage), then
   click **🚀 Publish This Week's Picks**.
5. Refresh the public site -- the week's real picks replace whatever was there.

To grade last week's picks (mark them WON/LOST against real final scores)
before publishing the new week: same panel, **🔄 Resolve Live Site Results**
-- looks up each past-dated PENDING pick via ESPN and resolves it, same
logic as the personal tool's own local resolve flow. Worth running this
before Sunday's publish so the Track Record page stays current.

## Activating a paying subscriber

Real accounts, not a shared passcode -- a customer signs up on the site
themselves (`/signup`), then pays and gets activated manually:

1. Customer pays ₦5,000 on Selar, gets redirected to WhatsApp with a
   pre-filled message. They need to include the **email they signed up
   with on the site** (not just their payment email -- these can differ).
2. Confirm the payment actually landed in your Selar dashboard.
3. In the personal scanner's admin panel, enter that email into
   **✅ Activate Subscriber** (optionally set a custom number of days --
   defaults to 30, matching Selar's monthly billing) and click it.
4. This calls `/api/admin/activate-subscriber`, which requires the email to
   already have an account (if they paid before signing up, ask them to
   sign up first, then re-run this). It writes an active `subscriptions`
   row for that user, and their access shows up next time they load
   `/predictions` -- no code to enter, it's tied to their login.

## Config that matters (`saas/.env`)

- `DATABASE_URL` -- a Postgres connection string. Required; the app won't
  start without it. On Render this is set for you automatically once you
  attach the free Postgres database (see below). Locally, you'd need your
  own Postgres instance to point this at.
- `ADMIN_TOKEN` -- protects the publish/resolve endpoints. Whoever has this
  can publish content to your site. Keep it out of anything you share
  publicly (screenshots, chat logs, etc).
- `PUBLIC_BASE_URL` -- currently `http://localhost:8000`. Only matters for
  Stripe redirects and a CSRF origin check, neither of which are active
  right now (no accounts, no payments -- see below).
- `FREE_DAILY_LIMIT` -- how many free-preview predictions `/predictions`
  shows before the rest are locked behind an active subscription.

## Deploying to Render (the permanent, always-on home)

The database layer was migrated from SQLite to Postgres specifically for
this -- Render's free web services don't keep a local disk between deploys,
so SQLite would lose its data; a real Postgres database doesn't have that
problem. **This migration hasn't been run against a live Postgres yet** --
local Postgres install was blocked in this environment (Docker crashed,
and the direct installer download was also blocked here) -- so treat the
first real deploy as the actual test, and check the deploy logs for errors
on that first boot.

1. Push this repo to GitHub (Render deploys from a repo, not a local folder).
2. In the Render dashboard: **New → Blueprint**, point it at the repo.
   Render reads [`render.yaml`](../render.yaml) at the repo root and creates
   both the web service and the free Postgres database together, already
   wired to each other.
3. Render will ask you to fill in `PUBLIC_BASE_URL` (marked `sync: false` in
   the blueprint since it can't be known until Render assigns your service
   its `.onrender.com` address) -- deploy once first, copy the URL Render
   gives you, then set that as `PUBLIC_BASE_URL` and redeploy.
4. `ADMIN_TOKEN` is auto-generated by the blueprint -- find it in the
   service's Environment tab and copy it into the personal scanner's admin
   panel (the API URL field also needs to change from `http://localhost:8000`
   to your new Render URL).
5. First boot runs `init_db()` automatically and creates the schema in the
   fresh Postgres database -- no manual migration step needed.

Known Render free-tier tradeoff: the web service spins down after a period
of inactivity, so the first visitor after a quiet stretch waits through a
cold start (tens of seconds) before the page loads. Everyone after that is
fast until it goes idle again.

## Deploying to Replit (alternative permanent home)

The repository root includes `.replit`, so Replit can start the public
FastAPI site without needing the Render blueprint. The root-level scanner
remains private and is not started by Replit.

1. Push this project to a private GitHub repository, then import that
   repository into Replit. Do not upload `saas/.env`, database files, logs,
   or the personal scanner's API key.
2. Add a Replit production PostgreSQL database. Replit supplies its
   connection string as `DATABASE_URL`; the app already reads that exact
   environment variable.
3. In Replit Publishing, add production secrets: `ADMIN_TOKEN`,
   `PUBLIC_BASE_URL`, `FREE_DAILY_LIMIT`, `SELAR_LINK`, `WHATSAPP_LINK`, and
   `ADMIN_CORS_ORIGINS`. Add Stripe secrets only when Stripe billing is
   enabled.
4. Publish the app as an Autoscale Deployment. Replit uses the deployment
   command in `.replit` and assigns a public Replit URL.
5. Set `PUBLIC_BASE_URL` to that published URL and set
   `ADMIN_CORS_ORIGINS` to a comma-separated list containing
   `http://localhost:8888` and the public URL. Publish again after changing
   production secrets.
6. Test signup, login, free-preview locking, and a publish from the private
   scanner before sharing the URL. A custom domain can be attached later.

## What's dormant, not deleted

Signup, login, and accounts are live and linked from navigation --
`/predictions` gates on a real per-account `subscriptions` row now, not a
shared passcode (that was the old approach; it's been fully retired since
there's no way to tell paying customers apart from anyone they shared the
code with). Only the Stripe billing code (`/billing/*`) is still dormant --
it needs a real Stripe account and payout method sorted out first (see
conversation history for the Nigeria/Stripe payout discussion). Until then,
activation stays manual: Selar payment -> WhatsApp confirmation -> admin
runs **✅ Activate Subscriber** (see above).

## Known limitations, said plainly

- **Not actually "always on."** This all depends on your PC staying awake
  and these three processes staying alive. Deploying to Render (see above)
  is the fix -- the site keeps running independent of your machine.
- **The tunnel URL is not permanent.** Anyone you send the current link to
  will lose it if the tunnel process restarts.
- **No real predictions are live until you run a scan.** The site currently
  shows an honest "no predictions published yet" empty state everywhere,
  which is correct -- there's no fake data pretending otherwise.
