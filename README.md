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
- `.github/workflows/build.yml` - builds `api/` and pushes it to GHCR on
  every push to `main`, so Unraid only ever pulls a finished image.
- `unraid-templates/` - the two containers as Unraid "Add Container"
  templates.

## CI: pushing this to GitHub

1. Push this repo to `github.com/raghalis/Daycare-App`.
2. The first push to `main` that touches `api/**` runs the workflow and
   publishes `ghcr.io/raghalis/access-window-api:latest` (plus a
   `:<commit-sha>` tag for rollback). No secrets to add - it uses the
   built-in `GITHUB_TOKEN`, which already has permission to publish
   packages under your own account.
3. **Make the package public** once it exists: GitHub -> your profile ->
   Packages -> `access-window-api` -> Package settings -> Change visibility.
   Otherwise Unraid needs registry credentials to pull it (Docker settings
   -> add a private registry login) - public is simpler if the code itself
   isn't sensitive.
4. From then on, every merge to `main` that changes `api/` republishes
   `:latest` - that's the whole update mechanism (see below).

## Deploying to Unraid

### Recommended: native "Add Container", one template per service

This matches how you already run your other NPMPlus-fronted apps - each
container gets its own entry in Unraid's Docker tab, with network chosen
from that per-container dropdown, and an "Update Ready" badge that shows up
automatically whenever CI publishes a new `:latest`.

1. **Docker tab -> Add Container -> Template: enter a URL manually**, paste:
   `https://raw.githubusercontent.com/raghalis/Daycare-App/main/unraid-templates/access-window-mediamtx.xml`
   Set its **Network Type** to whatever custom network your NPMPlus and
   other proxied apps already share. Before starting it, create
   `/mnt/user/appdata/access-window/mediamtx.yml` on the array using this
   repo's `mediamtx/mediamtx.yml` as a starting point, with your real camera
   RTSP source(s) filled in.
2. Repeat with:
   `https://raw.githubusercontent.com/raghalis/Daycare-App/main/unraid-templates/access-window-api.xml`
   **Same Network Type as step 1** - the API reaches MediaMTX by container
   name (`access-window-mediamtx`), which only resolves if they're on the
   same Docker network. Fill in the required fields (`SESSION_SECRET`,
   `STREAM_TOKEN_SECRET`, `MEDIAMTX_HLS_BASE_URL`, optionally
   `PUSHOVER_APP_TOKEN`) - the template flags which ones are required.
3. In NPMPlus, add a proxy host for the API's published port (`8000` by
   default) and a second location forwarding `/hls/` to MediaMTX's port
   (`8888`) - see "NPMPlus" below for why HLS, not WebRTC.
4. Bootstrap your own super admin account:
   `docker exec access-window-api python -m app.seed`
   (reads `SEED_SUPER_ADMIN_EMAIL`/`_PASSWORD` from the container's env -
   set those two vars in the template first, or pass them inline for that
   one command). Every other account - including your spouse's `admin`
   account - gets created by that super admin calling
   `POST /api/admin/invites`, not through this script.
5. Updating later is just the normal Unraid flow: when CI publishes a new
   image, both containers show "Update Ready" in the Docker tab - click
   Apply. No SSH, no manual pulls.

### Alternative: Docker Compose

If you'd rather run this on a plain Docker host (or Unraid's Compose
Manager plugin) instead of per-container templates:

```
cp .env.example .env   # fill in the same values as the template above
# edit mediamtx/mediamtx.yml with your real camera source(s)
docker compose pull
docker compose up -d
docker compose exec api python -m app.seed
```

`docker-compose.yml` already points `api` at the published GHCR image (not
a local build) and needs no custom network setup - compose puts both
services on one default network automatically, and `api`'s port `8000` /
mediamtx's port `8888` are published to the host for NPMPlus to reach
directly. `docker compose pull && docker compose up -d` is the update flow
here.

## NPMPlus

Point NPMPlus at this host's published ports rather than joining a shared
Docker network by name - simpler, and works the same whether you deployed
via templates or compose:

1. Proxy host for your parent-facing subdomain -> forward to
   `<unraid-ip>:8000`. Enable SSL (Let's Encrypt) as usual.
2. A `/hls/` location on the same proxy host -> forward to
   `<unraid-ip>:8888`, so camera segments are served from the same origin
   as the app (avoids cross-origin cookie/CORS complications). Match this
   to whatever you set `MEDIAMTX_HLS_BASE_URL` to.

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
- [x] CI build/publish to GHCR + Unraid templates
- [ ] Admin UI frontend (parents, schedule editor, overrides calendar, audit
      log, camera/admin management) - the backend routes under
      `/api/admin/*` already exist; this is wiring a UI to them
- [ ] Multi-camera viewer page (current one assumes one camera per parent)
- [ ] `next_window_start` computation for the "come back at..." messaging
      (currently only `window_end` is calculated)
