"""Request logging middleware for debugging."""
from fastapi import FastAPI, Request, Response
from api.settings import settings


async def log_request_headers(request: Request, call_next):
    """
    Log request and response details for debugging purposes.
    
    This middleware is only active when DEBUG mode is enabled.
    """
    # Output basic request info.
    print(f"🔹 Received request: {request.method} {request.url}")

    # Read and log the request headers.
    headers = request.headers
    print(f"🔹 Request headers: {headers}")

    # Read and log the request body
    body = await request.body()
    print(f"🔹 Request body: {body.decode('utf-8') if body else 'No Body'}")

    response = await call_next(request)

    # Collect the response body so it can be logged and re-sent.
    response_body = b""
    async for chunk in response.body_iterator:
        response_body += chunk

    print(f"🟪 Response status: {response.status_code}")
    print(f"🟪 Response headers: {dict(response.headers)}")
    
    # Only decode text responses, skip binary content (like gzipped files)
    content_type = response.headers.get('content-type', '')
    if response_body:
        # Check if it's a binary content type
        is_binary = any(binary_type in content_type.lower() for binary_type in 
                      ['application/octet-stream', 'application/gzip', 'application/zip', 
                       'image/', 'video/', 'audio/', 'application/pdf'])
        
        if is_binary:
            print(f"🟪 Response body: <Binary content, {len(response_body)} bytes>")
        else:
            try:
                print(f"🟪 Response body: {response_body.decode('utf-8')}")
            except UnicodeDecodeError:
                print(f"🟪 Response body: <Binary content, {len(response_body)} bytes>")
    else:
        print(f"🟪 Response body: No Body")

    # call_next returns a streaming Response whose body_iterator can only be consumed once.
    # We iterate above to log the payload, so we must rebuild the Response to forward the body.
    new_response = Response(
        content=response_body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=response.background,
    )

    return new_response


def setup_logging_middleware(app: FastAPI) -> None:
    """
    Configure request logging middleware for the FastAPI application.
    
    This middleware is only enabled when DEBUG mode is active.
    
    Args:
        app: The FastAPI application instance
    """
    if settings.DEBUG:
        app.middleware("http")(log_request_headers)
