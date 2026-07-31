"""Command-line entry point for the Booking Service quality runtime."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence

from booking_quality.config import BookingServiceQualityError, build_quality_runtime
from booking_quality.orchestration import (
    print_summary,
    run_with_teardown,
    start_stack,
    stop_stack,
    verify_stack,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the quality runner argument parser.

    Returns:
        argparse.ArgumentParser: Parser for run/up/verify/down and wait bounds.

    Side Effects:
        None.
    """
    parser = argparse.ArgumentParser(
        description="Run the disposable Booking Service backend quality stack.",
    )
    parser.add_argument("operation", choices=("run", "up", "verify", "down"))
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=240.0,
        help="Total API startup wait bound (default: 240).",
    )
    return parser


def _execute_operation(operation: str, timeout_seconds: float) -> None:
    """Execute one already-validated quality operation.

    Args:
        operation: One of ``run``, ``up``, ``verify``, or ``down``.
        timeout_seconds: Bounded API readiness wait.

    Returns:
        None.

    Raises:
        BookingServiceQualityError: When configuration or a semantic gate fails.
        subprocess.CalledProcessError: When Docker Compose exits non-zero.

    Side Effects:
        May create, verify, or remove isolated Docker resources.
    """
    runtime = build_quality_runtime(operation in {"up", "verify"})
    if operation == "run":
        run_with_teardown(runtime, timeout_seconds)
    elif operation == "up":
        start_stack(runtime, timeout_seconds)
        print_summary(runtime, "running")
    elif operation == "verify":
        verify_stack(runtime, timeout_seconds)
        print_summary(runtime, "verified")
    else:
        stop_stack(runtime)
        print_summary(runtime, "removed")


def main(argv: Sequence[str] | None = None) -> int:
    """Execute one quality operation with safe failure reporting.

    Args:
        argv: Optional test argument vector; process arguments are used when
        omitted.

    Returns:
        int: Zero on success and one on safe validation/runtime failure.

    Side Effects:
        Delegates to isolated Docker orchestration and writes only sanitized
        summaries or stable error categories.
    """
    arguments = build_argument_parser().parse_args(argv)
    if arguments.timeout_seconds <= 0:
        print("--timeout-seconds must be greater than zero.", file=sys.stderr)
        return 1
    try:
        _execute_operation(arguments.operation, arguments.timeout_seconds)
    except BookingServiceQualityError as error:
        print(f"Booking Service quality operation failed: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(
            f"Booking Service quality operation failed ({type(error).__name__}).",
            file=sys.stderr,
        )
        return 1
    return 0
