# BiteTrace

**Fifteen people get sick from one cart. Nobody connects them. BiteTrace does.**

BiteTrace is a crowdsourced early-warning system for street-food illness outbreaks. People anonymously report "I got sick after eating here". The system clusters reports per stall, tests whether the cluster is statistically unusual, has an AI reviewer double-check it, and, if it holds up, automatically emails an evidence report to the food-safety authority.

Built for OptiForge 2026 (IEEE EMBS x CIS), track 06 Open Innovation.

> **Demo notice.** All venues, cases and the "FSSAI" inbox in this repository are fictional demo data. Emails are labelled `[BiteTrace DEMO]` and go to a team-owned inbox, never to a real authority.

## The problem

Foodborne illness in India is heavily under-reported. Each victim sees a bad stomach; nobody sees that ten strangers ate at the same cart on the same evening. Health authorities usually learn of an outbreak after hospitalisations, days late. BiteTrace links those isolated reports while the cluster is still small enough to act on. (Cite your own sources for national statistics in the slides; this repo does not embed unverified numbers.)

## How it works

```
 phone (static UI, Leaflet map)
        |  POST /api/reports  (anonymous, hashed device id)
        v
 FastAPI ── validation ── anti-abuse weighting ── SQLite / Postgres
        |
        v
 Outbreak engine: cluster (72 h of newest meal) → weighted count
                  → Poisson tail test → level NONE / WATCH / ALERT / OUTBREAK
        |
        v  (level reached OUTBREAK and not already reported)
 AI reviewer (Gemini, rules fallback) → guardrails (AI can only hold back)
        |
        v
 Resend API ── evidence report + FSSAI-ready complaint text ── demo inbox
```

**Statistics.** Each stall has a baseline of 0.2 expected illnesses in the window. With a weighted count *k*, the p-value is P(X ≥ k) for a Poisson variable. Levels: WATCH p<0.05 with ≥2 devices, ALERT p<0.01 with ≥3, OUTBREAK p<0.001 with ≥5. Cases must share an exposure window of 12 hours or the level is capped at WATCH (a real single-source outbreak has coherent meal times).

**AI reviewer.** Claude (or Gemini, whichever key is set) receives only aggregate numbers (counts, p-value, time spread, weights), never stall names or free text, and returns a strict JSON verdict. If the key is missing or the call fails, a rules-based reviewer takes over. Guardrails make the AI one-directional: it can **hold back** a report, but can never push one through that the statistics rejected.

## Anti-abuse precautions

| Threat | Defence |
|---|---|
| One person filing many reports | One vote per device per stall; 3 reports per device per 7 days; salted HMAC device id |
| Bot farms / one network | 15 reports per network per 24 h; a burst of 3+ from one network in 2 minutes is down-weighted to 0.5; 4th+ device from the same network counts 0.3 |
| Fresh throw-away devices | Devices under 24 h old weigh 0.8 |
| Rival stall sabotage | Needs 5 distinct devices, statistical significance and coherent timing; the AI reviewer sees the weights |
| Impossible claims | Illness onset must be 1 to 72 h after the meal; a GI symptom is required |
| Fake location | Reports must be inside the service area (25 km of Shamshabad) |
| Duplicates | Same device and stall suppressed for 24 h |
| Prompt injection | No free text ever reaches the AI; stall names are excluded from the prompt |
| Form bots | Hidden honeypot field and a minimum form-fill time (under 4 s is refused). These stop naive scripts, not a determined attacker calling the API directly |
| Many devices, one person | Signed-in Google users vote as one account across all devices; verified accounts are weighted slightly higher than throw-away devices |
| Email flooding | One email per stall per 24 h unless the level escalates |
| Privacy | IPs and device ids stored only as salted HMACs; public timestamps blurred to 15 minutes; no names, phones or accounts |
| Defamation risk | Reports say "cluster of reports", not "this stall is unsafe"; human authority makes the call |
| XSS / injection | Sanitised names, HTML-escaped emails, parameterised SQL, strict CSP and security headers |

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env
uvicorn app.asgi:app --reload
```

Open <http://localhost:8000>. With no keys it works fully: the map, reporting, detection and the demo tools run, the AI falls back to rules, and emails are logged instead of sent.

Tests and lint:

```bash
pip install -r requirements-dev.txt
pytest          # 123 tests, ~99% coverage
ruff check .
```

## Environment variables

| Name | Purpose |
|---|---|
| `DATABASE_URL` | `sqlite:///bitetrace.db` locally; a Postgres URL (e.g. Neon) on Vercel |
| `SECRET_SALT` | Long random string for hashing. **Required in production** |
| `DEMO_MODE` | `true` shows the demo panel and enables `/api/demo/*` |
| `AUTO_SEND` | `true` sends approved reports automatically |
| `ENFORCE_AREA`, `AREA_CENTER_LAT/LNG`, `AREA_RADIUS_KM` | Service-area check |
| `RESEND_API_KEY`, `REPORT_FROM_EMAIL`, `REPORT_TO_EMAIL` | Email sending. Use `onboarding@resend.dev` as sender for testing; recipient is your demo "FSSAI" Gmail |
| `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` | Claude as the AI reviewer (used first if set; default model `claude-haiku-4-5`) |
| `GEMINI_API_KEY`, `AI_MODEL` | Gemini reviewer, used if no Claude key (`gemini-2.5-flash` default) |
| `GOOGLE_CLIENT_ID` | Enables optional Google sign-in and per-account report history |

Secrets live only in `.env` (git-ignored) or Vercel's environment settings, never in code.

## Real places from OpenStreetMap

The repository ships with fictional demo venues. To load real restaurants and stalls around Shamshabad, run this on your own computer (it needs internet):

```bash
python scripts/fetch_osm_places.py
```

Then delete `bitetrace.db` and restart. The few demo venues that carry the pre-seeded alerts stay on the map, so a real business never shows a fake warning. Map data (c) OpenStreetMap contributors.

### Adding local stalls by hand

Put them in `data/places_manual.json` (same format as `places_osm.json`: name, kind, lat, lng). They are added to the map automatically the next time the server starts, locally or on Vercel, so adding a stall is just an edit and a redeploy.

## Officer demo inbox

`/officer.html` shows what a food safety officer would receive: every alert the system sent, held back or could not deliver. It refreshes itself every few seconds, so it works well beside the map during a live demo.

## Google sign-in (optional)

1. In Google Cloud Console create a project, then *APIs & Services > Credentials > Create credentials > OAuth client ID > Web application*.
2. Under *Authorized JavaScript origins* add `http://localhost:8000` and your `https://<project>.vercel.app` URL.
3. Copy the client ID into `GOOGLE_CLIENT_ID`. The Sign in button then appears. BiteTrace stores only a salted hash of Google's user id, never the email.

## Deploy on Vercel

1. Push this folder to a GitHub repository.
2. Create a free Postgres database at Neon and copy its connection string.
3. In Vercel choose *Add New Project*, import the repo (no build settings needed).
4. Add the environment variables above, including `DATABASE_URL` and `SECRET_SALT`.
5. Deploy. Vercel serves `public/` from its CDN and `/api/*` through `api/index.py`.

No domain purchase is needed; Vercel gives a free `*.vercel.app` URL.

## Project layout

```
app/        backend (config, outbreak engine, anti-abuse, AI review, email, routes)
api/        Vercel serverless entry
public/     static frontend (vanilla ES modules, vendored Leaflet)
data/       fictional seed venues and background cases
tests/      pytest suite
docs/       presentation notes and viva answers
```

## Limitations (stated honestly)

- Crowdsourced signals are noisy; BiteTrace flags clusters for human follow-up and proves nothing about cause.
- Anonymity limits verification; the defences raise the cost of abuse but cannot eliminate it.
- The Poisson baseline is a fixed assumption; a real deployment would calibrate it per area.
- The Vercel deploy, live Resend delivery and live Gemini call require your own keys and were not exercised in the build sandbox.
- The map uses free OpenStreetMap tiles, fine for a demo; for heavy production traffic use a hosted tile provider.
