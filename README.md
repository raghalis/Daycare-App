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
- `api/app/static/` - login, invite-acceptance, single-camera viewer, and an
  `admin/` section (add-a-parent, schedules, overrides, live camera view,
  cameras, admins, audit log) wired to the `/api/admin/*` routes. No build
  step - plain HTML/JS, same as the rest of the app.
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

1. Load the MediaMTX template into Add Container by visiting, in a browser
   logged into the Unraid webGUI:
   `http://<unraid-ip>/Docker/AddContainer?xmlTemplate=https://raw.githubusercontent.com/raghalis/Daycare-App/main/unraid-templates/access-window-mediamtx.xml`
   (Only works once this repo is pushed and public - if you'd rather not
   wait, copy the XML files into
   `/boot/config/plugins/dockerMan/templates-user/` on the flash instead;
   they'll then appear in the **Template** dropdown at the top of Docker ->
   Add Container.) Set its **Network Type** to whatever custom network your
   NPMPlus and other proxied apps already share. Before starting it, create
   `/mnt/user/appdata/access-window/mediamtx.yml` on the array using this
   repo's `mediamtx/mediamtx.yml` as a starting point, with your real camera
   RTSP source(s) filled in.
2. Repeat for the API, same way, swapping in
   `access-window-api.xml`. **Same Network Type as step 1** - the API
   reaches MediaMTX by container name (`access-window-mediamtx`), which
   only resolves if they're on the same Docker network. Fill in the
   required fields (`SESSION_SECRET`, `STREAM_TOKEN_SECRET`,
   `MEDIAMTX_HLS_BASE_URL`, optionally `PUSHOVER_APP_TOKEN`) - the template
   flags which ones are required.
3. In NPMPlus, add a proxy host for the API's published port (`8000` by
   default) and a second location forwarding `/hls/` to MediaMTX's port
   (`8888`) - see "NPMPlus" below for why HLS, not WebRTC.
4. Bootstrap your own super admin account:
   `docker exec access-window-api python -m app.seed`
   (reads `SEED_SUPER_ADMIN_EMAIL`/`_PASSWORD` from the container's env -
   set those two vars in the template first, or pass them inline for that
   one command). Log in with it and you'll land on `/admin/` - every other
   account, including your spouse's `admin` account, gets created from
   there (Admins page for admins, Parents page for parents), not through
   this script.
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
- [x] Admin UI: one guided "add a parent" flow (invite + multi-camera pick +
      schedule, in one form), schedules, overrides, cameras, admins, audit
      log, live camera view for admins (no personal grant needed) - plain
      but complete; no calendar widget for overrides, no bulk actions
- [x] Parent-facing invite acceptance page (was missing entirely - the
      invite link pointed straight at a JSON API endpoint with no UI)
- [x] UTC/local timezone display bug fixed (SQLite drops tzinfo on read;
      timestamps sent to the browser now explicitly carry it)
- [x] Multi-camera viewer (Protect-style: one large player + a switcher strip
      with a live status dot per camera; parents can be assigned several now)
- [x] Login rate limiting (per-email lockout + a coarser per-IP throttle) and
      Pushover alerts on brute-force attempts and logins from a new IP
- [x] Mobile pass: admin's fixed sidebar collapses to a top bar under 780px,
      16px minimum on every input (avoids iOS Safari's auto-zoom-on-focus),
      44px+ tap targets throughout, viewer/login/accept-invite reflowed
- [x] Cameras page fully manages cameras now, including RTSP source - pushes
      to MediaMTX's own runtime config API (`/v3/config/paths/*`) instead of
      requiring a `mediamtx.yml` edit + restart. A sync failure surfaces as a
      warning rather than blocking the save, since I can't fully verify that
      API's exact shape against every MediaMTX version - see the comment in
      `api/app/mediamtx_client.py` for how to check yours if it happens.
- [x] Live View shows a still frame per camera (ffmpeg grabs one directly
      from the RTSP source, cached ~15s), not a live stream per tile - each
      card's "Watch live" opens the real thing in the same page a parent
      gets, via `/viewer.html?preview=<camera_id>` (admin-only; bypasses the
      schedule system the same way Live View itself does)
- [x] Admins get a "Back to admin" link on the viewer page, and land there
      automatically after login
- [x] Multi-quality streaming: a camera can have extra "quality variant" RTSP
      sources (Protect's Medium/Low aliases, say), managed from the Cameras
      page. The API serves a real HLS master playlist when variants exist,
      so hls.js auto-switches quality by bandwidth by default AND exposes a
      YouTube-style manual picker in the corner of the player - one
      mechanism gives both. A camera with no variants plays exactly as
      before, no change needed on existing cameras.
- [ ] `next_window_start` computation for the "come back at..." messaging
      (currently only `window_end` is calculated)
- [ ] SMTP invite delivery (lower priority per your call) - copy/paste the
      link is fine at this scale
- [ ] Recorded footage is explicitly out of scope for this app - handled by
      Protect on request, not stored or served here
