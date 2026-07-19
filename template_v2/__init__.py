"""Template V2 backend foundation contracts and lifecycle tooling."""

from .backend_foundation_contract import (
    BackendFoundationContractError,
    BackendFoundationIdentity,
    validate_backend_foundation,
)
from .backend_lifecycle import execute_backend_lifecycle
from .networked_recipes_contract import (
    NetworkedRecipesCatalog,
    NetworkedRecipesContractError,
    validate_networked_recipes_contract,
)
from .networked_recipe_sources import (
    RenderableNetworkedRecipe,
    RenderedNetworkedRecipeFile,
    validate_networked_recipe_sources,
)

__all__ = [
    "BackendFoundationContractError",
    "BackendFoundationIdentity",
    "NetworkedRecipesCatalog",
    "NetworkedRecipesContractError",
    "RenderableNetworkedRecipe",
    "RenderedNetworkedRecipeFile",
    "validate_backend_foundation",
    "validate_networked_recipes_contract",
    "validate_networked_recipe_sources",
    "execute_backend_lifecycle",
]
