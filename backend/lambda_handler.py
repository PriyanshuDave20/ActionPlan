"""AWS Lambda entry point for the FastAPI application.

Adapts the existing FastAPI app (``app.main:app``) to Lambda using Mangum.
This is the only Lambda-specific adapter layer: the FastAPI routes in
``app/`` remain the source of truth and are reused unchanged.

The application must NOT start uvicorn here. Lambda invokes this handler,
Mangum translates the API Gateway HTTP API event into an ASGI request, and
FastAPI handles it exactly as it would locally.
"""

import logging

from mangum import Mangum

from app.main import app

# Route CloudWatch Logs through the standard Python logging pipeline so
# unhandled exceptions and application logs are visible in CloudWatch.
logging.basicConfig(level=logging.INFO)

handler = Mangum(app, lifespan="off")