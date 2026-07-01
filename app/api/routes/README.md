# Legacy Route Package

`app\api\routes\` is retained for compatibility with older imports and older
documentation examples. New product endpoints must not be added here.

Use these locations instead:

- Product-specific route facades: `app\apps\<app_id>\routes\`.
- Reusable shared route groups: `app\api\shared_routes\`.
- Product-specific services: `app\apps\<app_id>\services\`.
- Product-specific schemas or schema aliases: `app\apps\<app_id>\schemas\`.

Selected apps expose app-owned routes through
`app\apps\<app_id>\definition.py`. Shared route groups are mounted only when an
app lists them in `BackendAppDefinition.shared_route_groups`.

Do not add route prefixes that start with slash-api in this API service.
