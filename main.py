"""ASGI entrypoint for uvicorn."""

from backend.app import create_app

app = create_app()
