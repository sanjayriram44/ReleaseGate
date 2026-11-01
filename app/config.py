import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = "./data/releasegate.db"
    enable_test_endpoints: bool = False
    # Commit the image was built from (GIT_SHA build arg), reported by /health (§16.1).
    commit: str = "unknown"
    # Vulnerability source (CLAUDE.md §6.1). Only "fixture" is built: the production source
    # (a local OSV snapshot) waits for instructor sign-off (docs/decisions.md, Q8).
    vuln_source: str = "fixture"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=os.environ.get("DB_PATH", cls.db_path),
            enable_test_endpoints=os.environ.get("ENABLE_TEST_ENDPOINTS", "").lower() == "true",
            commit=os.environ.get("GIT_SHA", "").strip() or cls.commit,
            vuln_source=os.environ.get("VULN_SOURCE", "").strip() or cls.vuln_source,
        )
