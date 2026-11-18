"""Shared-contract operations this build deliberately doesn't serve yet (Phases 4 and 5).

The contract test fails when one of these appears without being removed here, and the
post-deploy check skips or excuses them. Remove each operation as it's built.
"""

NOT_YET_IMPLEMENTED: frozenset[tuple[str, str]] = frozenset()
