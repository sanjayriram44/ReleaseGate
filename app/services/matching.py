"""Which stored releases contain a CVE's affected purls (REQ-03), grouped by support status."""

import logging
import sqlite3
from collections import defaultdict
from datetime import date

from app.clock import Clock
from app.models import AffectedRelease, AffectedReleaseResult, Component
from app.services.releases import support_status

log = logging.getLogger("releasegate.matching")


def normalize_purl(purl: str) -> str:
    """Decision Q5: compare purls without qualifiers (?...) and subpath (#...)."""
    return purl.split("#", 1)[0].split("?", 1)[0]


def affected_releases(
    conn: sqlite3.Connection, clock: Clock, cve_id: str, affected: frozenset[str]
) -> AffectedReleaseResult:
    wanted = {normalize_purl(p) for p in affected}
    matches: dict[str, list[Component]] = defaultdict(list)
    releases: dict[str, sqlite3.Row] = {}
    unmatchable = 0
    rows = conn.execute(
        "SELECT r.release_id, r.product, r.version AS release_version, r.support_end_date,"
        " c.name, c.version, c.purl FROM components c JOIN releases r USING (release_id)"
    ).fetchall()
    for row in rows:
        if row["purl"] is None:  # decision Q5: no purl, no match
            unmatchable += 1
            continue
        if wanted and normalize_purl(row["purl"]) in wanted:
            releases[row["release_id"]] = row
            matches[row["release_id"]].append(
                Component(name=row["name"], version=row["version"], purl=row["purl"])
            )
    if unmatchable:
        log.info("%s: %d stored components have no purl and can't match", cve_id, unmatchable)

    result = AffectedReleaseResult(cve_id=cve_id, supported=[], unsupported=[])
    ordered = sorted(
        releases.values(), key=lambda r: (r["product"], r["release_version"], r["release_id"])
    )
    for row in ordered:
        end = date.fromisoformat(row["support_end_date"])
        entry = AffectedRelease(
            release_id=row["release_id"],
            product=row["product"],
            version=row["release_version"],
            support_end_date=end,
            matched_components=sorted(
                matches[row["release_id"]], key=lambda c: (c.name, c.version, c.purl or "")
            ),
        )
        group = (
            result.supported if support_status(end, clock) == "supported" else result.unsupported
        )
        group.append(entry)
    return result
