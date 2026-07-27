"""Create selected-image SBOM and vulnerability-policy evidence.

This module is independent of menu, Git, versioning, and registry publication
concerns. It operates only on an already built local image plus an app-owned
PDM lock and returns sanitized evidence summaries.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import tomllib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence


class ImageEvidenceError(RuntimeError):
    """Raised when image inventory or vulnerability evidence fails closed."""


class EvidenceCommandRunner(Protocol):
    """Command-runner behavior required by image evidence collection."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run one argument-vector command.

        Args:
            command: Executable and arguments without shell interpolation.
            cwd: Working directory for the child process.
            check: Whether nonzero status should raise in the implementation.

        Returns:
            subprocess.CompletedProcess[str]: Captured command result.

        Side Effects:
            May execute an external image scanner.
        """

    def which(self, executable: str) -> str | None:
        """Resolve an executable from the host path.

        Args:
            executable: Executable name to locate.

        Returns:
            str | None: Resolved path, or ``None`` when unavailable.
        """


@dataclass(frozen=True)
class ImageEvidenceRequest:
    """Public, secret-free inputs for one image evidence collection.

    Attributes:
        app_id: Selected backend app identifier.
        package_name: App-owned package name.
        package_version: Immutable semantic version.
        git_revision: Full source revision.
        image_ref: Exact locally built image reference.
        dependency_lock_path: Selected app PDM lock.
        dependency_lock_sha256: Selected lock digest.
        image_sbom_path: Ignored full-image SPDX output.
        dependency_sbom_path: Ignored lock-derived SPDX output.
    """

    app_id: str
    package_name: str
    package_version: str
    git_revision: str
    image_ref: str
    dependency_lock_path: Path
    dependency_lock_sha256: str
    image_sbom_path: Path
    dependency_sbom_path: Path


def _utc_timestamp() -> str:
    """Return a second-precision UTC timestamp.

    Returns:
        str: ISO-8601 timestamp with an explicit UTC offset.
    """

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    """Hash one evidence artifact.

    Args:
        path: File to read in bounded chunks.

    Returns:
        str: Lowercase hexadecimal SHA-256 digest.

    Raises:
        OSError: If the file cannot be read.
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _spdx_identifier(value: str) -> str:
    """Normalize a package name for an SPDX element identifier.

    Args:
        value: Untrusted package name from the dependency lock.

    Returns:
        str: Non-empty SPDX-compatible identifier suffix.
    """

    normalized = re.sub(r"[^A-Za-z0-9.-]+", "-", value).strip("-.")
    return normalized or "package"


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    """Write a JSON evidence artifact atomically.

    Args:
        path: Final ignored evidence path.
        value: JSON-serializable document.

    Side Effects:
        Creates parent directories and atomically replaces the target file.

    Raises:
        OSError: If the temporary or final file cannot be written.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def write_dependency_sbom(request: ImageEvidenceRequest) -> Path:
    """Generate a deterministic SPDX SBOM from the selected PDM lock.

    Args:
        request: Selected app, lock, source, and output identity.

    Returns:
        Path: Written dependency SPDX JSON path.

    Side Effects:
        Creates or replaces the ignored dependency SBOM artifact.

    Raises:
        ImageEvidenceError: If the lock is not valid TOML.
        OSError: If lock or output files cannot be read or written.
    """

    try:
        lock_document = tomllib.loads(
            request.dependency_lock_path.read_text(encoding="utf-8")
        )
    except tomllib.TOMLDecodeError as exc:
        raise ImageEvidenceError("Selected app PDM lock is malformed.") from exc
    raw_packages = lock_document.get("package", [])
    packages: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    document_id = "SPDXRef-DOCUMENT"

    for index, raw_package in enumerate(raw_packages, start=1):
        if not isinstance(raw_package, dict):
            continue
        name = str(raw_package.get("name", "")).strip()
        version = str(raw_package.get("version", "")).strip()
        if not name or not version:
            continue
        package_id = f"SPDXRef-Package-{index}-{_spdx_identifier(name)}"
        package: dict[str, Any] = {
            "SPDXID": package_id,
            "name": name,
            "versionInfo": version,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
        }
        files = raw_package.get("files")
        if isinstance(files, list):
            hashes = [
                str(item.get("hash", ""))
                for item in files
                if isinstance(item, dict)
                and str(item.get("hash", "")).startswith("sha256:")
            ]
            if hashes:
                package["checksums"] = [
                    {
                        "algorithm": "SHA256",
                        "checksumValue": hashes[0].split(":", 1)[1],
                    }
                ]
        packages.append(package)
        relationships.append(
            {
                "spdxElementId": document_id,
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": package_id,
            }
        )

    namespace_seed = (
        f"{request.app_id}:{request.package_version}:{request.git_revision}:"
        f"{request.dependency_lock_sha256}"
    )
    timestamp = _utc_timestamp()
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": document_id,
        "name": f"{request.package_name}-{request.package_version}-dependencies",
        "documentNamespace": (
            "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, namespace_seed))
        ),
        "creationInfo": {
            "created": timestamp,
            "creators": ["Tool: python-api-template-release-api-image"],
        },
        "packages": packages,
        "relationships": relationships,
        "annotations": [
            {
                "annotationType": "OTHER",
                "annotator": "Tool: python-api-template-release-api-image",
                "annotationDate": timestamp,
                "comment": (
                    "Dependency SBOM generated from "
                    f"{request.dependency_lock_path.name} sha256:"
                    f"{request.dependency_lock_sha256}"
                ),
            }
        ],
    }
    _write_json_atomic(request.dependency_sbom_path, document)
    return request.dependency_sbom_path


def resolve_scanner(
    repository_root: Path,
    runner: EvidenceCommandRunner,
    scanner: str,
) -> str:
    """Resolve a scanner capable of image SBOM and vulnerability checks.

    Args:
        repository_root: Working directory for Docker commands.
        runner: Injectable argument-vector command runner.
        scanner: ``auto``, ``trivy``, or ``docker-scout``.

    Returns:
        str: Selected scanner identifier.

    Side Effects:
        In ``auto`` mode, may run ``docker scout version``.

    Raises:
        ImageEvidenceError: If no supported scanner is available.
    """

    if scanner == "auto":
        if runner.which("trivy"):
            return "trivy"
        scout_check = runner.run(
            ("docker", "scout", "version"),
            cwd=repository_root,
            check=False,
        )
        if scout_check.returncode == 0:
            return "docker-scout"
        raise ImageEvidenceError(
            "No supported image SBOM/vulnerability scanner is available. "
            "Install Trivy or enable Docker Scout before a release build."
        )
    if scanner not in {"trivy", "docker-scout"}:
        raise ImageEvidenceError(f"Unsupported image scanner: {scanner!r}")
    return scanner


def write_image_sbom(
    repository_root: Path,
    request: ImageEvidenceRequest,
    runner: EvidenceCommandRunner,
    scanner: str,
) -> Path:
    """Generate and validate a full-image SPDX JSON SBOM.

    Args:
        repository_root: Working directory for scanner commands.
        request: Image identity and evidence paths.
        runner: Injectable argument-vector command runner.
        scanner: Resolved scanner identifier.

    Returns:
        Path: Written full-image SPDX JSON path.

    Side Effects:
        Runs Trivy or Docker Scout and replaces the ignored image SBOM.

    Raises:
        ImageEvidenceError: If scanner output is missing, malformed, or not SPDX.
    """

    output_path = request.image_sbom_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if scanner == "trivy":
        runner.run(
            (
                "trivy",
                "image",
                "--quiet",
                "--format",
                "spdx-json",
                "--output",
                str(output_path),
                request.image_ref,
            ),
            cwd=repository_root,
        )
    elif scanner == "docker-scout":
        completed = runner.run(
            (
                "docker",
                "scout",
                "sbom",
                "--format",
                "spdx",
                request.image_ref,
            ),
            cwd=repository_root,
        )
        output_path.write_text(completed.stdout, encoding="utf-8")
    else:
        raise ImageEvidenceError(f"Unsupported image SBOM scanner: {scanner!r}")

    try:
        document = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImageEvidenceError(
            "Image scanner did not produce a valid SPDX JSON SBOM."
        ) from exc
    if not str(document.get("spdxVersion", "")).startswith("SPDX-"):
        raise ImageEvidenceError("Image scanner output is not an SPDX document.")
    return output_path


def run_vulnerability_scan(
    repository_root: Path,
    request: ImageEvidenceRequest,
    runner: EvidenceCommandRunner,
    selected_scanner: str,
) -> dict[str, Any]:
    """Apply the bounded HIGH/CRITICAL image vulnerability policy.

    Args:
        repository_root: Working directory for scanner commands.
        request: Exact local image identity.
        runner: Injectable argument-vector command runner.
        selected_scanner: Resolved scanner identifier.

    Returns:
        dict[str, Any]: Sanitized scanner, policy, and pass result.

    Side Effects:
        Runs an image scan and creates only an ephemeral raw report.

    Raises:
        ImageEvidenceError: If policy findings or scanner errors return nonzero.
    """

    if selected_scanner == "trivy":
        with tempfile.TemporaryDirectory(prefix="felix-api-trivy-") as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            completed = runner.run(
                (
                    "trivy",
                    "image",
                    "--quiet",
                    "--format",
                    "json",
                    "--output",
                    str(report_path),
                    "--severity",
                    "HIGH,CRITICAL",
                    "--ignore-unfixed",
                    "--exit-code",
                    "1",
                    request.image_ref,
                ),
                cwd=repository_root,
                check=False,
            )
            if completed.returncode != 0:
                raise ImageEvidenceError(
                    "Vulnerability policy failed: fixable HIGH or CRITICAL "
                    "findings, or a Trivy operational error, blocked the image."
                )
        scanner_name = "trivy"
    elif selected_scanner == "docker-scout":
        completed = runner.run(
            (
                "docker",
                "scout",
                "cves",
                "--only-severity",
                "high,critical",
                "--exit-code",
                request.image_ref,
            ),
            cwd=repository_root,
            check=False,
        )
        if completed.returncode != 0:
            raise ImageEvidenceError(
                "Vulnerability policy failed: HIGH or CRITICAL findings, "
                "or a Docker Scout operational error, blocked the image."
            )
        scanner_name = "docker-scout"
    else:
        raise ImageEvidenceError(
            f"Unsupported vulnerability scanner: {selected_scanner!r}"
        )

    return {
        "scanner": scanner_name,
        "policy": {
            "rejectedSeverities": ["HIGH", "CRITICAL"],
            "ignoreUnfixed": selected_scanner == "trivy",
        },
        "result": "passed",
    }


def collect_image_evidence(
    repository_root: Path,
    request: ImageEvidenceRequest,
    runner: EvidenceCommandRunner,
    scanner: str,
) -> dict[str, dict[str, Any]]:
    """Collect lock SBOM, full-image SBOM, and vulnerability evidence.

    Args:
        repository_root: Repository used as scanner working directory.
        request: Exact image, source, lock, and evidence identity.
        runner: Injectable argument-vector command runner.
        scanner: Requested scanner or ``auto``.

    Returns:
        dict[str, dict[str, Any]]: Sanitized dependency, image, and policy maps.

    Side Effects:
        Writes two ignored SPDX files and runs the selected image scanner.

    Raises:
        ImageEvidenceError: If scanner resolution, SBOM validation, or policy fails.
        OSError: If evidence files cannot be written.
    """

    dependency_sbom_path = write_dependency_sbom(request)
    selected_scanner = resolve_scanner(repository_root, runner, scanner)
    image_sbom_path = write_image_sbom(
        repository_root,
        request,
        runner,
        selected_scanner,
    )
    vulnerability = run_vulnerability_scan(
        repository_root,
        request,
        runner,
        selected_scanner,
    )
    return {
        "dependencyEvidence": {
            "lockSha256": request.dependency_lock_sha256,
            "sbomPath": request.dependency_sbom_path.relative_to(
                repository_root
            ).as_posix(),
            "sbomSha256": _sha256_file(dependency_sbom_path),
            "sbomFormat": "SPDX-2.3",
        },
        "imageEvidence": {
            "sbomPath": request.image_sbom_path.relative_to(
                repository_root
            ).as_posix(),
            "sbomSha256": _sha256_file(image_sbom_path),
            "sbomFormat": "SPDX",
            "sbomScanner": selected_scanner,
        },
        "vulnerabilityPolicy": vulnerability,
    }
