1. Should timestamp inputs accept a numeric UTC offset (such as `+02:00` or `-00:00`) as well as `Z`, keep fractional seconds to microseconds, and always be returned in UTC ending in `Z`?
2. What status does a deadline stage have when its report was submitted after the deadline: `overdue`, or a new `late` status?
3. What should a second submission for the same stage return: 409, 400, replace the first, or keep the first?
4. What should a submission for a `not_applicable` stage return (any stage of a voluntary case, or `final_report` before `fix_available_at` is set)?
5. Should `submitted_at` or `fix_available_at` earlier than the incident's `awareness_at` be rejected with 400?
6. Should timestamps later than the clock's current time be accepted?
7. Can `fix_available_at` be set again on the same incident, and if so, does it overwrite the earlier value?
8. What happens when `fix_available_at` is set on a voluntary incident?
9. What should the CVE query return for a malformed CVE ID such as `CVE-26-1` or `abc`: 400 or 404?
10. When does a component's purl match an affected purl: exact string match, or after removing qualifiers and subpath?
11. Do `affected_purls` list exact versions only, or can they express version ranges?
12. Can a component without a purl ever match a CVE?
13. After `POST /api/v1/test/reset`, what mode and records does the vulnerability source have?
14. Does `PUT /api/v1/test/vulnerability-source` replace all records or add to them?
15. Does an incident's `cve_id` have to be known to the vulnerability source, or is a format check enough?
16. Should the production vulnerability source stay Dependency-Track, or switch to matching against a local OSV snapshot?
17. Are there push alerts for deadlines in Phase 4, or is the status only shown when an incident is read?
18. Is a report submitted exactly at its deadline `met`, and is an unsubmitted stage `pending` at the deadline and `overdue` one second later?
19. May cross-team tests depend on the order of affected releases and matched components?
20. Who on each team checks the expected values in the AC-04 fixtures, and by when?
