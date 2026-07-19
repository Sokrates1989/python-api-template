"""Command-line validation for the Template V2 backend foundation contract.

The command emits a content-free, path-independent identity on success. Its
optional digest mode supports intentional contract maintenance without editing
or formatting source files.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from template_v2.backend_foundation_contract import (  # noqa: E402
    BackendFoundationContractError,
    _portable_source_paths,
    _read_manifest,
    calculate_source_sha256,
    validate_backend_foundation,
)


def _parse_arguments() -> argparse.Namespace:
    """Parse validator CLI arguments.

    Returns:
        Parsed repository root, output mode, and maintenance options.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--print-source-sha256", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Validate the foundation or print its current canonical source digest.

    Returns:
        Zero on success, or one when compatibility validation fails.
    """

    arguments = _parse_arguments()
    try:
        if arguments.print_source_sha256:
            document, _ = _read_manifest(arguments.root.resolve())
            print(calculate_source_sha256(arguments.root.resolve(), _portable_source_paths(document)))
            return 0
        identity = validate_backend_foundation(arguments.root)
    except BackendFoundationContractError as error:
        for issue in error.issues:
            print(issue, file=sys.stderr)
        return 1
    payload = asdict(identity)
    print(json.dumps(payload, sort_keys=True) if arguments.as_json else f"Template V2 backend foundation valid: {payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
