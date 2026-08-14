"""Publish stable and test API images through the shared release core.

This module owns source-version transitions, deployment-floor advancement,
registry aliases, and publication receipts. Image planning, building, evidence,
and command execution remain owned by ``release_api_image``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from tools.api_release_stack import (
        advance_api_release_minimum,
        evaluate_api_release_candidate,
    )
    from tools.release_api_image import (
        STABLE_CHANNEL,
        TEST_CHANNEL,
        _normalize_channel,
        _print_status,
        _read_project_manifest,
        _utc_timestamp,
        _write_json_atomic,
        build_release_image,
        create_release_plan,
    )
    from tools.release_command import CommandRunner, ReleaseError
    from tools.release_registry_publication import (
        push_image_with_auth_retry,
    )
    from tools.release_source_publication import (
        ensure_release_branch,
        extract_push_digest,
        prepare_release_source,
        validate_release_worktree,
        validate_version_transition,
    )
    from tools.release_stack_authority import ReleaseStackAuthorityError
except ModuleNotFoundError:
    from api_release_stack import (  # type: ignore[no-redef]
        advance_api_release_minimum,
        evaluate_api_release_candidate,
    )
    from release_api_image import (  # type: ignore[no-redef]
        STABLE_CHANNEL,
        TEST_CHANNEL,
        _normalize_channel,
        _print_status,
        _read_project_manifest,
        _utc_timestamp,
        _write_json_atomic,
        build_release_image,
        create_release_plan,
    )
    from release_command import CommandRunner, ReleaseError  # type: ignore[no-redef]
    from release_registry_publication import (  # type: ignore[no-redef]
        push_image_with_auth_retry,
    )
    from release_source_publication import (  # type: ignore[no-redef]
        ensure_release_branch,
        extract_push_digest,
        prepare_release_source,
        validate_release_worktree,
        validate_version_transition,
    )
    from release_stack_authority import (  # type: ignore[no-redef]
        ReleaseStackAuthorityError,
    )


def _validate_override_mode(
    *,
    minimum_override: bool,
    allow_current_version: bool,
    channel: str,
) -> None:
    """Reject incompatible publication-mode flags.

    Args:
        minimum_override: Whether a lower image-only override was requested.
        allow_current_version: Whether stable current-version reuse was chosen.
        channel: Normalized stable or test channel.

    Raises:
        ReleaseError: If flags describe conflicting source behavior.
    """

    if minimum_override and allow_current_version:
        raise ReleaseError(
            "Current-version reuse and a below-minimum override are mutually exclusive."
        )
    if channel == TEST_CHANNEL and allow_current_version:
        raise ReleaseError(
            "Test images always leave the source package unchanged; "
            "--allow-current-version is stable-only."
        )


def publish_release_image(
    repository_root: Path,
    app_id: str,
    target_version: str,
    *,
    image_name: str | None = None,
    python_version: str,
    pdm_version: str,
    scanner: str = "auto",
    allow_current_version: bool = False,
    channel: str = STABLE_CHANNEL,
    allow_version_below_minimum: bool = False,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Prove and publish one stable or production-connected test image.

    Args:
        repository_root: Canonical API repository.
        app_id: Explicit selected backend app.
        target_version: Strict stable semantic-version base.
        image_name: Optional registry repository override.
        python_version: Python base image tag.
        pdm_version: Exact PDM build-tool version.
        scanner: Image SBOM and vulnerability scanner.
        allow_current_version: Permit exact stable package-version reuse.
        channel: Stable release or production-connected test image channel.
        allow_version_below_minimum: Permit an exact lower image override
            without changing source or the deployment minimum.
        runner: Optional injectable command runner.

    Returns:
        Receipt bound to the resulting registry digest.

    Side Effects:
        May commit one stable package-version bump, advance the public Swarm
        minimum, build/scan images, push exact and convenience tags, and write
        ignored evidence. It never deploys or pushes Git source.
    """

    runner = runner or CommandRunner()
    repository_root = repository_root.resolve()
    normalized_channel = _normalize_channel(channel)
    _validate_override_mode(
        minimum_override=allow_version_below_minimum,
        allow_current_version=allow_current_version,
        channel=normalized_channel,
    )
    _print_status("[RELEASE] Validating source and selected version...")
    validate_release_worktree(repository_root, app_id, runner)
    ensure_release_branch(repository_root, runner)
    manifest_path = repository_root / "app" / "apps" / app_id / "pyproject.toml"
    _, current_version = _read_project_manifest(manifest_path)

    try:
        stack_decision = evaluate_api_release_candidate(
            repository_root,
            app_id,
            target_version,
            allow_below_minimum=allow_version_below_minimum,
        )
        if allow_version_below_minimum and (
            stack_decision is None or not stack_decision.minimum_override
        ):
            raise ReleaseStackAuthorityError(
                "The below-minimum override flag is valid only for an exact "
                "image version below an enrolled stack minimum."
            )
        advance_api_release_minimum(stack_decision)
    except ReleaseStackAuthorityError as error:
        raise ReleaseError(str(error)) from error

    if stack_decision is not None:
        effective_minimum = max(
            stack_decision.authority.minimum,
            stack_decision.candidate,
        )
        _print_status(
            "[RELEASE] Minimum version for the next stack release is "
            f"{effective_minimum.text}."
        )
        if stack_decision.minimum_update_required:
            _print_status(
                "[RELEASE] Updated deployment authority: "
                f"{stack_decision.authority.source}"
            )
            _print_status(
                "[INFO] Commit and push that public deployment-profile change "
                "separately when ready."
            )

    if normalized_channel == STABLE_CHANNEL and not allow_version_below_minimum:
        reuse_current = validate_version_transition(
            current_version,
            target_version,
            allow_current_version=allow_current_version,
        )
    else:
        reuse_current = True

    if allow_version_below_minimum:
        _print_status(
            f"[RELEASE] Using exact image override {target_version}; source and "
            "the next minimum remain unchanged."
        )
    elif normalized_channel == TEST_CHANNEL:
        _print_status(
            f"[RELEASE] Using test image {target_version}-test; the source "
            "package version remains unchanged."
        )
    elif reuse_current:
        _print_status(
            f"[RELEASE] Reusing version {target_version}; an existing registry "
            "tag may be replaced."
        )
    else:
        _print_status(
            f"[RELEASE] Creating local version commit: "
            f"{current_version} -> {target_version}"
        )

    prepare_release_source(
        repository_root,
        manifest_path,
        app_id,
        current_version,
        target_version,
        reuse_current_version=reuse_current,
        runner=runner,
    )
    plan = create_release_plan(
        repository_root,
        app_id,
        version=target_version,
        image_name=image_name,
        python_version=python_version,
        pdm_version=pdm_version,
        channel=normalized_channel,
        allow_version_below_minimum=allow_version_below_minimum,
        runner=runner,
    )
    receipt = build_release_image(
        repository_root,
        plan,
        runner=runner,
        scanner=scanner,
    )
    receipt["sourcePublication"] = {
        "currentVersionReused": reuse_current,
        "versionBumpCommitCreated": (
            normalized_channel == STABLE_CHANNEL and not reuse_current
        ),
        "gitPushPerformed": False,
        "sourcePushOwnedByOperator": True,
    }
    _write_json_atomic(repository_root / plan.receipt_path, receipt)

    _print_status("[PUSH] Publishing selected version tag; republishing is allowed...")
    version_push = push_image_with_auth_retry(repository_root, plan.image_ref, runner)
    registry_digest = extract_push_digest(
        f"{version_push.stdout}\n{version_push.stderr}"
    )
    if registry_digest is None:
        raise ReleaseError(
            "Version image push succeeded without a registry digest; "
            "deployment evidence cannot be bound."
        )

    publication = receipt["publication"]
    publication["channel"] = normalized_channel
    publication["baseVersion"] = target_version
    publication["minimumOverride"] = allow_version_below_minimum
    publication["versionTagPushed"] = True
    publication["versionTagRepublishAllowed"] = True
    publication["registryDigest"] = registry_digest
    receipt["state"] = "version-pushed"
    _write_json_atomic(repository_root / plan.receipt_path, receipt)

    convenience_tag = (
        "latest" if normalized_channel == STABLE_CHANNEL else "latest-test"
    )
    convenience_ref = f"{plan.image_name}:{convenience_tag}"
    _print_status(f"[TAG] Tagging {plan.image_ref} as {convenience_ref}")
    runner.run(("docker", "tag", plan.image_ref, convenience_ref), cwd=repository_root)
    _print_status(f"[PUSH] Publishing {convenience_tag} convenience tag...")
    push_image_with_auth_retry(repository_root, convenience_ref, runner)
    publication["latestConvenienceTagPushed"] = True
    publication["latestAllowedForDeployment"] = False
    receipt["state"] = "published"
    receipt["publishedAt"] = _utc_timestamp()
    _write_json_atomic(repository_root / plan.receipt_path, receipt)
    _print_status(f"[OK] Published version digest: {registry_digest}")
    _print_status(f"[OK] Published {convenience_tag}: {convenience_ref}")
    _print_status("[INFO] Git source was not pushed; push it separately when ready.")
    return receipt
