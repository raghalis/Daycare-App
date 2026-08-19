# Access Window

Private, scheduled camera viewing for daycare parents, built on your own
UniFi Protect RTSP streams. Full design rationale lives in the design spec
artifact from the planning conversation; this README covers running what's
scaffolded so far.

## What's here

- `mediamtx/` - MediaMTX config: pulls RTSP from your cameras, re-publishes
  as HLS, and calls the API before letting any viewer connect through.
- `api/` - FastAPI backend: login, invites, stream-token issuance, the
  MediaMTX auth hook, admin endpoints, and camera-health polling with
  Pushover alerts.
- `api/app/static/` - a minimal login + single-camera viewer page, enough to
  prove the full gate-flow end to end. No admin UI frontend yet (see "What's
  next").

## First run

1. `cp .env.example .env` and fill in every `change-me` value, plus:
   - `MEDIAMTX_HLS_BASE_URL` - the public HTTPS URL NPMPlus will front
     MediaMTX's HLS output as (see below).
   - `PROXY_NETWORK_NAME` - the Docker network your NPMPlus container is on
     (`docker network ls`, or `docker inspect <npmplus-container>` and look
     at `.NetworkSettings.Networks`).
   - `PUSHOVER_APP_TOKEN` - create a Pushover "Application" at
     pushover.net/apps/build; this is that app's token, shared by the whole
     system. Each admin's personal *user* key gets set later via
     `PATCH /api/admin/users/{id}`, not here.
2. Edit `mediamtx/mediamtx.yml` - replace the placeholder camera block with
   your real RTSP source(s), one `paths:` entry per camera.
3. `docker compose up -d --build`
4. `docker compose exec api python -m app.seed` - creates your first
   `super_admin` account from `SEED_SUPER_ADMIN_EMAIL`/`_PASSWORD`. Every
   other account (including your spouse's `admin` account) gets created by
   calling `POST /api/admin/invites` as that super admin, then visiting the
   returned `/invite/{id}` link.
5. Add a matching `Camera` row for each `mediamtx.yml` path
   (`POST /api/admin/cameras`) and at least one `AccessGrant`
   (`POST /api/admin/grants`) so there's something to view.

## NPMPlus

This stack doesn't run its own reverse proxy - it expects your existing
NPMPlus to front it, same as your other hosted apps.

1. In NPMPlus, add a Proxy Host pointing at the `api` container (port
   `8000`) for whatever subdomain you want parents to use. NPMPlus and this
   stack's containers need to share a Docker network for NPMPlus to reach
   `api` by container name - that's what `PROXY_NETWORK_NAME` in `.env` is
   for. Enable SSL (Let's Encrypt) as usual.
2. Add a second location on the same proxy host forwarding `/hls/` to
   `mediamtx:8888`, so camera segments are served from the same origin as
   the app (avoids cross-origin cookie/CORS complications). Match this path
   to whatever you set `MEDIAMTX_HLS_BASE_URL` to in `.env`.

### WebRTC & NPMPlus

The original design leaned WebRTC-primary for sub-second latency. This
scaffold ships **HLS only** (5-15s latency) instead, on purpose: NPMPlus
(nginx) proxies HTTP/HTTPS cleanly, but MediaMTX's WebRTC media transport is
UDP/ICE, which a standard reverse proxy can't forward. Getting WebRTC
working would mean either forwarding a UDP port directly on your router
(bypassing NPMPlus for just that port) or standing up a TURN relay - both
solvable, but out of scope for the initial scaffold. Worth revisiting once
the HLS path is proven out and the added latency is actually a problem in
practice.

## What's next

Following the design doc's build order, roughly in this shape:

- [x] MediaMTX config + API skeleton + schema
- [x] Login, invite flow, stream-token issuance
- [x] MediaMTX auth hook (`/internal/validate`)
- [x] Camera health polling + Pushover alerts
- [x] Bare viewer page (single camera, HLS, countdown banner, end/offline card)
- [ ] Admin UI frontend (parents, schedule editor, overrides calendar, audit
      log, camera/admin management) - the backend routes under
      `/api/admin/*` already exist; this is wiring a UI to them
- [ ] Multi-camera viewer page (current one assumes one camera per parent)
- [ ] `next_window_start` computation for the "come back at..." messaging
      (currently only `window_end` is calculated)
