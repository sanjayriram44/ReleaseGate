1. Should timestamp inputs accept a numeric UTC offset (such as `+02:00` or `-00:00`) as well as `Z`, keep fractional seconds to microseconds, and always be returned in UTC ending in `Z`?
   - Proposed answer: Yes to all three; a timestamp with no zone is 400.
2. How do submissions and deadline statuses work: is a report submitted exactly at its deadline `met`; is an unsubmitted stage `pending` at the deadline and `overdue` one second later; what status does a late submission get; and what does a duplicate submission, or one for a `not_applicable` stage, return?
   - Proposed answer: Yes; yes; `overdue` with `submitted_at` set (no new `late` status); 409 for a duplicate (400 if we don't add 409 to the contract) and 400 for a `not_applicable` stage.
3. Which incident timestamps are allowed: should `submitted_at` or `fix_available_at` earlier than `awareness_at` be rejected, should times later than the clock's now be accepted, can `fix_available_at` be set again, and what happens when it is set on a voluntary incident?
   - Proposed answer: Reject earlier times with 400; accept future times; a second value overwrites the first and is audited; on a voluntary incident it's stored but deadlines stay `not_applicable`.
4. What should the CVE query return for a malformed CVE ID such as `CVE-26-1` or `abc` (400 or 404), and does an incident's `cve_id` have to be known to the vulnerability source, or is a format check enough?
   - Proposed answer: 400 `INVALID_REQUEST` (added to the contract); a format check is enough.
5. When does a component's purl match an affected purl (exact string, or after removing qualifiers and subpath), do `affected_purls` list exact versions only, and can a component without a purl ever match?
   - Proposed answer: Exact match after removing qualifiers and subpath; exact versions only; no.
6. After `POST /api/v1/test/reset`, what mode and records does the vulnerability source have, and does `PUT /api/v1/test/vulnerability-source` replace all records or add to them?
   - Proposed answer: `available` with zero records; a PUT replaces all records.
7. Who on each team checks the expected values in the AC-04 fixtures, and by when, and may cross-team tests depend on the order of affected releases and matched components?
   - Proposed answer: One person per team, before the Phase 4 milestone; no, tests compare them as sets.
8. Should the production vulnerability source stay Dependency-Track or switch to matching against a local OSV snapshot, and are there push alerts for deadlines in Phase 4, or is the status only shown when an incident is read?
   - Proposed answer: Switch to a local OSV snapshot (needs instructor sign-off); no push alerts, status is shown on read.
