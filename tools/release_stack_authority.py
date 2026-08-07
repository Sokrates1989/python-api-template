"""Resolve and update the deployment-owned release-stack minimum.

The Swarm deployment profile is the single authority for the minimum semantic
version that the next independently published stack component may use. Source
repositories discover that profile through an explicit environment override or
the standard sibling-workspace layout; no application identity is hardcoded.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROFILE_PATH_ENV = "RELEASE_STACK_PROFILE_PATH"
DEPLOYMENT_ROOT_ENV = "RELEASE_STACK_DEPLOYMENT_ROOT"
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)


class ReleaseStackAuthorityError(ValueError):
    """Report missing, ambiguous, malformed, or regressive authority data."""


@dataclass(frozen=True, order=True)
class StableVersion:
    """Represent one stable semantic version.

    Attributes:
        major: Non-negative major version.
        minor: Non-negative minor version.
        patch: Non-negative patch version.
    """

    major: int
    minor: int
    patch: int

    @property
    def text(self) -> str:
        """Return the normalized ``MAJOR.MINOR.PATCH`` representation."""

        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ReleaseStackAuthority:
    """Describe one validated deployment-owned release stack.

    Attributes:
        source: Exact Swarm site-profile path.
        profile_id: Site-profile filename without its JSON suffix.
        stack_id: Stable cross-repository release identity.
        minimum: Minimum version permitted for the next component release.
        components: Complete set of coordinated component identifiers.
    """

    source: Path
    profile_id: str
    stack_id: str
    minimum: StableVersion
    components: tuple[str, ...]


def parse_stable_version(value: str, *, field: str) -> StableVersion:
    """Parse one stable semantic version.

    Args:
        value: Candidate ``MAJOR.MINOR.PATCH`` string.
        field: Human-readable field name used in diagnostics.

    Returns:
        Parsed stable version.

    Raises:
        ReleaseStackAuthorityError: If ``value`` is not stable SemVer.
    """

    match = _SEMVER_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ReleaseStackAuthorityError(
            f"{field} must use stable semantic version form MAJOR.MINOR.PATCH."
        )
    return StableVersion(*(int(item) for item in match.groups()))


def _read_mapping(path: Path) -> dict[str, Any]:
    """Read one JSON object.

    Args:
        path: JSON file to read.

    Returns:
        Parsed root mapping.

    Raises:
        ReleaseStackAuthorityError: If JSON is malformed or not an object.
        OSError: If the file cannot be read.
    """

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReleaseStackAuthorityError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ReleaseStackAuthorityError(f"{path}: root value must be an object.")
    return value


def _resolve_override(value: str, source_root: Path) -> Path:
    """Resolve one explicit path relative to the source repository.

    Args:
        value: Absolute or source-root-relative operator override.
        source_root: Repository requesting release coordination.

    Returns:
        Absolute normalized path.
    """

    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = source_root / candidate
    return candidate.resolve()


def _automatic_profile_candidates(source_root: Path, profile_id: str) -> tuple[Path, ...]:
    """Find standard sibling-workspace site-profile candidates.

    Args:
        source_root: Repository requesting release coordination.
        profile_id: Deployment profile filename without ``.json``.

    Returns:
        Unique existing candidate paths. Only bounded ``site-configs`` and
        ``swarm/*/site-configs`` locations below ancestors are inspected.
    """

    candidates: set[Path] = set()
    for ancestor in (source_root.resolve(), *source_root.resolve().parents):
        direct = ancestor / "site-configs" / f"{profile_id}.json"
        if direct.is_file():
            candidates.add(direct.resolve())
        swarm_root = ancestor / "swarm"
        if swarm_root.is_dir():
            for candidate in swarm_root.glob(f"*/site-configs/{profile_id}.json"):
                if candidate.is_file():
                    candidates.add(candidate.resolve())
    return tuple(sorted(candidates, key=lambda item: str(item).lower()))


def _candidate_profile_paths(
    source_root: Path,
    profile_id: str,
    environment: Mapping[str, str],
) -> tuple[Path, ...]:
    """Resolve explicit or automatically discovered profile paths.

    Args:
        source_root: Repository requesting release coordination.
        profile_id: Deployment site-profile identifier.
        environment: Process environment or a test mapping.

    Returns:
        Candidate paths in deterministic order.

    Raises:
        ReleaseStackAuthorityError: If an explicit override is missing.
    """

    exact = environment.get(PROFILE_PATH_ENV, "").strip()
    if exact:
        path = _resolve_override(exact, source_root)
        if not path.is_file():
            raise ReleaseStackAuthorityError(
                f"{PROFILE_PATH_ENV} does not identify a file: {path}"
            )
        return (path,)
    deployment_root = environment.get(DEPLOYMENT_ROOT_ENV, "").strip()
    if deployment_root:
        root = _resolve_override(deployment_root, source_root)
        path = root / "site-configs" / f"{profile_id}.json"
        if not path.is_file():
            raise ReleaseStackAuthorityError(
                f"{DEPLOYMENT_ROOT_ENV} has no site profile {profile_id!r}: {path}"
            )
        return (path.resolve(),)
    return _automatic_profile_candidates(source_root, profile_id)


def load_release_stack_authority(
    path: Path,
    *,
    expected_stack_id: str,
    required_component: str,
) -> ReleaseStackAuthority:
    """Load one Swarm site profile as a release-stack authority.

    Args:
        path: Exact site-profile JSON path.
        expected_stack_id: Source-owned stack identity that must match.
        required_component: Component the source action intends to release.

    Returns:
        Validated authority data.

    Raises:
        ReleaseStackAuthorityError: If release identity, policy, minimum, or
            component membership is incomplete or unsafe.
        OSError: If the profile cannot be read.
    """

    if not _IDENTIFIER_PATTERN.fullmatch(expected_stack_id):
        raise ReleaseStackAuthorityError("Expected stack ID is unsafe.")
    if not _IDENTIFIER_PATTERN.fullmatch(required_component):
        raise ReleaseStackAuthorityError("Required component ID is unsafe.")
    payload = _read_mapping(path)
    release = payload.get("release")
    if not isinstance(release, dict):
        raise ReleaseStackAuthorityError(f"{path}: release must be an object.")
    if release.get("stackId") != expected_stack_id:
        raise ReleaseStackAuthorityError(
            f"{path}: release.stackId must equal {expected_stack_id!r}."
        )
    if release.get("versionPolicy") != "monotonic-floor":
        raise ReleaseStackAuthorityError(
            f"{path}: release.versionPolicy must equal 'monotonic-floor'."
        )
    raw_minimum = release.get("versionFloor")
    if not isinstance(raw_minimum, str):
        raise ReleaseStackAuthorityError(
            f"{path}: release.versionFloor must be a SemVer string."
        )
    raw_components = release.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ReleaseStackAuthorityError(
            f"{path}: release.components must be a non-empty list."
        )
    components = tuple(str(item) for item in raw_components)
    if len(components) != len(set(components)) or any(
        not _IDENTIFIER_PATTERN.fullmatch(item) for item in components
    ):
        raise ReleaseStackAuthorityError(
            f"{path}: release.components contains duplicate or unsafe IDs."
        )
    if required_component not in components:
        raise ReleaseStackAuthorityError(
            f"{path}: release.components does not include {required_component!r}."
        )
    return ReleaseStackAuthority(
        source=path.resolve(),
        profile_id=path.stem,
        stack_id=expected_stack_id,
        minimum=parse_stable_version(
            raw_minimum,
            field="release.versionFloor",
        ),
        components=components,
    )


def resolve_release_stack_authority(
    source_root: Path,
    *,
    profile_id: str,
    stack_id: str,
    component_id: str,
    environment: Mapping[str, str] | None = None,
) -> ReleaseStackAuthority:
    """Discover the unique deployment profile for one source action.

    Args:
        source_root: Repository requesting release coordination.
        profile_id: Deployment profile filename without ``.json``.
        stack_id: Expected cross-repository stack identity.
        component_id: Component being built or published.
        environment: Optional path-override mapping; defaults to ``os.environ``.

    Returns:
        Unique validated deployment authority.

    Raises:
        ReleaseStackAuthorityError: If no profile or multiple matching
            profiles are found, or a candidate profile is invalid.
        OSError: If a candidate cannot be read.
    """

    if not _IDENTIFIER_PATTERN.fullmatch(profile_id):
        raise ReleaseStackAuthorityError("Authority profile ID is unsafe.")
    active_environment = os.environ if environment is None else environment
    candidates = _candidate_profile_paths(
        source_root.resolve(),
        profile_id,
        active_environment,
    )
    if not candidates:
        raise ReleaseStackAuthorityError(
            "No deployment-owned release profile was found for "
            f"{profile_id!r}. Set {PROFILE_PATH_ENV} to the exact site-config "
            f"file or {DEPLOYMENT_ROOT_ENV} to its Swarm repository."
        )
    valid: list[ReleaseStackAuthority] = []
    errors: list[str] = []
    for candidate in candidates:
        try:
            valid.append(
                load_release_stack_authority(
                    candidate,
                    expected_stack_id=stack_id,
                    required_component=component_id,
                )
            )
        except ReleaseStackAuthorityError as error:
            errors.append(str(error))
    if len(valid) == 1:
        return valid[0]
    if len(valid) > 1:
        locations = ", ".join(str(item.source) for item in valid)
        raise ReleaseStackAuthorityError(
            "Multiple deployment profiles claim this release stack. Set "
            f"{PROFILE_PATH_ENV} explicitly: {locations}"
        )
    details = "\n".join(f"- {item}" for item in errors)
    raise ReleaseStackAuthorityError(
        f"No valid deployment authority matched stack {stack_id!r}:\n{details}"
    )


def advance_release_stack_minimum(
    authority: ReleaseStackAuthority,
    candidate_version: str,
) -> ReleaseStackAuthority:
    """Advance the deployment-owned minimum when a release moves beyond it.

    Args:
        authority: Previously validated authority and drift guard.
        candidate_version: Confirmed component version.

    Returns:
        Existing authority when no change is needed, otherwise the reloaded
        authority containing the advanced minimum.

    Side Effects:
        Atomically rewrites only the public site-profile JSON when the
        candidate is greater than the current minimum.

    Raises:
        ReleaseStackAuthorityError: If the candidate regresses, the profile
            drifted, or the release block is no longer valid.
        OSError: If the profile cannot be replaced.
    """

    candidate = parse_stable_version(candidate_version, field="candidate version")
    if candidate < authority.minimum:
        raise ReleaseStackAuthorityError(
            f"Candidate {candidate.text} is below the minimum version for the "
            f"next release ({authority.minimum.text})."
        )
    if candidate == authority.minimum:
        return authority
    payload = _read_mapping(authority.source)
    release = payload.get("release")
    if not isinstance(release, dict):
        raise ReleaseStackAuthorityError(
            f"{authority.source}: release block disappeared before update."
        )
    if release.get("versionFloor") != authority.minimum.text:
        raise ReleaseStackAuthorityError(
            f"{authority.source}: minimum changed after validation; retry the release plan."
        )
    release["versionFloor"] = candidate.text
    temporary = authority.source.with_suffix(authority.source.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, authority.source)
    return load_release_stack_authority(
        authority.source,
        expected_stack_id=authority.stack_id,
        required_component=authority.components[0],
    )



