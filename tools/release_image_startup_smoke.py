"""Run app-owned, secret-free startup imports against built API images.

Each selected app may provide ``deployment/release-startup-smoke.env``. The
fixture contains public environment values and ``*_FILE`` paths only. Dummy
values are created inside the disposable container, so neither real secrets
nor host secret files enter the release command or evidence.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

try:
    from tools.release_command import ReleaseError
except ModuleNotFoundError:
    from release_command import ReleaseError  # type: ignore[no-redef]


ENVIRONMENT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
SMOKE_SECRET_PATH_PATTERN = re.compile(
    r"^/tmp/release-smoke/[a-z0-9][a-z0-9._-]*$"
)
DIRECT_SECRET_KEY_PATTERN = re.compile(
    r"(?:PASSWORD|SECRET|TOKEN|PRIVATE_KEY|API_KEY)$"
)
FORBIDDEN_RUNTIME_KEYS = frozenset(
    {"PATH", "PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH"}
)


class StartupSmokeRunner(Protocol):
    """Command behavior required by the image startup smoke."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Execute one captured command.

        Args:
            command: Argument-vector command to execute.
            cwd: Child-process working directory.
            check: Whether failure raises the release error boundary.

        Returns:
            Completed child-process result.
        """


def _read_public_environment(path: Path) -> dict[str, str]:
    """Read and validate one dedicated public startup-smoke fixture.

    Args:
        path: App-owned ``release-startup-smoke.env`` file.

    Returns:
        Public environment values in declaration order.

    Raises:
        ReleaseError: If syntax, duplicate keys, direct secrets, runtime
            overrides, or secret-file paths are unsafe.
    """

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ReleaseError(
                f"Invalid startup-smoke entry at {path}:{line_number}."
            )
        key, value = (part.strip() for part in line.split("=", 1))
        if not ENVIRONMENT_KEY_PATTERN.fullmatch(key) or key in FORBIDDEN_RUNTIME_KEYS:
            raise ReleaseError(f"Unsafe startup-smoke environment key: {key!r}.")
        if key in values:
            raise ReleaseError(f"Duplicate startup-smoke environment key: {key}.")
        if DIRECT_SECRET_KEY_PATTERN.search(key) and not key.endswith("_FILE"):
            raise ReleaseError(
                f"Startup-smoke fixture must not contain direct secret field {key}."
            )
        if key.endswith("_FILE") and not SMOKE_SECRET_PATH_PATTERN.fullmatch(value):
            raise ReleaseError(
                f"Startup-smoke secret path for {key} must stay below "
                "/tmp/release-smoke/."
            )
        if not value or any(character in value for character in ("\x00", "\r", "\n")):
            raise ReleaseError(f"Startup-smoke value for {key} is empty or unsafe.")
        values[key] = value
    return values


def _validate_identity_bindings(environment: dict[str, str], app_id: str) -> None:
    """Require a production fixture bound to the selected app identity.

    Args:
        environment: Parsed startup-smoke environment.
        app_id: Selected backend app identifier.

    Raises:
        ReleaseError: If production, build, or runtime identity drifts.
    """

    expected = {
        "APP_ENVIRONMENT": "production",
        "BACKEND_APP_ID": app_id,
        "APP_PROFILE": app_id,
    }
    for key, value in expected.items():
        if environment.get(key) != value:
            raise ReleaseError(
                f"Startup-smoke {key} must equal {value!r} for {app_id}."
            )


def _container_command(
    image_ref: str,
    app_id: str,
    environment: dict[str, str],
) -> tuple[str, ...]:
    """Build a shell-safe disposable container command.

    Args:
        image_ref: Exact locally built image reference.
        app_id: Selected backend app identifier.
        environment: Validated public fixture values.

    Returns:
        Docker argument vector that creates dummy mounted-file stand-ins and
        imports the production application without starting external services.
    """

    command = ["docker", "run", "--rm", "--entrypoint", "sh"]
    for key, value in environment.items():
        command.extend(("--env", f"{key}={value}"))
    secret_paths = sorted(
        value for key, value in environment.items() if key.endswith("_FILE")
    )
    setup_parts = ["set -eu", "umask 077", "mkdir -p /tmp/release-smoke"]
    setup_parts.extend(
        f"printf '%s' 'release-smoke-placeholder' > '{path}'"
        for path in secret_paths
    )
    python_statement = (
        "from api.settings import settings; import main; "
        "assert settings.APP_ENVIRONMENT == 'production'; "
        f"assert main.selected_backend_app.app_id == '{app_id}'; "
        "print('Release image startup smoke passed')"
    )
    setup_parts.append(
        "exec /app/.venv/bin/python -c \"" + python_statement + "\""
    )
    command.extend((image_ref, "-c", "; ".join(setup_parts)))
    return tuple(command)


def run_image_startup_smoke(
    repository_root: Path,
    app_id: str,
    image_ref: str,
    runner: StartupSmokeRunner,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Run an optional app-owned production import smoke against an image.

    Args:
        repository_root: Canonical API repository root.
        app_id: Selected backend app identifier.
        image_ref: Exact locally built image reference.
        runner: Injectable command boundary.
        progress: Optional secret-free operator status callback.

    Returns:
        Sanitized evidence describing whether and which fixture was executed.

    Side Effects:
        Runs one disposable Docker container when the app declares a fixture.

    Raises:
        ReleaseError: If the fixture or production application import fails.
    """

    relative_path = Path("app") / "apps" / app_id / "deployment" / (
        "release-startup-smoke.env"
    )
    fixture_path = repository_root / relative_path
    if not fixture_path.is_file():
        return {
            "executed": False,
            "kind": "production-application-import",
            "configurationPath": None,
            "configurationSha256": None,
        }
    environment = _read_public_environment(fixture_path)
    _validate_identity_bindings(environment, app_id)
    if progress is not None:
        progress(
            "[VERIFY] Running app-owned production startup import with "
            "non-default public identity..."
        )
    runner.run(
        _container_command(image_ref, app_id, environment),
        cwd=repository_root,
    )
    if progress is not None:
        progress("[OK] Production startup import smoke passed.")
    return {
        "executed": True,
        "kind": "production-application-import",
        "configurationPath": relative_path.as_posix(),
        "configurationSha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
    }


__all__ = ["run_image_startup_smoke"]
