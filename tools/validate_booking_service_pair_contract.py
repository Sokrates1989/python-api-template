"""Validate and summarize the Python-owned Booking Service pair contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPOSITORY_ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from booking_service_contract import (  # noqa: E402
    BookingServiceContractError,
    validate_booking_service_pair_contract,
)


def main() -> int:
    """Validate the canonical contract and print a sanitized identity summary.

    Returns:
        Process status: zero when the contract is valid, otherwise one.

    Side Effects:
        Reads the canonical contract and writes sanitized JSON to stdout or a
        stable validation message to stderr.
    """

    try:
        identity = validate_booking_service_pair_contract(REPOSITORY_ROOT)
    except BookingServiceContractError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "app_id": identity.app_id,
                "contract_id": identity.contract_id,
                "contract_revision": identity.contract_revision,
                "contract_version": identity.contract_version,
                "manifest_sha256": identity.manifest_sha256,
                "semantic_sha256": identity.semantic_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
