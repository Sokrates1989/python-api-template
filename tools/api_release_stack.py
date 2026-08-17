"""Coordinate API image versions with a deployment-owned version track.

Backend apps opt in through ``[tool.fe_wi.release_stack]`` in their own
``pyproject.toml``. The selected Swarm site profile remains the only authority
for the shared baseline and per-component build history.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    from tools.release_stack_authority import (
        ReleaseStackAuthority,
        ReleaseStackAuthorityError,
        StableVersion,
        advance_release_stack_minimum,
        parse_stable_version,
        resolve_release_stack_authority,
    )
except ModuleNotFoundError:
    from release_stack_authority import (  # type: ignore[no-redef]
        ReleaseStackAuthority,
        ReleaseStackAuthorityError,
        StableVersion,
        advance_release_stack_minimum,
        parse_stable_version,
        resolve_release_stack_authority,
    )


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")
InputReader = Callable[[str], str]
OutputWriter = Callable[[str], None]


@dataclass(frozen=True)
class ApiReleaseStackBinding:
    """Describe one backend app's public stack membership.

    Attributes:
        stack_id: Cross-repository release stack identity.
        authority_profile_id: Swarm site-profile filename without ``.json``.
        component_id: Component ID owned by this backend source.
    """

    stack_id: str
    authority_profile_id: str
    component_id: str


@dataclass(frozen=True)
class ApiReleaseStackDecision:
    """Describe one API candidate relative to its component minimum.

    Attributes:
        binding: Source-owned stack identity.
        authority: Deployment profile owning the API component minimum.
        candidate: Selected API image version.
        minimum_update_required: Whether confirmed publication must advance
            the authority before building the image.
        minimum_override: Whether an explicit image-only candidate remains
            below the minimum without changing it.
    """

    binding: ApiReleaseStackBinding
    authority: ReleaseStackAuthority
    candidate: StableVersion
    minimum_update_required: bool
    minimum_override: bool = False

    def safe_summary(self) -> dict[str, object]:
        """Return secret-free receipt data.

        Returns:
            Public stack, component, candidate, minimum, and authority path.
        """

        return {
            "stackId": self.binding.stack_id,
            "componentId": self.binding.component_id,
            "candidateVersion": self.candidate.text,
            "componentVersion": self.authority.component_version.text,
            "sharedReleaseBaseline": self.authority.minimum.text,
            "nextReleaseMinimum": self.authority.next_version.text,
            "minimumUpdateRequired": self.minimum_update_required,
            "minimumOverride": self.minimum_override,
            "authorityProfile": str(self.authority.source),
        }


def _read_manifest(path: Path) -> dict[str, object]:
    """Read one backend app TOML manifest.

    Args:
        path: App-owned ``pyproject.toml``.

    Returns:
        Parsed TOML mapping.

    Raises:
        ReleaseStackAuthorityError: If the file is absent or malformed.
    """

    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ReleaseStackAuthorityError(
            f"Unable to read backend release membership: {path}"
        ) from error


def load_api_release_stack_binding(path: Path) -> ApiReleaseStackBinding | None:
    """Load optional API stack membership from an app manifest.

    Args:
        path: App-owned ``pyproject.toml``.

    Returns:
        Validated membership, or ``None`` for an independently versioned app.

    Raises:
        ReleaseStackAuthorityError: If an opt-in table is incomplete, has
            unknown keys, or contains unsafe identifiers.
    """

    document = _read_manifest(path)
    tool = document.get("tool", {})
    if not isinstance(tool, dict):
        raise ReleaseStackAuthorityError(f"{path}: [tool] must be a table.")
    namespace = tool.get("fe_wi", {})
    if not isinstance(namespace, dict):
        raise ReleaseStackAuthorityError(f"{path}: [tool.fe_wi] must be a table.")
    release = namespace.get("release_stack")
    if release is None:
        return None
    if not isinstance(release, dict):
        raise ReleaseStackAuthorityError(
            f"{path}: [tool.fe_wi.release_stack] must be a table."
        )
    expected = {"stack_id", "authority_profile_id", "component_id"}
    unknown = sorted(set(release).difference(expected))
    missing = sorted(expected.difference(release))
    if unknown or missing:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise ReleaseStackAuthorityError(
            f"{path}: invalid release-stack membership ({'; '.join(details)})."
        )
    values = {key: str(release[key]).strip() for key in expected}
    unsafe = sorted(
        key for key, value in values.items() if not _IDENTIFIER_PATTERN.fullmatch(value)
    )
    if unsafe:
        raise ReleaseStackAuthorityError(
            f"{path}: unsafe release-stack values: {', '.join(unsafe)}."
        )
    return ApiReleaseStackBinding(
        stack_id=values["stack_id"],
        authority_profile_id=values["authority_profile_id"],
        component_id=values["component_id"],
    )


def evaluate_api_release_candidate(
    repository_root: Path,
    app_id: str,
    candidate_version: str,
    *,
    allow_below_minimum: bool = False,
    environment: Mapping[str, str] | None = None,
) -> ApiReleaseStackDecision | None:
    """Validate one API candidate against its deployment authority.

    Args:
        repository_root: Backend source repository.
        app_id: Explicit app directory identifier.
        candidate_version: Proposed stable image version.
        allow_below_minimum: Permit an explicit image-only override without
            lowering or advancing the deployment minimum.
        environment: Optional authority path overrides.

    Returns:
        Decision for an enrolled app, or ``None`` for an independent app.

    Raises:
        ReleaseStackAuthorityError: If membership, authority, or the candidate
            is invalid, or if the candidate is below the API minimum.
    """

    manifest = repository_root / "app" / "apps" / app_id / "pyproject.toml"
    binding = load_api_release_stack_binding(manifest)
    if binding is None:
        return None
    candidate = parse_stable_version(candidate_version, field="API candidate version")
    authority = resolve_release_stack_authority(
        repository_root,
        profile_id=binding.authority_profile_id,
        stack_id=binding.stack_id,
        component_id=binding.component_id,
        environment=environment,
    )
    if candidate < authority.minimum and not allow_below_minimum:
        raise ReleaseStackAuthorityError(
            f"API candidate {candidate.text} is below the minimum version for "
            f"the next release ({authority.minimum.text})."
        )
    return ApiReleaseStackDecision(
        binding=binding,
        authority=authority,
        candidate=candidate,
        minimum_update_required=(
            candidate >= authority.minimum
            and candidate > authority.component_version
        ),
        minimum_override=candidate < authority.minimum,
    )


def advance_api_release_minimum(decision: ApiReleaseStackDecision | None) -> None:
    """Advance the API component minimum for one confirmed publication.

    Args:
        decision: Validated API decision, or ``None`` for an unenrolled app.

    Returns:
        None.

    Side Effects:
        Atomically updates the deployment site profile only when required.
    """

    if decision is None or not decision.minimum_update_required:
        return
    advance_release_stack_minimum(decision.authority, decision.candidate.text)


def _stderr(message: str) -> None:
    """Write one human-facing selector line to standard error.

    Args:
        message: Public operator text.

    Returns:
        None.
    """

    print(message, file=sys.stderr)


def _read_input(prompt: str) -> str:
    """Read an interactive response without polluting captured stdout.

    Args:
        prompt: Operator prompt.

    Returns:
        Response without its newline.
    """

    print(prompt, end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().rstrip("\r\n")


def _read_manual_candidate(
    minimum: StableVersion,
    *,
    reader: InputReader,
    writer: OutputWriter,
) -> StableVersion:
    """Read a valid manual candidate at or above the API minimum.

    Args:
        minimum: Current lower bound.
        reader: Injectable input adapter.
        writer: Injectable output adapter.

    Returns:
        Validated manual candidate.
    """

    while True:
        raw = reader("Exact semantic version: ")
        try:
            candidate = parse_stable_version(raw, field="candidate version")
        except ReleaseStackAuthorityError as error:
            writer(f"[WARN] {error}")
            continue
        if candidate < minimum:
            writer(f"[WARN] Choose {minimum.text} or newer.")
            continue
        return candidate


def select_api_candidate(
    candidate: StableVersion,
    minimum: StableVersion,
    *,
    reader: InputReader = _read_input,
    writer: OutputWriter = _stderr,
) -> StableVersion | None:
    """Resolve an API candidate/minimum mismatch with a small menu.

    Args:
        candidate: Initially selected release version.
        minimum: Deployment-owned lower bound.
        reader: Injectable input adapter.
        writer: Injectable output adapter.

    Returns:
        Final candidate, or ``None`` when cancelled.
    """

    if candidate == minimum:
        return candidate
    writer("")
    writer("Coordinated release version")
    writer("---------------------------")
    if candidate < minimum:
        writer(
            f"Selected {candidate.text} is below the minimum version for the "
            f"next release ({minimum.text})."
        )
        writer(f"  1) Use {minimum.text} (recommended)")
        writer("  2) Enter another version")
        writer("  0) Cancel")
        choice = reader("Your choice [1]: ").strip() or "1"
        if choice == "1":
            return minimum
        if choice == "2":
            return _read_manual_candidate(minimum, reader=reader, writer=writer)
        return None
    writer(
        f"Selected {candidate.text} is newer than the current minimum for the "
        f"next release ({minimum.text})."
    )
    writer("The confirmed publication will update the deployment site profile.")
    writer(f"  1) Advance the minimum to {candidate.text} and continue (recommended)")
    writer(f"  2) Use the current minimum {minimum.text}")
    writer("  3) Enter another version")
    writer("  0) Cancel")
    choice = reader("Your choice [1]: ").strip() or "1"
    if choice == "1":
        return candidate
    if choice == "2":
        return minimum
    if choice == "3":
        return _read_manual_candidate(minimum, reader=reader, writer=writer)
    return None


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the API release-stack helper parser.

    Returns:
        Parser for app identity and candidate selection.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument(
        "--minimum-only",
        action="store_true",
        help=(
            "Print the deployment-owned API minimum, or the candidate for an "
            "app without release-stack membership."
        ),
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print the shared baseline and next API version separated by a space.",
    )
    parser.add_argument(
        "--allow-below-minimum",
        action="store_true",
        help="Permit an explicit image override without lowering the minimum.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> int:
    """Select and print the final API publication version.

    Args:
        argv: Optional explicit arguments.
        environment: Optional deployment-authority overrides.

    Returns:
        Zero after printing a version, two for invalid configuration, or three
        when the operator cancels.
    """

    arguments = build_argument_parser().parse_args(argv)
    active_environment = os.environ if environment is None else environment
    try:
        manifest = (
            arguments.repository_root
            / "app"
            / "apps"
            / arguments.app
            / "pyproject.toml"
        )
        binding = load_api_release_stack_binding(manifest)
        candidate = parse_stable_version(arguments.candidate, field="candidate version")
        if binding is None:
            next_version = StableVersion(
                candidate.major,
                candidate.minor,
                candidate.patch + 1,
            )
            if arguments.plan_only:
                print(candidate.text, next_version.text)
                return 0
            if arguments.minimum_only:
                print(next_version.text)
                return 0
            print(candidate.text)
            return 0
        authority = resolve_release_stack_authority(
            arguments.repository_root,
            profile_id=binding.authority_profile_id,
            stack_id=binding.stack_id,
            component_id=binding.component_id,
            environment=active_environment,
        )
        if arguments.plan_only:
            print(authority.minimum.text, authority.next_version.text)
            return 0
        if arguments.minimum_only:
            print(authority.next_version.text)
            return 0
        if arguments.allow_below_minimum and candidate < authority.minimum:
            print(candidate.text)
            return 0
        if candidate != authority.minimum:
            _stderr(f"Authority: {authority.source}")
        selected = select_api_candidate(candidate, authority.minimum)
        if selected is None:
            return 3
        print(selected.text)
        return 0
    except (ReleaseStackAuthorityError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
