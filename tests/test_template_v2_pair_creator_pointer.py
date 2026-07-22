"""Verify Python quick-start documentation points to the shared pair creator.

The Python runtime wizard remains responsible for configuring and running an
existing backend checkout. New application generation belongs exclusively to
the Flutter repository's safe interactive/non-interactive Template V2 creator.
"""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_quick_start_points_to_shared_pair_creator() -> None:
    """Require both Python quick-start guides to identify the safe creator.

    Returns:
        None after verifying PowerShell/Bash entry points, management guidance,
        and the explicit existing-checkout boundary.
    """

    documents = (
        (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8"),
        (REPOSITORY_ROOT / "docs" / "QUICK_START.md").read_text(encoding="utf-8"),
    )
    for content in documents:
        assert "flutter_app_template" in content
        assert "quick-start-v2.ps1" in content
        assert "quick-start-v2.sh" in content
        assert "manage" in content
        assert "backend checkout" in content
        assert "must not" in content or "do not generate" in content
