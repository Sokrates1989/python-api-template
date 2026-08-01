"""Safe exception contract shared by local Keycloak bootstrap modules."""


class KeycloakBootstrapError(RuntimeError):
    """Raised when a bounded local Keycloak bootstrap operation fails."""
