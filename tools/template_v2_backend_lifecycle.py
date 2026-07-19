"""CLI for safe Python-owned Template V2 backend lifecycle operations.

No operation provisions services, reads credentials, or writes environment
files. Check, plan, diff, and reconcile are always read-only. Every mutation
requires both the exact current plan digest and operation-specific intent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from template_v2.backend_lifecycle import execute_backend_lifecycle  # noqa: E402
from template_v2.backend_lifecycle_models import BackendLifecycleError  # noqa: E402


def _parse_arguments() -> argparse.Namespace:
    """Parse lifecycle CLI arguments.

    Returns:
        Parsed operation, roots, target, detach paths, and write authority.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=("check", "plan", "diff", "create", "reconcile", "apply", "detach", "rollback-create"),
    )
    parser.add_argument("--template-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--target-directory", required=True)
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--write-intent")
    parser.add_argument("--detach-path", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    """Run one lifecycle operation with content-free diagnostics.

    Returns:
        Zero on success, two on lifecycle failure, or 130 on cancellation.
    """

    arguments = _parse_arguments()
    try:
        output = execute_backend_lifecycle(
            arguments.operation,
            template_root=arguments.template_root,
            repository_root=arguments.repository_root,
            bundle_root=arguments.bundle_root,
            target_directory=arguments.target_directory,
            expected_plan_sha256=arguments.expected_plan_sha256,
            write_intent=arguments.write_intent,
            detach_paths=tuple(arguments.detach_path),
        )
    except (KeyboardInterrupt, EOFError):
        print("cancelled: backend lifecycle published no partial state", file=sys.stderr)
        return 130
    except (BackendLifecycleError, OSError) as error:
        issues = getattr(error, "issues", (str(error),))
        for issue in issues:
            print(issue, file=sys.stderr)
        return 2
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
