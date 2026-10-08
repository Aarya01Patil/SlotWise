# Render free deployment

This deploys a synthetic demonstration, not a real clinic service. Render's free web services sleep after 15 minutes idle and have ephemeral filesystems. SQLite bookings, sessions, and promoted runtime policies reset after a restart. Captured reports under `examples/` remain readable and are labeled saved evidence. See [Render free services](https://render.com/docs/free).

## Dashboard route

1. Push this repository to GitHub, then open [Deploy to Render](https://render.com/deploy?repo=https://github.com/Aarya01Patil/SlotWise).
2. Sign in and select the workspace. The Blueprint explicitly selects **Free**, Docker, Singapore, and `/healthz`.
3. Enter **GROQ_API_KEY** in Render's secret environment editor. Never commit it or put it in browser code.
4. Apply the Blueprint and wait for the build. Render supplies the exact hostname; the app binds `$PORT` on `0.0.0.0`.
5. Open the service URL. Check `/healthz`, then book a synthetic general appointment tomorrow morning. Confirm the summary before booking.
6. Evaluation evidence is public; starting a run needs the generated **SLOTWISE_OPERATOR_TOKEN** from the service's environment settings. Enter it only in the Evaluation lab. It is never saved in browser storage. Running live evaluations consumes substantial provider quota.

The public demo limits chat to 60 requests/day per process, 20/hour per address, six/minute, and eight new sessions/hour per address. These small local budgets are a demo safeguard, not distributed rate limiting. The provider may impose tighter limits.

## API route

For authorized automated publishing, save `RENDER_API_KEY` in the local ignored `.env`, not in the Render app's environment. Run `uv run python scripts/deploy_render.py`. The deploy script reads it without printing credentials. Account access is required; a deploy file alone does not mean a service was published.

## Verification and limits

- Health returns `{status: ok, synthetic: true}` without making an LLM call.
- Host and origin checks reject unexpected sites; HTTPS cookies are Secure and HttpOnly.
- A visitor cannot start evaluation without the operator token; no external staff notifications exist.
- Keep one instance: SQLite and session locks are process-local.
- Docker is not installed in the current Windows workspace; the image must be built on Render or a Docker-equipped machine. Dependency lock, wheel build, local server, and public-mode HTTP checks were verified locally.
- To restart locally: `uv run slotwise serve --port 8002`. Public settings stay off locally by default.
