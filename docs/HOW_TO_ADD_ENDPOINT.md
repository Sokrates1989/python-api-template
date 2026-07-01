# How To Add A New Endpoint

This guide shows the current app-slice-first workflow for adding backend
endpoints. Product endpoints belong under `app/apps/<app_id>/`; shared reusable
route groups belong under `app/api/shared_routes/`.

Never add `/api/` as a route prefix in this API service.

## Choose The Owner

| Endpoint type | Location | Registration |
| --- | --- | --- |
| Product-specific endpoint | `app/apps/<app_id>/routes/` | `RouteRegistration` in the app definition. |
| Product endpoint using shared runtime | `app/apps/<app_id>/routes/` | App route facade imports shared service/schema contracts. |
| Reusable platform/shared endpoint | `app/api/shared_routes/` | App opts in through `shared_route_groups`. |
| Legacy compatibility endpoint | `app/api/routes/` | Do not add new endpoints here. |

## Add A Product Endpoint

The example below adds a product-owned `products` route to
`app/apps/template_app/`.

### 1. Create The Service

Create `app/apps/template_app/services/product_service.py`.

```python
"""
Product service for the Template App slice.

This module keeps product-specific behavior inside the owning app slice.
"""


class ProductService:
    """
    Provide product catalog operations for Template App.

    Attributes:
        products (list[dict[str, object]]): In-memory example product rows.

    Methods:
        list_products: Return the product catalog.
    """

    def __init__(self) -> None:
        """
        Initialize the example product catalog.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            Stores in-memory example data on the service instance.
        """
        self.products = [
            {"id": 1, "name": "Laptop", "price": 999.99},
            {"id": 2, "name": "Mouse", "price": 29.99},
        ]

    def list_products(self) -> dict[str, object]:
        """
        Return all products.

        Args:
            None.

        Returns:
            dict[str, object]: Product list and count.

        Side Effects:
            None.
        """
        return {"products": self.products, "count": len(self.products)}
```

### 2. Create The Route Facade

Create `app/apps/template_app/routes/products.py`.

```python
"""
Product routes owned by the Template App slice.

The router exposes Template App product behavior and is mounted only when the
Template App definition registers it.
"""
from fastapi import APIRouter

from apps.template_app.services.product_service import ProductService

router = APIRouter(tags=["products"], prefix="/v1/products")


def get_service() -> ProductService:
    """
    Return the Template App product service.

    Args:
        None.

    Returns:
        ProductService: App-owned service facade.

    Side Effects:
        Instantiates the service for the current request.
    """
    return ProductService()


@router.get("")
def list_products() -> dict[str, object]:
    """
    Return the Template App product catalog.

    Args:
        None.

    Returns:
        dict[str, object]: Product list and count.

    Side Effects:
        None.
    """
    return get_service().list_products()
```

### 3. Register The Route In The App Definition

Edit `app/apps/template_app/definition.py`.

```python
from apps.contracts import BackendAppDefinition, RouteRegistration
from apps.template_app.config import TEMPLATE_APP_CONFIG
from apps.template_app.routes import products, sync, wellness


TEMPLATE_APP_DEFINITION = BackendAppDefinition(
    app_id=TEMPLATE_APP_CONFIG.app_id,
    display_name=TEMPLATE_APP_CONFIG.display_name,
    backend_data_profile=TEMPLATE_APP_CONFIG.backend_data_profile,
    route_registrations=(
        RouteRegistration(
            router=wellness.router,
            external_prefix=TEMPLATE_APP_CONFIG.wellness_mount_prefix,
            public_prefix=TEMPLATE_APP_CONFIG.wellness_public_prefix,
        ),
        RouteRegistration(
            router=products.router,
            external_prefix=TEMPLATE_APP_CONFIG.wellness_mount_prefix,
            public_prefix="/template/v1/products",
        ),
        RouteRegistration(
            router=sync.router,
            external_prefix="",
            public_prefix=TEMPLATE_APP_CONFIG.sync_public_prefix,
        ),
    ),
)
```

Do not mount product routers directly in `app/main.py`.

### 4. Test The Endpoint

```bash
curl http://localhost:8081/template/v1/products
```

Use the selected app's actual mount prefix. Swagger UI is still available at
`http://localhost:8081/docs`.

## Add A Shared Route Group

Create shared routes only when the route is product-neutral and reusable across
apps. Place the module under `app/api/shared_routes/`.

```python
"""
Shared operational ping routes.

Apps opt in by listing the route group in shared_route_groups.
"""
from fastapi import APIRouter

router = APIRouter(tags=["ops"], prefix="/ops")


@router.get("/ping")
def ping() -> dict[str, str]:
    """
    Return a lightweight operational ping.

    Args:
        None.

    Returns:
        dict[str, str]: Static status payload.

    Side Effects:
        None.
    """
    return {"status": "ok"}
```

Then add the group to `_available_shared_route_groups()` in `app/main.py` and
opt in from each app definition that needs it:

```python
BackendAppDefinition(
    ...,
    shared_route_groups=("ops", "users"),
)
```

## Endpoint Checklist

- Product name, app copy, app-only table, reward, Startlist, streak, or Sonnen
  behavior: keep it under `app/apps/<app_id>/`.
- Shared reusable HTTP surface: put it under `app/api/shared_routes/` and make
  apps opt in explicitly.
- Shared runtime without product semantics: `app/backend/` or `app/api/schemas/`
  can be appropriate.
- Product SQL migration: `app/apps/<app_id>/migrations/versions/`.
- Provider-wide migration: `alembic/versions/`.
- Route prefix starts with `/api/`: reject it.
