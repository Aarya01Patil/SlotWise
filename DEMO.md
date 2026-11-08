# Short SlotWise recording guide

## Before recording

Use the live app for the real model conversation and the offline app for the repeatable policy loop. They use the same interface, booking rules, and evidence checks; offline uses a scripted provider and does not show LLM quality.

Start two terminals:

```sh
uv run slotwise serve --mode live --port 8002 --fresh-demo
uv run slotwise serve --mode offline --port 8003 --fresh-demo
```

Open `http://127.0.0.1:8002/` for live chat, then `http://127.0.0.1:8003/` for offline evaluation. Keep API keys and operator tokens off screen. Start a new conversation for a clean synthetic schedule.

## Three-minute script

**0:00–0:15 — Scope and mode.** Show the live badge. Say:

> SlotWise books appointments at a synthetic clinic. The model can suggest a tool call, but the runtime controls identity, consent, and database writes. Nothing is sent to a real clinic.

**0:15–0:55 — Multi-turn booking.** Send one message at a time: “I need an appointment,” “general,” “tomorrow,” “morning.” Choose an offered appointment, read the exact summary, then confirm. Show the receipt. Say:

> It asks for missing details. Choosing a time prepares a proposal; the separate confirmation is what permits a booking.

**0:55–1:15 — Correction and scope guardrail.** Before selecting a slot, change morning to afternoon and show the offers update. This recording step demonstrates corrected preferences; it does not demonstrate revoking an already prepared confirmation. If time allows, ask for binary-search code, show the refusal, then send a valid appointment request.

> The first correction changes the search before selection. The app also refuses requests outside appointment scheduling.

**1:15–1:30 — Switch to offline.** Open the offline app and point out the OFFLINE SCRIPTED badge. Say:

> This next run uses a deterministic test double. It demonstrates the evaluation and policy update, not live model quality.

**1:30–2:35 — Run and inspect the loop.** In Evaluation lab, click **Run improvement loop** and wait for completion. Inspect the slot-conflict case before and after. Expand **Assertions**, **Tool & consent events**, and **Database rows** on the candidate. Show that conflict cleared the old consent, refreshed alternatives, collected new consent, and created a matching booking row. Open the JSON patch and show its evidence reference. Say:

> The baseline hands off after a slot conflict even though matching alternatives remain. The evaluator records that failure. A bounded patch changes the recovery policy to refresh alternatives and ask for a new confirmation. The repair cannot change the safety rules or the test suite.

**2:35–3:00 — Scores and limits.** Show the result and a withheld conflict variant. Read the numbers displayed. The verified two-repeat offline result is 94.67 to 100, with passes rising from 26/30 to 30/30 and zero regressions. Say:

> Promotion requires the target fix, a higher score, no safety violations, and no previously passing assertion to regress. My saved live Groq candidate was rejected after a preference-change failure, so I’m not claiming a successful live improvement. The offline result validates the harness mechanics only.

End on `DESIGN.md` and say:

> AI helped with implementation, tests, and debugging. I kept the scope to synthetic appointment booking, strengthened the guardrails after testing valid requests, and kept the live failure visible instead of presenting it as a win. A real clinic would need verified patient identity and a durable booking integration.

## Editing the existing recording

The local `SlotWise_demo.mp4` is about eight minutes. It already shows the live booking, corrections, refusal examples, offline rerun, patch, scores, and the rejected live result. Trim long typing and pauses to about five minutes if you keep it. Correct the line around 1:11: the visible preference change happens **before** slot selection, so it does not show revoking a pending confirmation. For stronger evaluator evidence, make a short pickup showing the candidate's passing assertions, tool/consent events, and database rows expanded, plus the withheld conflict case. Preserve the explicit live/offline distinction and the honest live rejection.

Upload the final MP4 to a shareable location, test the viewer link in a signed-out window, then paste that link into the recording URL field and `SUBMISSION.md`. The local file path alone is not accessible to reviewers.
