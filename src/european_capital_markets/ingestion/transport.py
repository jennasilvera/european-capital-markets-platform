"""Transport-layer results for controlled ingestion."""

from dataclasses import dataclass
from datetime import datetime


def _require_non_blank(
    value: str,
    field_name: str,
) -> None:
    if not value.strip():
        raise ValueError(
            f"{field_name} must not be blank."
        )


@dataclass(frozen=True, slots=True)
class HttpRetrievedPayload:
    """One successfully retrieved HTTP payload before raw landing."""

    request_url: str
    response_url: str
    retrieved_at: datetime
    status_code: int
    content: bytes
    media_type: str | None = None
    last_modified: str | None = None
    etag: str | None = None
    cache_control: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(
            self.request_url,
            "request_url",
        )
        _require_non_blank(
            self.response_url,
            "response_url",
        )

        if self.retrieved_at.utcoffset() is None:
            raise ValueError(
                "retrieved_at must be timezone-aware."
            )

        if (
            isinstance(self.status_code, bool)
            or not isinstance(self.status_code, int)
        ):
            raise TypeError(
                "status_code must be an integer."
            )

        if not 100 <= self.status_code <= 599:
            raise ValueError(
                "status_code must be a valid HTTP status."
            )

        if not isinstance(self.content, bytes):
            raise TypeError(
                "content must be bytes."
            )

        for field_name in (
            "media_type",
            "last_modified",
            "etag",
            "cache_control",
        ):
            value = getattr(
                self,
                field_name,
            )

            if value is not None:
                _require_non_blank(
                    value,
                    field_name,
                )
