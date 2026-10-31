1. Should timestamp inputs accept a numeric UTC offset (such as `+02:00` or `-00:00`) as well as `Z`, keep fractional seconds to microseconds, and always be returned in UTC ending in `Z`?
2. Is a report submitted exactly at its deadline `met`, is an unsubmitted stage `pending` at the deadline and `overdue` one second later, and what status does a report submitted after its deadline get: `overdue`, or a new `late` status?
3. What should a submission return when its stage was already submitted (409, 400, replace, or keep the first), and when its stage is `not_applicable` (a voluntary case, or `final_report` before `fix_available_at` is set)?
4. Should `submitted_at` or `fix_available_at` earlier than the incident's `awareness_at` be rejected with 400, and should timestamps later than the clock's current time be accepted?
5. Can `fix_available_at` be set again on the same incident (overwriting the earlier value), and what happens when it is set on a voluntary incident?
6. What should the CVE query return for a malformed CVE ID such as `CVE-26-1` or `abc` (400 or 404), and does an incident's `cve_id` have to be known to the vulnerability source, or is a format check enough?
7. When does a component's purl match an affected purl (exact string, or after removing qualifiers and subpath), do `affected_purls` list exact versions only, and can a component without a purl ever match?
8. After `POST /api/v1/test/reset`, what mode and records does the vulnerability source have, and does `PUT /api/v1/test/vulnerability-source` replace all records or add to them?
9. Who on each team checks the expected values in the AC-04 fixtures, and by when, and may cross-team tests depend on the order of affected releases and matched components?
10. Should the production vulnerability source stay Dependency-Track or switch to matching against a local OSV snapshot, and are there push alerts for deadlines in Phase 4, or is the status only shown when an incident is read?
