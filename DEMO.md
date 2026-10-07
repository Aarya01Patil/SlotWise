# Recording walkthrough — 3 to 5 minutes

Record with Loom or equivalent after testing. The repository does not contain a fabricated recording or link.

1. **State the scope (15 seconds).** “SlotWise books synthetic clinic appointments through the selected live model provider, with booking authorization in code. The improvement loop adapts one bounded recovery policy.” If running offline, visibly say it is a scripted provider; do not call it live LLM evidence.
2. **Full conversation (60 seconds).** Start a new conversation. Enter “I need a general appointment tomorrow morning.” Select the first offer through text (“The first available appointment, please”) or a card. Show the exact doctor/date/time/location summary. Enter “Yes, but afternoon instead.” Show that the old proposal was discarded. Choose the new offer and explicitly confirm. Show the database-backed receipt. Send “yes” again to demonstrate one booking.
3. **Run baseline and candidate (30–90 seconds plus live API time).** Open Evaluation lab, choose two repetitions, and run the improvement loop. The lab invokes the same loop as `uv run slotwise eval-loop --mode live --repeats 2`. Baseline is immutable even if an earlier policy was promoted. Show live/scripted mode label throughout.
4. **Inspect the failure (45 seconds).** Open “Slot taken before commit.” Before transcript shows offer, patient consent, `SLOT_CONFLICT`, then conservative handoff. Expand tool/consent events and database rows. The first slot belongs to a competing synthetic patient; no appointment was created for the evaluated patient. Outcome fails despite safe refusal.
5. **Explain the reinforcement (30 seconds).** Show JSON patch, prior value, replacement, policy version, and failure evidence. Explain that repair cannot modify code, rubric, scenarios, or consent gates. It is policy adaptation, not reinforcement learning.
6. **Inspect the rerun (45 seconds).** After transcript shows fresh matching alternatives, new selection, new explicit consent, then one receipt. Show score increase, zero regressions, the withheld conflict variant, and unchanged happy-path/safety cases. Explain that rejected candidates preserve active policy.
7. **Own the limits (15 seconds).** “Database evidence catches failures a transcript-only judge misses. This small synthetic suite does not prove clinical suitability or general conversational quality.” Mention AI assistance truthfully using the design note.

Before recording live: configure `.env`, restart, run live eval, and inspect its actual report. If the candidate is rejected, diagnose that outcome; do not present the offline score as a live success. Keep keys and `.env` off screen. Optionally begin with “write binary search code” to show the scheduling-only refusal, then continue a genuine booking in the same conversation. Explain that scope classification is fallible but arbitrary model prose cannot reach the patient.

**Loom link:** add your actual recording URL here after recording.
