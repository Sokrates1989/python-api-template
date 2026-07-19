"""Validate and render the Python-owned Template V2 records starter contract.

The module gives the backend repository an independently testable source
contract while allowing the Flutter pair orchestrator to consume exact,
checksum-pinned templates instead of duplicating backend business logic.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


CONTRACT_RELATIVE_PATH = "template_v2/records_starter_contract.json"
TEMPLATE_ROOT_RELATIVE_PATH = "template_v2/records_starter/templates"
SUPPORTED_CONTRACT_ID = "template-v2-records-starter"
SUPPORTED_CONTRACT_VERSION = 1
SUPPORTED_STARTER_REVISION = "1.0.0"
_APP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_FILE_BYTES = 1_000_000
_REQUIRED_OUTPUT_PATHS = (
    "definition.py",
    "migrations/README.md",
    "migrations/versions/__REVISION_ID__.py",
    "models/__init__.py",
    "models/record.py",
    "repositories/__init__.py",
    "repositories/records_repository.py",
    "routes/__init__.py",
    "routes/records.py",
    "schemas/__init__.py",
    "schemas/records.py",
    "services/__init__.py",
    "services/records_service.py",
)


class RecordsStarterContractError(ValueError):
    """Report stable content-free records contract failures.

    Attributes:
        issues: Sorted unique validation diagnostics.
    """

    def __init__(self, issues: list[str] | tuple[str, ...]) -> None:
        """Store at least one normalized validation issue.

        Args:
            issues: Validation diagnostics without machine-local paths.

        Raises:
            ValueError: If no issue is supplied.
        """

        normalized = tuple(sorted(set(issues)))
        if not normalized:
            raise ValueError("RecordsStarterContractError requires an issue")
        self.issues = normalized
        super().__init__("\n".join(normalized))


@dataclass(frozen=True)
class RecordsStarterTemplate:
    """Describe one checksum-pinned source-to-output mapping.

    Attributes:
        template_path: Portable path below the canonical template root.
        output_path: Portable app-relative path with optional revision token.
        sha256: SHA-256 of normalized template bytes.
        content: Exact validated source template text.
    """

    template_path: str
    output_path: str
    sha256: str
    content: str


@dataclass(frozen=True)
class RecordsStarterContract:
    """Hold the validated starter identity and renderable source templates.

    Attributes:
        contract_version: Machine-readable contract schema version.
        starter_revision: Semantic records starter revision.
        templates: Ordered checksum-pinned source templates.
    """

    contract_version: int
    starter_revision: str
    templates: tuple[RecordsStarterTemplate, ...]

    def render(self, app_id: str) -> dict[str, bytes]:
        """Render the complete app-local records starter.

        Args:
            app_id: Validated 3-48 character snake-case generated app id.

        Returns:
            Output paths mapped to UTF-8 bytes in contract order.

        Raises:
            RecordsStarterContractError: If the app id is unsafe.
        """

        if not _APP_ID_PATTERN.fullmatch(app_id) or not 3 <= len(app_id) <= 48:
            raise RecordsStarterContractError(["records starter app_id: invalid value"])
        substitutions = _render_substitutions(app_id)
        outputs: dict[str, bytes] = {}
        for template in self.templates:
            path = _substitute(template.output_path, substitutions)
            source = _substitute(template.content, substitutions)
            outputs[path] = source.encode("utf-8")
        return outputs


def _render_substitutions(app_id: str) -> dict[str, str]:
    """Build bounded identifiers derived only from a validated app id.

    Args:
        app_id: Validated generated app id.

    Returns:
        Placeholder values safe for Python and PostgreSQL identifiers.
    """

    return {
        "__APP_ID__": app_id,
        "__TABLE_NAME__": f"{app_id}_records",
        "__INDEX_NAME__": f"ix_{app_id}_owner",
        "__REVISION_ID__": f"{app_id}_001_records",
    }


def _substitute(source: str, substitutions: dict[str, str]) -> str:
    """Replace every declared records starter token.

    Args:
        source: Template path or text.
        substitutions: Complete placeholder mapping.

    Returns:
        Rendered text with no declared placeholders remaining.
    """

    rendered = source
    for token, value in substitutions.items():
        rendered = rendered.replace(token, value)
    return rendered


def _portable_path(value: Any, *, field: str) -> str:
    """Validate one safe portable relative contract path.

    Args:
        value: Candidate JSON value.
        field: Stable diagnostic field name.

    Returns:
        Validated POSIX path string.

    Raises:
        RecordsStarterContractError: If the path is absent or unsafe.
    """

    if not isinstance(value, str) or not value:
        raise RecordsStarterContractError([f"{field}: expected a path"])
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or path.as_posix() != value:
        raise RecordsStarterContractError([f"{field}: unsafe path"])
    return value


def _read_json(root: Path) -> dict[str, Any]:
    """Read the bounded contract manifest.

    Args:
        root: Backend repository root.

    Returns:
        Parsed manifest object.

    Raises:
        RecordsStarterContractError: If the manifest is unsafe or invalid.
    """

    path = root.joinpath(*CONTRACT_RELATIVE_PATH.split("/"))
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
            raise OSError
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RecordsStarterContractError(
            [f"{CONTRACT_RELATIVE_PATH}: expected bounded UTF-8 JSON"]
        ) from error
    if not isinstance(value, dict):
        raise RecordsStarterContractError([f"{CONTRACT_RELATIVE_PATH}: expected an object"])
    return value


def _read_template(root: Path, relative_path: str) -> str:
    """Read one bounded regular template and normalize line endings.

    Args:
        root: Backend repository root.
        relative_path: Portable path below the records template root.

    Returns:
        UTF-8 template text with LF line endings.

    Raises:
        RecordsStarterContractError: If the source is unsafe or unreadable.
    """

    path = root.joinpath(*TEMPLATE_ROOT_RELATIVE_PATH.split("/"), *relative_path.split("/"))
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
            raise OSError
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise RecordsStarterContractError(
            [f"records template {relative_path}: expected bounded UTF-8 text"]
        ) from error
    return content.replace("\r\n", "\n").replace("\r", "\n")


def _parse_templates(root: Path, document: dict[str, Any]) -> tuple[RecordsStarterTemplate, ...]:
    """Validate every declared template mapping and digest.

    Args:
        root: Backend repository root.
        document: Parsed records contract manifest.

    Returns:
        Ordered validated templates.

    Raises:
        RecordsStarterContractError: If a declaration or checksum drifted.
    """

    values = document.get("templates")
    if not isinstance(values, list) or not values:
        raise RecordsStarterContractError(["contract.templates: expected entries"])
    templates: list[RecordsStarterTemplate] = []
    issues: list[str] = []
    for index, value in enumerate(values):
        try:
            template = _parse_template(root, value, index)
        except RecordsStarterContractError as error:
            issues.extend(error.issues)
        else:
            templates.append(template)
    paths = [item.output_path for item in templates]
    if tuple(paths) != _REQUIRED_OUTPUT_PATHS:
        issues.append("contract.templates: expected the complete ordered records starter")
    if issues:
        raise RecordsStarterContractError(issues)
    return tuple(templates)


def _parse_template(root: Path, value: Any, index: int) -> RecordsStarterTemplate:
    """Validate one declared source-to-output mapping.

    Args:
        root: Backend repository root.
        value: Candidate template declaration.
        index: Manifest list index used in diagnostics.

    Returns:
        Validated template mapping and content.

    Raises:
        RecordsStarterContractError: If fields or digest are invalid.
    """

    field = f"contract.templates[{index}]"
    if not isinstance(value, dict):
        raise RecordsStarterContractError([f"{field}: expected an object"])
    template_path = _portable_path(value.get("template_path"), field=f"{field}.template_path")
    output_path = _portable_path(value.get("output_path"), field=f"{field}.output_path")
    expected_hash = value.get("sha256")
    content = _read_template(root, template_path)
    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if not isinstance(expected_hash, str) or not _SHA256_PATTERN.fullmatch(expected_hash):
        raise RecordsStarterContractError([f"{field}.sha256: invalid digest"])
    if actual_hash != expected_hash:
        raise RecordsStarterContractError([f"records template {template_path}: checksum drifted"])
    return RecordsStarterTemplate(template_path, output_path, expected_hash, content)


def validate_records_starter_contract(root: Path) -> RecordsStarterContract:
    """Validate the canonical B3 source contract and all declared templates.

    Args:
        root: Backend repository root containing ``template_v2``.

    Returns:
        Validated independently renderable records starter contract.

    Raises:
        RecordsStarterContractError: If identity, policy, source, or digest drifts.
    """

    document = _read_json(root)
    expected = {
        "contract_id": SUPPORTED_CONTRACT_ID,
        "contract_version": SUPPORTED_CONTRACT_VERSION,
        "starter_revision": SUPPORTED_STARTER_REVISION,
        "standard_profile": {"auth_provider": "keycloak", "backend": "postgresql"},
        "route_prefixes": ["/records"],
    }
    issues = [
        f"contract.{field}: unsupported value"
        for field, value in expected.items()
        if document.get(field) != value
    ]
    if issues:
        raise RecordsStarterContractError(issues)
    templates = _parse_templates(root, document)
    return RecordsStarterContract(
        contract_version=SUPPORTED_CONTRACT_VERSION,
        starter_revision=SUPPORTED_STARTER_REVISION,
        templates=templates,
    )
