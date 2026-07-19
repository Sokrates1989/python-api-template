"""Validate and render checksum-pinned Template V2 networked recipe sources.

The catalog and source manifests are separate so contract-only declarations
cannot be mistaken for executable generation support. This module performs no
filesystem writes and returns app-relative UTF-8 files only after every source
checksum and output boundary passes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .networked_recipes_contract import (
    NetworkedRecipeContract,
    NetworkedRecipesCatalog,
    NetworkedRecipesContractError,
)


_APP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_FILE_BYTES = 1_000_000
_SOURCE_FIELDS = frozenset({"backend_recipe_id", "backend_revision", "templates"})
_TEMPLATE_FIELDS = frozenset({"output_path", "sha256", "template_path"})


@dataclass(frozen=True)
class RenderedNetworkedRecipeFile:
    """Hold one rendered app-relative backend source file.

    Attributes:
        relative_path: Portable path below the generated backend app.
        content: Complete rendered UTF-8 bytes.
    """

    relative_path: str
    content: bytes


@dataclass(frozen=True)
class _SourceTemplate:
    """Hold one validated template-to-output mapping.

    Attributes:
        output_path: App-relative destination containing optional app tokens.
        content: LF-normalized checksum-validated source text.
    """

    output_path: str
    content: str


@dataclass(frozen=True)
class RenderableNetworkedRecipe:
    """Hold one exact source contract ready for safe substitution.

    Attributes:
        backend_recipe_id: Matching catalog recipe identifier.
        backend_revision: Matching renderable backend revision.
        source_manifest_sha256: Digest of exact source-manifest bytes.
        templates: Complete declared migration and service source set.
    """

    backend_recipe_id: str
    backend_revision: str
    source_manifest_sha256: str
    templates: tuple[_SourceTemplate, ...]

    def render(self, app_id: str) -> tuple[RenderedNetworkedRecipeFile, ...]:
        """Substitute one validated app id into all paths and sources.

        Args:
            app_id: Validated generated backend application id.

        Returns:
            Stable path-sorted rendered source files.

        Raises:
            NetworkedRecipesContractError: If the app id is unsafe.
        """

        if not _APP_ID_PATTERN.fullmatch(app_id):
            raise NetworkedRecipesContractError(["app_id: unsafe recipe substitution"])
        files = tuple(
            RenderedNetworkedRecipeFile(
                relative_path=template.output_path.replace("__APP_ID__", app_id),
                content=template.content.replace("__APP_ID__", app_id).encode("utf-8"),
            )
            for template in self.templates
        )
        return tuple(sorted(files, key=lambda item: item.relative_path.casefold()))


def _portable_path(value: Any, field: str) -> str:
    """Validate one portable non-empty relative path.

    Args:
        value: Candidate JSON value.
        field: Stable diagnostic field.

    Returns:
        Validated POSIX path string.

    Raises:
        NetworkedRecipesContractError: If the path is absent or unsafe.
    """

    if not isinstance(value, str) or not value:
        raise NetworkedRecipesContractError([f"{field}: expected a path"])
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or path.as_posix() != value:
        raise NetworkedRecipesContractError([f"{field}: unsafe path"])
    return value


def _read_json(root: Path, relative_path: str) -> tuple[dict[str, Any], bytes]:
    """Read one bounded regular UTF-8 JSON object.

    Args:
        root: Backend repository root.
        relative_path: Portable manifest path below the root.

    Returns:
        Parsed JSON object and exact bytes.

    Raises:
        NetworkedRecipesContractError: If the manifest is unsafe or invalid.
    """

    path = root.joinpath(*relative_path.split("/"))
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
            raise OSError
        content = path.read_bytes()
        document = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise NetworkedRecipesContractError(
            [f"recipe source {relative_path}: expected bounded UTF-8 JSON"]
        ) from error
    if not isinstance(document, dict):
        raise NetworkedRecipesContractError(
            [f"recipe source {relative_path}: expected an object"]
        )
    return document, content


def _read_template(root: Path, source_contract: str, template_path: str) -> str:
    """Read one bounded template below its source contract directory.

    Args:
        root: Backend repository root.
        source_contract: Portable recipe source-manifest path.
        template_path: Portable path below the adjacent templates directory.

    Returns:
        LF-normalized UTF-8 source text.

    Raises:
        NetworkedRecipesContractError: If the template is unsafe or unreadable.
    """

    base = PurePosixPath(source_contract).parent / "templates"
    relative_path = (base / PurePosixPath(template_path)).as_posix()
    path = root.joinpath(*relative_path.split("/"))
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
            raise OSError
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise NetworkedRecipesContractError(
            [f"recipe template {template_path}: expected bounded UTF-8 text"]
        ) from error
    return content.replace("\r\n", "\n").replace("\r", "\n")


def _parse_template(
    root: Path,
    recipe: NetworkedRecipeContract,
    value: Any,
    index: int,
) -> _SourceTemplate:
    """Validate one source mapping and its normalized checksum.

    Args:
        root: Backend repository root.
        recipe: Matching validated catalog recipe.
        value: Candidate template declaration.
        index: Stable template index.

    Returns:
        Checksum-validated template mapping.

    Raises:
        NetworkedRecipesContractError: If fields, paths, or checksum drift.
    """

    field = f"recipe {recipe.backend_recipe_id}.templates[{index}]"
    if not isinstance(value, dict) or set(value) != _TEMPLATE_FIELDS:
        raise NetworkedRecipesContractError([f"{field}: unexpected fields"])
    template_path = _portable_path(value.get("template_path"), f"{field}.template_path")
    output_path = _portable_path(value.get("output_path"), f"{field}.output_path")
    assert recipe.source_contract is not None
    content = _read_template(root, recipe.source_contract, template_path)
    expected_sha256 = value.get("sha256")
    actual_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if not isinstance(expected_sha256, str) or not _SHA256_PATTERN.fullmatch(expected_sha256):
        raise NetworkedRecipesContractError([f"{field}.sha256: invalid digest"])
    if actual_sha256 != expected_sha256:
        raise NetworkedRecipesContractError([f"recipe template {template_path}: checksum drifted"])
    return _SourceTemplate(output_path=output_path, content=content)


def _validate_dependency_lock(
    root: Path,
    recipe: NetworkedRecipeContract,
) -> None:
    """Validate one selected-only dependency lock against its catalog digest.

    Args:
        root: Backend repository root.
        recipe: Validated networked recipe contract.

    Returns:
        None when the recipe has no overlay or its exact lock matches.

    Raises:
        NetworkedRecipesContractError: If the lock is missing, unsafe, or drifted.
    """

    profile = recipe.python_dependency_profile
    expected_sha256 = recipe.python_dependency_lock_sha256
    if profile is None:
        return
    path = root / "template_v2" / "dependency_profiles" / profile / "pdm.lock"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
            raise OSError
        content = path.read_bytes()
    except OSError as error:
        raise NetworkedRecipesContractError(
            [f"recipe dependency profile {profile}: expected bounded lock"]
        ) from error
    if expected_sha256 is None or hashlib.sha256(content).hexdigest() != expected_sha256:
        raise NetworkedRecipesContractError(
            [f"recipe dependency profile {profile}: lock checksum drifted"]
        )


def _validate_one_source(
    root: Path,
    recipe: NetworkedRecipeContract,
) -> RenderableNetworkedRecipe:
    """Validate one renderable recipe's exact source manifest and templates.

    Args:
        root: Backend repository root.
        recipe: Renderable validated catalog recipe.

    Returns:
        Validated renderable recipe.

    Raises:
        NetworkedRecipesContractError: If identity or output coverage drifts.
    """

    assert recipe.source_contract is not None
    document, manifest_bytes = _read_json(root, recipe.source_contract)
    if set(document) != _SOURCE_FIELDS:
        raise NetworkedRecipesContractError(
            [f"recipe source {recipe.backend_recipe_id}: unexpected fields"]
        )
    if (
        document.get("backend_recipe_id") != recipe.backend_recipe_id
        or document.get("backend_revision") != recipe.backend_revision
    ):
        raise NetworkedRecipesContractError(
            [f"recipe source {recipe.backend_recipe_id}: identity drifted"]
        )
    values = document.get("templates")
    if not isinstance(values, list) or not values:
        raise NetworkedRecipesContractError(
            [f"recipe source {recipe.backend_recipe_id}: expected templates"]
        )
    templates = tuple(
        _parse_template(root, recipe, value, index)
        for index, value in enumerate(values)
    )
    _validate_dependency_lock(root, recipe)
    expected_outputs = (*recipe.migration_paths, *recipe.service_paths)
    if tuple(item.output_path for item in templates) != expected_outputs:
        raise NetworkedRecipesContractError(
            [f"recipe source {recipe.backend_recipe_id}: incomplete output coverage"]
        )
    return RenderableNetworkedRecipe(
        backend_recipe_id=recipe.backend_recipe_id,
        backend_revision=recipe.backend_revision,
        source_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        templates=templates,
    )


def validate_networked_recipe_sources(
    root: Path,
    catalog: NetworkedRecipesCatalog,
) -> tuple[RenderableNetworkedRecipe, ...]:
    """Validate every and only renderable recipe source contract.

    Args:
        root: Backend repository root.
        catalog: Previously validated catalog.

    Returns:
        Renderable recipes in catalog order; contract-only entries are absent.

    Raises:
        NetworkedRecipesContractError: If any renderable source contract drifts.
    """

    return tuple(
        _validate_one_source(root.resolve(), recipe)
        for recipe in catalog.recipes
        if recipe.implementation_status == "renderable"
    )
