# Recording script and workflow

## Readiness: distinguish implementation from evidence

The agent, scoped tools, evaluator, bounded policy repair, and regression gate are implemented. A real Groq conversation and consent-gated synthetic booking have been verified on Render.

| Evidence | Baseline | Candidate | Decision |
|---|---:|---:|---|
| Offline scripted provider, two repetitions | 94.67; 26/30 pass | 100; 30/30 pass | Promoted; zero regressions |
| Live Groq, one repetition | 94.67; 13/15 pass | 93.33; 14/15 pass | Rejected; changed-preference regression |

A successful live improvement without regressions has **not** been demonstrated. The offline result validates harness and policy mechanics; it does not establish live LLM improvement. Do not claim the complete assignment is proven yet. The final recording URL is also still pending.

## Preferred workflow for the final submission

1. Fix and investigate the live changed-preference failure. Preserve the rejected report and keep the scenario assertions and safety gate intact.
2. With the local Groq key configured, run `uv run slotwise eval-loop --mode live --repeats 1`. Inspect the actual paired report. Proceed with a successful-live-loop recording only if promotion is accepted, the target passes, and there are zero regressions. One repetition closes a demonstration loop; it is not statistical validation. Use two repetitions when quota allows.
3. Open the local live app at `http://127.0.0.1:8002/` (start with `uv run slotwise serve --mode live --port 8002` if needed). The public app at `https://slotwise-szrx.onrender.com` also supports conversations; public eval runs need an operator token. Enter any token **before** recording.
4. Record one browser window with Loom or another recorder. Keep `.env`, provider dashboards, Render Environment settings, and tokens off screen. Record a real run; if API waits are cut, label the cut as a shortened wait.
5. Follow the four-minute script below. Do not substitute a stored report for a new run without saying it is saved evidence.
6. Upload the actual recording, test its link in a signed-out/private window, and put the URL in `SUBMISSION.md` and the README.

## Four-minute script

**0:00–0:20 — Scope.** Show the live mode badge and say:

> SlotWise schedules one appointment at a synthetic clinic. Groq proposes tools; the runtime owns patient identity, consent, and the actual booking. No real clinic or staff connection exists.

**0:20–1:15 — Full multi-turn conversation.** Click New conversation. Send these separately, waiting for each reply:

- I need an appointment.
- General.
- Tomorrow.
- Morning.

Choose an offered appointment card. Pause on the exact doctor, date, time, duration, and location. Then click Confirm appointment and show the reference. Say:

> Missing preferences are clarified rather than guessed. Choosing a slot only prepares a proposal. Explicit confirmation is a separate step, and the receipt comes from SQLite.

Optionally demonstrate a preference correction before confirmation after checking it works in the dry run; show the previous proposal disappearing. A coding refusal can be shown briefly, but is not the main demonstration.

**1:15–1:40 — Run the evaluation.** Open Evaluation lab, choose one or two repetitions, and click Run improvement loop. Say:

> Twelve development scenarios and three variants withheld from repair cover conflicts, uncertain commits, duplicate confirmation, changed preferences, urgency, and injection. Each gets a fresh database and fixed clock and faults. Scores check tools, consent events, and database rows, not just friendly text.

Show the run starting and progressing. Shorten long live API waits transparently.

**1:40–2:25 — Inspect the failure.** Inspect Slot taken before commit. Show the before transcript and expand tool/consent events and database rows. Say:

> The baseline hands off safely when another patient takes the slot. No unauthorized booking occurs, but the task fails because matching alternatives still exist. The evaluator records CONFLICT_RECOVERY_INCOMPLETE.

**2:25–3:00 — Show the structured improvement.** Show the generated JSON patch and evidence references. Say:

> Development failure evidence generates a bounded policy patch: handoff becomes refresh_and_reconfirm. The patch includes the prior value, proposed value, expected effect, and evidence. It cannot change executable code, consent rules, scenarios, or scoring. This is policy adaptation, not model training.

**3:00–3:40 — Inspect the rerun and gate.** Show the after conflict transcript: fresh matching offers, new selection, fresh explicit consent, and one booking. Then show the actual aggregate before/after scores, promotion decision, zero regressions, and withheld conflict case. Say:

> The same complete suite is rerun. Promotion requires a higher aggregate score, a fixed target, no safety violations, and every previously passing assertion still passing. A rejected candidate leaves the active policy unchanged.

Read the actual score shown; do not memorize or invent a successful live number.

**3:40–4:00 — Limits and AI use.** Show DESIGN.md and say:

> Database checks catch failures a transcript-only judge misses, but this small suite does not prove empathy or clinical suitability. Production would require clinic-verified patient authentication. AI helped with implementation, tests, and debugging; my testing pushed stronger scope guardrails and corrected a valid scheduling reply that was wrongly refused.

## Honest walkthrough possible with the current evidence

Until a live candidate passes, record the live conversation above, then explicitly switch to a local offline app:

```sh
uv run slotwise serve --mode offline --port 8003
```

Open `http://127.0.0.1:8003/`, show the OFFLINE SCRIPTED badge, and run the loop in its Evaluation lab with two repetitions. Say:

> This section uses a scripted test double. It demonstrates the evaluation, structured patch, and regression gate. The measured score is 94.67 to 100, with 26/30 to 30/30 passes and zero regressions. It does not prove live-model improvement. The live candidate was rejected, and that result is preserved separately.

Then inspect the same failure, patch, and rerun as described above. This is a truthful partial-evidence walkthrough, **not** a substitute for demonstrating the complete live-agent improvement requirement.

**Recording URL:** pending an actual recording.
