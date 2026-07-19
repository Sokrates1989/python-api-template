"""Validate and summarize the Template V2 B4 networked recipe catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from template_v2.networked_recipes_contract import (  # noqa: E402
    NetworkedRecipesContractError,
    validate_networked_recipes_contract,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only catalog validation parser.

    Returns:
        Parser accepting an optional repository root and JSON output switch.
    """

    parser = argparse.ArgumentParser(
        description="Validate the Python-owned Template V2 networked recipe catalog."
    )
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate the selected repository and print only content-free identity.

    Args:
        argv: Optional command arguments. Defaults to process arguments.

    Returns:
        Zero on success and one for a stable validation failure.
    """

    arguments = build_parser().parse_args(argv)
    try:
        catalog = validate_networked_recipes_contract(arguments.root.resolve())
    except NetworkedRecipesContractError as error:
        for issue in error.issues:
            print(issue)
        return 1
    value = {
        "catalog_revision": catalog.catalog_revision,
        "contract_version": catalog.contract_version,
        "manifest_sha256": catalog.manifest_sha256,
        "recipe_count": len(catalog.recipes),
        "recipe_ids": [recipe.backend_recipe_id for recipe in catalog.recipes],
    }
    if arguments.json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "Template V2 networked recipe catalog valid: "
            f"revision={catalog.catalog_revision} recipes={len(catalog.recipes)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
