"""Immutable filesystem landing for retrieved raw market-data artifacts."""

from __future__ import annotations

import os
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from european_capital_markets.ingestion.contracts import (
    RawRetrievalArtifact,
    RetrievalSource,
    compute_sha256,
    validate_raw_artifact_content,
)
from european_capital_markets.ingestion.transport import (
    HttpRetrievedPayload,
)

_NAMESPACE_RE = re.compile(
    r"[a-z][a-z0-9_-]{0,63}"
)

_SUFFIX_RE = re.compile(
    r"\.[a-z0-9]{1,10}"
)

_ARCHIVE_COMPONENT_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
)


@dataclass(frozen=True, slots=True)
class RawArtifactLanding:
    """One successfully published immutable raw artifact."""

    artifact: RawRetrievalArtifact
    filesystem_path: Path
    storage_token: UUID


def _validate_namespace(
    namespace: str,
) -> str:
    if _NAMESPACE_RE.fullmatch(
        namespace
    ) is None:
        raise ValueError(
            "Raw archive namespace must match "
            "[a-z][a-z0-9_-]{0,63}."
        )

    return namespace


def _validate_suffix(
    suffix: str,
) -> str:
    if _SUFFIX_RE.fullmatch(
        suffix
    ) is None:
        raise ValueError(
            "Raw artifact suffix must be a lower-case "
            "extension such as '.csv'."
        )

    return suffix


def _validate_archive_location_prefix(
    value: str,
) -> PurePosixPath:
    if not value.strip():
        raise ValueError(
            "archive_location_prefix must not be blank."
        )

    prefix = PurePosixPath(
        value
    )

    if prefix.is_absolute():
        raise ValueError(
            "archive_location_prefix must be relative."
        )

    if not prefix.parts:
        raise ValueError(
            "archive_location_prefix must contain "
            "at least one path component."
        )

    for part in prefix.parts:
        if (
            part in {".", ".."}
            or _ARCHIVE_COMPONENT_RE.fullmatch(
                part
            )
            is None
        ):
            raise ValueError(
                "archive_location_prefix contains "
                "an unsafe path component."
            )

    return prefix


def _directory_open_flags() -> int:
    if not hasattr(
        os,
        "O_DIRECTORY",
    ):
        raise RuntimeError(
            "Immutable raw landing requires "
            "os.O_DIRECTORY support."
        )

    if not hasattr(
        os,
        "O_NOFOLLOW",
    ):
        raise RuntimeError(
            "Immutable raw landing requires "
            "os.O_NOFOLLOW support."
        )

    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
    )


def _file_create_flags() -> int:
    if not hasattr(
        os,
        "O_NOFOLLOW",
    ):
        raise RuntimeError(
            "Immutable raw landing requires "
            "os.O_NOFOLLOW support."
        )

    return (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
    )


def _fsync_directory_fd(
    directory_fd: int,
) -> None:
    os.fsync(
        directory_fd
    )


def _open_archive_directory(
    root: Path,
    components: tuple[str, ...],
) -> int:
    flags = _directory_open_flags()

    current_fd = os.open(
        root,
        flags,
    )

    try:
        for component in components:
            created = False

            try:
                os.mkdir(
                    component,
                    mode=0o750,
                    dir_fd=current_fd,
                )
                created = True
            except FileExistsError:
                pass

            if created:
                _fsync_directory_fd(
                    current_fd
                )

            next_fd = os.open(
                component,
                flags,
                dir_fd=current_fd,
            )

            os.close(
                current_fd
            )

            current_fd = next_fd

        result_fd = current_fd
        current_fd = -1

        return result_fd
    finally:
        if current_fd >= 0:
            os.close(
                current_fd
            )


class ImmutableRawArtifactStore:
    """Publish retrieved bytes without permitting silent replacement."""

    def __init__(
        self,
        *,
        root: Path,
        archive_location_prefix: str,
    ) -> None:
        self.root = Path(
            root
        )

        self.archive_location_prefix = (
            _validate_archive_location_prefix(
                archive_location_prefix
            )
        )

        if not self.root.exists():
            raise FileNotFoundError(
                "Raw artifact root does not exist: "
                f"{self.root}"
            )

        if self.root.is_symlink():
            raise ValueError(
                "Raw artifact root must not be a symlink."
            )

        if not self.root.is_dir():
            raise NotADirectoryError(
                f"Raw artifact root is not a directory: "
                f"{self.root}"
            )

        # Opening the root with O_NOFOLLOW verifies that the
        # platform can enforce the required directory semantics.
        root_fd = os.open(
            self.root,
            _directory_open_flags(),
        )

        try:
            _fsync_directory_fd(
                root_fd
            )
        finally:
            os.close(
                root_fd
            )

    def land_http_retrieval(
        self,
        *,
        market_series_id: str,
        source: RetrievalSource,
        retrieval: HttpRetrievedPayload,
        namespace: str,
        suffix: str,
        storage_token: UUID | None = None,
    ) -> RawArtifactLanding:
        """Durably publish one successful HTTP retrieval.

        The storage token is an operational filesystem identity. It is not a
        canonical entity identifier and is intentionally independent of the
        content digest.
        """

        namespace = _validate_namespace(
            namespace
        )

        suffix = _validate_suffix(
            suffix
        )

        if storage_token is None:
            storage_token = uuid4()
        elif not isinstance(
            storage_token,
            UUID,
        ):
            raise TypeError(
                "storage_token must be a UUID."
            )

        if not 200 <= retrieval.status_code <= 299:
            raise ValueError(
                "Only successful HTTP retrievals may be "
                "landed as raw market-data artifacts."
            )

        if source.url != retrieval.response_url:
            raise ValueError(
                "RetrievalSource.url must equal the actual "
                "HTTP response URL used for raw provenance."
            )

        content_sha256 = compute_sha256(
            retrieval.content
        )

        # Validate all canonical raw-artifact fields before any archive
        # directory or file is created.
        preflight = RawRetrievalArtifact(
            market_series_id=market_series_id,
            source=source,
            retrieved_at=retrieval.retrieved_at,
            archived_location=(
                f"{self.archive_location_prefix.as_posix()}/"
                "_preflight"
            ),
            content_sha256=content_sha256,
            byte_length=len(
                retrieval.content
            ),
            media_type=retrieval.media_type,
        )

        validate_raw_artifact_content(
            preflight,
            retrieval.content,
        )

        retrieved_utc = (
            retrieval.retrieved_at.astimezone(
                UTC
            )
        )

        directory_components = (
            namespace,
            market_series_id,
            retrieved_utc.strftime(
                "%Y"
            ),
            retrieved_utc.strftime(
                "%m"
            ),
            retrieved_utc.strftime(
                "%d"
            ),
        )

        timestamp_component = (
            retrieved_utc.strftime(
                "%Y%m%dT%H%M%S.%fZ"
            )
        )

        final_name = (
            f"{timestamp_component}_"
            f"{storage_token.hex}"
            f"{suffix}"
        )

        staging_name = (
            f".{final_name}."
            f"{uuid4().hex}.tmp"
        )

        directory_fd = (
            _open_archive_directory(
                self.root,
                directory_components,
            )
        )

        try:
            staging_fd = os.open(
                staging_name,
                _file_create_flags(),
                mode=0o640,
                dir_fd=directory_fd,
            )

            try:
                with os.fdopen(
                    staging_fd,
                    "wb",
                    closefd=True,
                ) as handle:
                    handle.write(
                        retrieval.content
                    )
                    handle.flush()
                    os.fsync(
                        handle.fileno()
                    )
            except BaseException:
                with suppress(
                    FileNotFoundError
                ):
                    os.unlink(
                        staging_name,
                        dir_fd=directory_fd,
                    )

                raise

            try:
                # Hard-link publication gives us atomic creation of the final
                # directory entry with no replacement semantics.
                os.link(
                    staging_name,
                    final_name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )

                _fsync_directory_fd(
                    directory_fd
                )
            finally:
                with suppress(
                    FileNotFoundError
                ):
                    os.unlink(
                        staging_name,
                        dir_fd=directory_fd,
                    )

                _fsync_directory_fd(
                    directory_fd
                )
        finally:
            os.close(
                directory_fd
            )

        relative_path = Path(
            *directory_components,
            final_name,
        )

        filesystem_path = (
            self.root
            / relative_path
        )

        archived_location = (
            self.archive_location_prefix
            / PurePosixPath(
                *directory_components,
                final_name,
            )
        ).as_posix()

        artifact = RawRetrievalArtifact(
            market_series_id=market_series_id,
            source=source,
            retrieved_at=retrieval.retrieved_at,
            archived_location=archived_location,
            content_sha256=content_sha256,
            byte_length=len(
                retrieval.content
            ),
            media_type=retrieval.media_type,
        )

        landed_content = (
            filesystem_path.read_bytes()
        )

        validate_raw_artifact_content(
            artifact,
            landed_content,
        )

        return RawArtifactLanding(
            artifact=artifact,
            filesystem_path=filesystem_path,
            storage_token=storage_token,
        )
