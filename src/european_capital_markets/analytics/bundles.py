"""Lossless rate-change bundles and explicit, offline replay verification.

No archive, deployment attestation, version migration, or release approval.
"""

import hashlib
import hmac
import json
import platform
import re
from dataclasses import dataclass

from european_capital_markets.analytics.market_selection import (
    EXACT_DATE_POLICY_VERSION,
)
from european_capital_markets.analytics.rate_changes import (
    RATE_CHANGE_DECIMAL_POLICY_REF,
    RATE_CHANGE_METHODOLOGY_VERSION,
    RateChangeRequest,
    RateChangeResult,
    calculate_rate_change,
)
from european_capital_markets.domain.dataset import CanonicalDataset

BUNDLE_FORMAT_VERSION = "rate-change-bundle-v1"
RECORD_SCHEMA_VERSION = "canonical-records-v1"


class BundleError(ValueError):
    """Malformed, incompatible, or inconsistent retained content."""


class ReplayUnavailableError(BundleError):
    """The declared execution identity/artifacts are unavailable or incompatible."""


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    source_commit: str
    source_artifact_sha256: str
    lock_sha256: str
    python_implementation: str
    python_version: str
    source_tree_clean: bool
    selection_policy: str = EXACT_DATE_POLICY_VERSION
    methodology: str = RATE_CHANGE_METHODOLOGY_VERSION
    decimal_policy: str = RATE_CHANGE_DECIMAL_POLICY_REF

    def __post_init__(self) -> None:
        for value, size in (
            (self.source_commit, 40),
            (self.source_artifact_sha256, 64),
            (self.lock_sha256, 64),
        ):
            if (
                type(value) is not str
                or re.fullmatch(f"[0-9a-f]{{{size}}}", value) is None
            ):
                raise BundleError("Execution digests must be full lowercase hex.")
        if self.source_tree_clean is not True:
            raise ReplayUnavailableError("A clean source tree is required.")
        if (self.python_implementation, self.python_version) != (
            platform.python_implementation(),
            platform.python_version(),
        ):
            raise ReplayUnavailableError("Unsupported Python runtime identity.")
        if (self.selection_policy, self.methodology, self.decimal_policy) != (
            EXACT_DATE_POLICY_VERSION,
            RATE_CHANGE_METHODOLOGY_VERSION,
            RATE_CHANGE_DECIMAL_POLICY_REF,
        ):
            raise ReplayUnavailableError("Unsupported analytical execution policy.")


@dataclass(frozen=True, slots=True)
class RateChangeBundle:
    dataset: CanonicalDataset
    request: RateChangeRequest
    result: RateChangeResult
    execution: ExecutionIdentity
    format_version: str = BUNDLE_FORMAT_VERSION
    record_schema_version: str = RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (self.format_version, self.record_schema_version) != (
            BUNDLE_FORMAT_VERSION,
            RECORD_SCHEMA_VERSION,
        ):
            raise BundleError("Unsupported bundle format or record schema.")


def create_rate_change_bundle(
    dataset: CanonicalDataset,
    request: RateChangeRequest,
    execution: ExecutionIdentity,
) -> RateChangeBundle:
    """Compute over exactly the supplied dataset; retain every record."""
    result = calculate_rate_change(dataset, request)
    bundle = RateChangeBundle(dataset, request, result, execution)
    # The codec checks every annotated field, even those domain constructors
    # leave to annotations, and rejects unsupported runtime scalar types.
    encode_bundle(bundle)
    return bundle


def encode_bundle(bundle: RateChangeBundle) -> bytes:
    """Encode valid typed content; only verify_bundle proves result consistency."""
    from european_capital_markets.analytics._bundle_codec import encode

    if type(bundle) is not RateChangeBundle:
        raise BundleError("Expected a RateChangeBundle.")
    return encode(bundle)


def decode_bundle(content: bytes, *, expected_sha256: str) -> RateChangeBundle:
    """Verify bytes and reconstruct/validate; does not certify replay consistency."""
    from european_capital_markets.analytics._bundle_codec import MAX_BYTES, decode
    from european_capital_markets.domain.dataset import validate_canonical_dataset

    if type(content) is not bytes:
        raise BundleError("Bundle content must be bytes.")
    if len(content) > MAX_BYTES:
        raise BundleError("Bundle byte limit exceeded.")
    if (
        type(expected_sha256) is not str
        or re.fullmatch("[0-9a-f]{64}", expected_sha256) is None
    ):
        raise BundleError("Expected a lowercase SHA-256 digest.")
    if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected_sha256):
        raise BundleError("Bundle digest mismatch.")
    bundle = decode(content)
    if type(bundle) is not RateChangeBundle:
        raise BundleError("Expected a bundle envelope.")
    try:
        validate_canonical_dataset(bundle.dataset)
    except (ValueError, TypeError) as exc:
        raise BundleError("Invalid retained canonical dataset.") from exc
    return bundle


def verify_bundle(
    content: bytes,
    *,
    expected_sha256: str,
    execution: ExecutionIdentity,
    source_artifact: bytes,
    lock_artifact: bytes,
) -> RateChangeBundle:
    """Replay only after matching caller-attested execution and retained artifacts.

    The caller owns deployment attestation and artifact-to-commit binding. This
    function hashes supplied bytes; it cannot prove what code is running.
    """
    bundle = decode_bundle(content, expected_sha256=expected_sha256)
    if type(execution) is not ExecutionIdentity or execution != bundle.execution:
        raise ReplayUnavailableError("Execution identity does not match the bundle.")
    for artifact, digest in (
        (source_artifact, execution.source_artifact_sha256),
        (lock_artifact, execution.lock_sha256),
    ):
        if (
            type(artifact) is not bytes
            or hashlib.sha256(artifact).hexdigest() != digest
        ):
            raise ReplayUnavailableError(
                "Required retained execution artifact mismatch."
            )
    actual = calculate_rate_change(bundle.dataset, bundle.request)
    from european_capital_markets.analytics._bundle_codec import encode

    if encode(actual) != encode(bundle.result):
        raise BundleError("Complete result replay mismatch.")
    return bundle


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
