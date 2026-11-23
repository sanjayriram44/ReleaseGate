# Cross-team run: our tests against Team 2's service, 2026-11-22

**Tester commit:** `271da8e0e973d0255e0c060a953e9704a6b209eb` (our deployed tester, `http://136.116.160.182:8081`, tag `phase5`)
**Target:** `https://cra-phase3-api-456725640364.us-central1.run.app` (Team 2's final system URL; their contract copy is version 1.1.0, which their `/openapi.json` reports)
**Runner:** `POST /api/v1/runs` on our deployed tester, run `run-0895aea438`, 2026-11-23T02:37:22Z to 02:37:34Z (UTC; 9:37 PM ET on 2026-11-22, inside the window Team 2 proposed). The run resets Team 2's data at the start and the end.
**Result:** 89/89 passed (in scope: every required check, AC-01..AC-09 and the contract; 0 failed, 0 skipped). Informational: 22/22 passed.

Per AC (required): AC-01 9/9, AC-02 5/5, AC-03 6/6, AC-04 6/6, AC-05 3/3, AC-06 5/5, AC-07 6/6,
AC-08 30/30, AC-09 7/7, contract 8/8, setup and teardown 4/4. Informational: AC-08 11/11, AC-09 2/2,
provisional 9/9. The informational checks include every check that rests on the Phase 5 pod answers
(the PUT's report body, the AC-08 edge cases, the audit action names and entity types), so Team 2's
service already matches the answers both teams agreed on 2026-11-22.

Timing: the slowest AC-04 query took 0.09 s (limit 10 s); the AC-05 errors took 0.06–0.07 s (limit 15 s).

**Main problem / owner:** none found.

**Coverage:**
- Code: not measurable; this is a black-box run over HTTP, and Team 2's `/test/report` publishes coverage only per session.
- Component: 14 of 14 contract API operations called (100%).
- System model: AC-01..AC-09 exercised (100% of what a single run can reach). AC-10 needs Team 2 to restart their service, so it runs only as the two-step `python -m tester.ac10 snapshot` / `verify` procedure; not run yet.

**Caveat:** AC-04 and AC-08 compare against `fixtures/ground_truth.json` and `fixtures/report_cases.json`,
which are still drafts until the named checkers sign off (Team 6 AC-04: Donovan Baran, done 2026-11-18;
Team 2 AC-04: Pataraphol Keeraswangporn; Team 2 AC-08: Chris Feng; Team 6 AC-08: not named yet).
