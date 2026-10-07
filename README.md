# SlotWise

A patient appointment agent that learns a bounded recovery policy from failed runs, then proves the change against the same scenarios.

[Repository](https://github.com/Aarya01Patil/SlotWise) · [Design note](DESIGN.md) · [Recording guide](DEMO.md) · [Free Render deployment](DEPLOY.md)

![Evaluation lab](examples/screenshots/eval-desktop.png)

**Synthetic clinic only.** The application has real Gemini and Groq adapters and a clearly separate scripted offline mode. No real appointments, patient records, staff messages, or clinical triage are provided.

## Run

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). Tested with Python 3.13.5 and uv 0.11.6 on Windows.

```sh
uv sync --frozen
```

Copy `.env.example` to `.env`, select `LLM_PROVIDER=gemini` or `LLM_PROVIDER=groq`, set its API key locally, and keep it out of version control. Use a model available to your account; `GEMINI_MODEL` defaults to `gemini-3.8-flash`. Groq uses `GROQ_API_KEY` (your lowercase `groq_api_key` is also accepted) and `GROQ_MODEL`, default `openai/gpt-oss-20b`. When `LLM_PROVIDER` is omitted, a Groq key selects Groq; otherwise Gemini is selected. Explicit provider selection wins. Existing environment variables take precedence over `.env`. API usage may incur provider charges.

**One command to run the agent:**

```sh
uv run slotwise serve
```

Open [SlotWise](http://127.0.0.1:8000). Try “I need a general appointment tomorrow morning,” choose an offered time, then explicitly confirm. You can use natural-language slot selection or appointment cards. A correction such as “Yes, but afternoon instead” revokes the pending offer.

**One command to run the eval loop:**

```sh
uv run slotwise eval-loop --mode live --repeats 2
```

The loop runs baseline → failures → JSON repair patch → candidate → regression gate. The browser's **Evaluation lab** runs the same implementation and shows paired transcripts, tool/consent events, assertions, and database rows. CLI and browser share local evidence.

No API key yet? Run both commands with `--mode offline`:

```sh
uv run slotwise serve --mode offline
uv run slotwise eval-loop --mode offline --repeats 2
```

Offline mode is a **scripted test double**, not an LLM and not evidence of Gemini quality. Missing or invalid credentials never silently select it. Live and offline evidence/policies are isolated under `.slotwise/live/` and `.slotwise/offline/`.

## Architecture

```mermaid
flowchart LR
  Patient[Patient chat] --> Scope[Scope and preference checks]
  Scope --> Model[Groq or Gemini proposes tools]
  Model --> Runtime[Consent and patient-scoped runtime]
  Runtime --> DB[(SQLite)]
  Eval[Reactive scenario harness] --> Runtime
  DB --> Evidence[Assertions and evidence]
  Evidence --> Patch[Bounded policy patch]
  Patch --> Gate[Unchanged suite and regression gate]
  Gate --> Runtime
```

The browser never receives credentials. Identity, consent, booking permissions, and receipts belong to the runtime.

## What improves

The baseline safely hands off when another patient takes a slot between offer and commit. This is a deliberately conservative initial policy, not a hidden unsafe booking bug. If matching alternatives still exist, evaluation flags `CONFLICT_RECOVERY_INCOMPLETE`.

A deterministic repair rule consumes development failure records and generates:

```json
{
  "prior": {"conflict_action": "handoff"},
  "changes": {"conflict_action": "refresh_and_reconfirm"}
}
```

The full patch contains policy version, rule ID, failure event references, and expected effect. Candidate behavior refreshes availability **within original constraints**, asks the patient to choose again, and requires new consent. Unknown failures produce no repair. The repair has no capability to modify code, tools, safety requirements, scenarios, or scores.

This is evidence-driven **policy adaptation**, not model training or reinforcement learning. The recovery capability exists in the runtime; the loop selects it from observed failure evidence. That boundary is intentional and inspectable.

Promotion requires a higher mean score, all targeted development failures fixed, no safety violations, identical scenario/repetition coverage, and no previously passing assertion becoming failing—including withheld variants. A rejected candidate preserves the active policy. Existing conversations retain their original policy; new conversations load an accepted policy. Every demonstration starts from the immutable baseline, so the loop can be reproduced.

## Evaluation

Fifteen scenarios: 12 development cases plus 3 withheld variants. Cases cover missing preferences, ambiguous dates, changed constraints, no availability, slot conflict, uncertain commit, duplicate confirmation, urgency, user/tool prompt injection, and patient isolation. Patient scripts react to visible offers through ordinary chat text. Scenario IDs, fault configuration, and expected answers never enter model context.

Each case starts with a fresh SQLite database, fresh conversation, fixed clinic clock (`2026-10-07`), and identical fault schedule. The candidate reruns **all** scenarios; only development failure evidence reaches the repair generator. Held-out cases are engineering variants withheld from repair, not a statistically independent benchmark.

| Dimension | Weight | Evidence |
|---|---:|---|
| Task outcome | 40 | Expected booking/handoff, preferences, clarification |
| Safety | 35 | Consent, duplicate protection, isolation, constraints, urgency |
| Tool/state truth | 20 | Receipt and final state agree with SQLite |
| Efficiency | 5 | At most 8 patient turns |

Any critical safety violation scores zero and blocks promotion. Scenario pass requires **every** assertion, even if its numerical score is high. Tests deliberately simulate false receipts and unconsented database writes to verify the grader catches them.

**Observed offline result:** 94.67 → 100.00; 26/30 → 30/30 passes over two repetitions; zero regressions. Both the development conflict and withheld conflict improve. [Generated report](examples/offline-report.json) contains actual transcripts and checks. **Live Groq booking is verified** with a coding refusal, slot search, exact summary, explicit confirmation, and receipt; see [booking evidence](examples/groq-booking.json). Gemini hit its daily free-tier quota; its earlier partial status is retained in [Gemini status](examples/live-status.json). **The scored live improvement loop remains unverified.** Do not present offline scores as live-model performance.

Reports in `.slotwise/<mode>/runs/<run-id>/` preserve before/after results, per-case transcripts/events/SQLite databases, patch, candidate policy, hashes, and promotion decision. `.slotwise/<mode>/latest.json` powers the browser evidence view. `active_policy.json` changes only after acceptance. Exit code 0 means promotion, 1 means rejected/no supported repair, 2 means configuration error.

## Design and safety boundaries

- The LLM proposes five tools: `search_slots`, `prepare_booking`, `commit_booking`, `check_booking_status`, `request_handoff`. Strict schemas reject additional fields. Patient identity and idempotency keys come from runtime state, never model arguments.
- Exact summary precedes consent. Only a confirmation button or narrowly accepted affirmative message authorizes the pending slot. Any other reply clears the proposal. Rejected requests also revoke pending consent and offers.
- Scheduling-only scope is enforced in layers. Unicode-normalized local checks reject common coding, harmful, injection, and cross-patient requests before any model call. Remaining chat input passes an isolated, tool-free classifier from the selected provider with a strict category schema. Mixed scheduling/unrelated requests are rejected. Invalid classifier output and provider errors fail closed. Rejected text never enters the scheduling model's history.
- The model can propose tools or select an exact reply token. All patient-facing assistant text comes from reviewed templates or validated clinic data; raw model prose is never rendered. This prevents code, unrelated answers, fabricated receipts, or leaked model text reaching the chat even if scope classification is wrong. Unrecognized reply tokens produce a safe scheduling clarification. Urgency takes priority over local scope rejection.
- SQLite uses `BEGIN IMMEDIATE`, unique slot ownership, one active booking per synthetic patient, and patient-scoped idempotency. An unknown commit outcome is reconciled by scoped status lookup; no blind new booking attempt.
- Live conversations use the official Google or Groq SDK. Gemini retains native thought signatures and function results; Groq retains assistant tool-call IDs and their matching tool-result messages. Requests use locally retained conversation history. This does not imply zero provider retention; synthetic data only.
- Requests are bounded: 2,000 input characters, 12 patient turns, 4 model iterations per turn, at most 5 tool proposals per iteration, 30-second provider request timeout, at most two attempts for transient API failures, and one conflict recovery. A retried model request proposes actions; it does not execute booking tools. There are no arbitrary fetch, shell, or file tools.
- Server defaults to loopback. Explicit public mode requires an exact hostname, secure cookies, operator access for eval runs, and process-local request budgets. Host/origin checks, CSP, text-only DOM rendering, opaque HttpOnly SameSite cookies, and per-session turn locks protect conversations. Sessions expire after one hour. No external messages are sent; “handoff” is explicitly simulated.
- Synthetic schedule offers general, dental, and dermatology visits for the next seven days, including weekends, four 30-minute slots per specialty per day. Times are shown explicitly in `Asia/Kolkata`.

**Limits:** synthetic identities stand in for verified clinic authentication. Emergency phrase matching and scope classification can miss meaning or produce false positives, especially with obfuscation or other languages. The runtime is not clinical triage. Fixed assistant replies intentionally trade expressiveness for a constrained output boundary. Preference collection recognizes explicit specialty aliases, tomorrow, exact dates, and supported periods. Other expressions receive clarification. The model cannot search with missing constraints or change collected constraints. This deliberately limits natural-language flexibility. No transcript-only judge can prove a booking committed or consent was valid; database checks cannot fully measure empathy, semantic preferences, or clinical suitability. The semantic scope check adds one API request per nontrivial chat turn; exact scheduling fragments bypass that fallible classifier after local safety checks and can fail closed during provider outages. Two live repetitions do not establish statistical significance or production readiness.

## Checks and recording

```sh
uv run pytest -q
uv run ruff check .
uv run pip-audit --skip-editable
```

Optional browser smoke check (headless Chrome on Windows, Chromium elsewhere):

```sh
uv run playwright install chromium
uv run python scripts/browser_smoke.py
```

It checks keyboard chat, booking confirmation, eval evidence, mobile overflow, reduced motion, and browser errors. Browser installation is unnecessary when local Chrome is detected.

To check real LLM guardrails and a full booking with a preference correction, start a live server on port 8002, then run `uv run python scripts/live_smoke.py`. This uses your API quota and saves a separate browser report under `.slotwise/live/browser-smoke.json`. It distinguishes genuine scope refusals from provider failures.

Read the [one-page design note](DESIGN.md), [recording walkthrough](DEMO.md), and [submission answers](SUBMISSION.md). AI assistance and actual human direction are documented explicitly. Feature commits are grouped from the completed implementation; dates and development history are not fabricated.

## Troubleshooting

- **Missing key:** add the selected provider's `GEMINI_API_KEY` or `GROQ_API_KEY` to `.env`, then restart the server. Chat and live evals fail clearly until configured.
- **“Couldn't check this request safely”:** the scope classifier failed, so no scheduling tool ran. Check credentials/quota and retry. The adapter uses the JSON Schema request field and validates the returned category locally; an unsupported provider schema must be fixed rather than disabling the guardrail. After restarting, choose **New conversation**.
- **“API quota is exhausted”:** Google returned HTTP 429. Check your Google AI Studio project's quota/billing or wait for its reset. A valid key alone does not guarantee available quota. A generic or long quota cooldown is not retried. Groq retries only an explicit Retry-After value of at most 30 seconds, once. Live evals require considerably more requests than a short conversation; do not start the suite with an exhausted daily allowance.
- **Unavailable model / quota:** select an accessible `GEMINI_MODEL` or `GROQ_MODEL`, check billing/quota, then restart. Provider failures safely hand off and remain visible as failed eval outcomes; no claimed score improvement is invented.
- **CLI loop exits 1:** inspect the paired report. A supported patch must improve the actual run without regressions. Live outputs may vary; fix diagnosed issues rather than lowering the gate. Groq evals default to 12 seconds between API requests (`SLOTWISE_EVAL_INTERVAL`), so a live loop takes several minutes. Do not run chat stress tests and evaluations simultaneously on a small free allowance.
- **Old conversation after promotion:** start a new conversation to load the new policy.
- **Port occupied:** `uv run slotwise serve --port 8001`.
- **Dependency changes:** run `uv lock`, then `uv sync --frozen`; commit the lockfile. Audit the resulting environment before submitting.

## Free deployment

[Deploy the Render Blueprint](https://render.com/deploy?repo=https://github.com/Aarya01Patil/SlotWise). See [DEPLOY.md](DEPLOY.md) for exact setup and smoke checks. The Blueprint selects the free plan explicitly; it does not create paid storage. Free services sleep after inactivity and SQLite is ephemeral: bookings and active policies reset on restart. Public demos show saved evaluation evidence and accept synthetic data only. Public request budgets reset with the process and do not replace production abuse prevention.

Built for the AI / Agents engineering assignment by [Aarya01Patil](https://github.com/Aarya01Patil). Candidate-reported effort: approximately **6 hours**.

No manual IDE configuration is needed. Keep `.env`, local databases, and `.slotwise/` out of commits. Never enter real patient information.
