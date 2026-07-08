"""Custom exception classes and error handling."""

from fastapi import HTTPException, status


class SynclookError(Exception):
    """Base exception for Synclook."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(self.message)


class ImageProcessingError(SynclookError):
    """Raised when image processing fails."""

    pass


class AgentError(SynclookError):
    """Raised when an agent encounters an error."""

    pass


class LLMError(SynclookError):
    """Raised when LLM communication fails."""

    pass


class ToolError(SynclookError):
    """Raised when a tool execution fails."""

    pass


class ProductSearchError(SynclookError):
    """Raised when product search via SerpAPI fails."""

    pass


def raise_not_found(resource: str, identifier: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} with id '{identifier}' not found",
    )


def raise_bad_request(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )
