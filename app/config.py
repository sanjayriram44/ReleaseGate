import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = "./data/releasegate.db"
    enable_test_endpoints: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=os.environ.get("DB_PATH", cls.db_path),
            enable_test_endpoints=os.environ.get("ENABLE_TEST_ENDPOINTS", "").lower() == "true",
        )
