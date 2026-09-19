"""ECB Data Portal SDMX CSV transport and Deposit Facility Rate adapter."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from re import fullmatch

import httpx

from european_capital_markets.domain.market_data import (
    PolicyRateDefinitionRecord,
)
from european_capital_markets.domain.taxonomy import (
    MarketSeriesType,
    SourceTier,
    SourceType,
)
from european_capital_markets.ingestion.contracts import (
    NormalizedMarketDatum,
)
from european_capital_markets.ingestion.transport import (
    HttpRetrievedPayload,
)
from european_capital_markets.reference_data.market_series_catalog import (
    MarketSeriesCatalogEntry,
)

ECB_DATA_API_BASE_URL = (
    "https://data-api.ecb.europa.eu/service/data"
)

_ECB_USER_AGENT = (
    "european-capital-markets-platform/"
    "controlled-ingestion"
)

_ECB_TIMEOUT = httpx.Timeout(
    30.0,
    connect=15.0,
)

_DFR_REQUIRED_COLUMNS = frozenset(
    {
        "KEY",
        "FREQ",
        "CURRENCY",
        "PROVIDER_FM_ID",
        "DATA_TYPE_FM",
        "TIME_PERIOD",
        "OBS_VALUE",
        "UNIT",
    }
)

_DFR_EXPECTED_METADATA = {
    "FREQ": "D",
    "CURRENCY": "EUR",
    "PROVIDER_FM_ID": "DFR",
    "DATA_TYPE_FM": "LEV",
    "UNIT": "PCPA",
}


@dataclass(frozen=True, slots=True)
class EcbDfrFetchResult:
    """Transport response plus normalized ECB DFR observations."""

    retrieval: HttpRetrievedPayload
    datums: tuple[NormalizedMarketDatum, ...]


def _split_ecb_provider_series_id(
    provider_series_id: str,
) -> tuple[str, str]:
    if not provider_series_id.strip():
        raise ValueError(
            "ECB provider_series_id must not be blank."
        )

    try:
        dataflow, series_key = (
            provider_series_id.split(
                ".",
                1,
            )
        )
    except ValueError as exc:
        raise ValueError(
            "ECB provider_series_id must contain "
            "a dataflow and SDMX series key."
        ) from exc

    if (
        fullmatch(
            r"[A-Z0-9_]+",
            dataflow,
        )
        is None
    ):
        raise ValueError(
            "ECB dataflow contains unsupported characters."
        )

    if (
        fullmatch(
            r"[A-Z0-9_]+(?:\.[A-Z0-9_]+)+",
            series_key,
        )
        is None
    ):
        raise ValueError(
            "ECB SDMX series key has invalid syntax."
        )

    return dataflow, series_key


def build_ecb_data_url(
    provider_series_id: str,
) -> str:
    """Build the ECB Data Portal SDMX data endpoint for one series."""

    dataflow, series_key = (
        _split_ecb_provider_series_id(
            provider_series_id
        )
    )

    return (
        f"{ECB_DATA_API_BASE_URL}/"
        f"{dataflow}/{series_key}"
    )


def create_ecb_client(
    *,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    """Create the controlled ECB HTTP client.

    TLS certificate verification remains enabled. Retry policy is intentionally
    not implemented in this increment.
    """

    return httpx.Client(
        headers={
            "Accept": "text/csv",
            "User-Agent": _ECB_USER_AGENT,
        },
        timeout=_ECB_TIMEOUT,
        follow_redirects=True,
        verify=True,
        transport=transport,
    )


def fetch_ecb_csv(
    client: httpx.Client,
    provider_series_id: str,
    *,
    last_n_observations: int,
) -> HttpRetrievedPayload:
    """Retrieve a bounded ECB SDMX CSV response."""

    if (
        isinstance(
            last_n_observations,
            bool,
        )
        or not isinstance(
            last_n_observations,
            int,
        )
    ):
        raise TypeError(
            "last_n_observations must be an integer."
        )

    if last_n_observations <= 0:
        raise ValueError(
            "last_n_observations must be positive."
        )

    url = build_ecb_data_url(
        provider_series_id
    )

    params = {
        "format": "csvdata",
        "lastNObservations": str(
            last_n_observations
        ),
    }

    requested_url = str(
        httpx.URL(
            url,
            params=params,
        )
    )

    response = client.get(
        url,
        params=params,
    )

    response.raise_for_status()

    content = response.content

    if not content:
        raise ValueError(
            "ECB response body is empty."
        )

    media_type = (
        response.headers.get(
            "content-type",
            "",
        )
        .partition(";")[0]
        .strip()
        .lower()
    )

    if media_type != "text/csv":
        raise ValueError(
            "ECB response must have text/csv media type."
        )

    prefix = content[:256].lower()

    if (
        b"<html" in prefix
        or b"<!doctype" in prefix
    ):
        raise ValueError(
            "ECB response unexpectedly contains HTML."
        )

    return HttpRetrievedPayload(
        request_url=requested_url,
        response_url=str(
            response.url
        ),
        retrieved_at=datetime.now(UTC),
        status_code=response.status_code,
        content=content,
        media_type=media_type,
        last_modified=response.headers.get(
            "last-modified"
        ),
        etag=response.headers.get(
            "etag"
        ),
        cache_control=response.headers.get(
            "cache-control"
        ),
    )


def _validate_ecb_dfr_catalog_entry(
    catalog_entry: MarketSeriesCatalogEntry,
) -> str:
    market_series = (
        catalog_entry.market_series
    )

    if (
        market_series.series_type
        is not MarketSeriesType.POLICY_RATE
    ):
        raise ValueError(
            "ECB DFR adapter requires a POLICY_RATE series."
        )

    definition = catalog_entry.definition

    if not isinstance(
        definition,
        PolicyRateDefinitionRecord,
    ):
        raise TypeError(
            "ECB DFR adapter requires a "
            "PolicyRateDefinitionRecord."
        )

    if definition.authority != (
        "European Central Bank"
    ):
        raise ValueError(
            "ECB DFR adapter requires ECB authority."
        )

    if definition.currency != "EUR":
        raise ValueError(
            "ECB DFR adapter requires EUR currency."
        )

    if definition.rate_name != (
        "Deposit Facility Rate"
    ):
        raise ValueError(
            "ECB DFR adapter requires the "
            "Deposit Facility Rate definition."
        )

    source_mapping = (
        catalog_entry.source_mapping
    )

    if source_mapping.publisher != (
        "European Central Bank"
    ):
        raise ValueError(
            "ECB DFR adapter requires the ECB "
            "catalog publisher."
        )

    if (
        source_mapping.source_tier
        is not SourceTier.OFFICIAL_INSTITUTION
    ):
        raise ValueError(
            "ECB DFR adapter requires "
            "OFFICIAL_INSTITUTION source tier."
        )

    if (
        source_mapping.source_type
        is not SourceType.CENTRAL_BANK_PUBLICATION
    ):
        raise ValueError(
            "ECB DFR adapter requires "
            "CENTRAL_BANK_PUBLICATION source type."
        )

    provider_series_id = (
        source_mapping.provider_series_id
    )

    if provider_series_id is None:
        raise ValueError(
            "ECB DFR catalog entry requires "
            "provider_series_id."
        )

    _split_ecb_provider_series_id(
        provider_series_id
    )

    return provider_series_id


def parse_ecb_dfr_csv(
    content: bytes,
    *,
    market_series_id: str,
    expected_provider_series_id: str,
) -> tuple[NormalizedMarketDatum, ...]:
    """Normalize ECB Deposit Facility Rate CSV observations."""

    if not isinstance(
        content,
        bytes,
    ):
        raise TypeError(
            "ECB CSV content must be bytes."
        )

    try:
        text = content.decode(
            "utf-8-sig"
        )
    except UnicodeDecodeError as exc:
        raise ValueError(
            "ECB CSV response is not valid UTF-8."
        ) from exc

    reader = csv.DictReader(
        StringIO(
            text,
            newline="",
        )
    )

    if reader.fieldnames is None:
        raise ValueError(
            "ECB CSV response has no header row."
        )

    missing_columns = (
        _DFR_REQUIRED_COLUMNS
        - set(reader.fieldnames)
    )

    if missing_columns:
        raise ValueError(
            "ECB DFR CSV is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    datums: list[
        NormalizedMarketDatum
    ] = []

    seen_dates: set[date] = set()

    for row_number, row in enumerate(
        reader,
        start=2,
    ):
        provider_key = (
            row["KEY"] or ""
        ).strip()

        if provider_key != (
            expected_provider_series_id
        ):
            raise ValueError(
                "ECB DFR CSV KEY does not match "
                "the controlled provider series."
            )

        for (
            column,
            expected_value,
        ) in _DFR_EXPECTED_METADATA.items():
            actual_value = (
                row[column] or ""
            ).strip()

            if actual_value != expected_value:
                raise ValueError(
                    "ECB DFR CSV metadata mismatch "
                    f"for {column}: "
                    f"{actual_value!r}."
                )

        raw_date = (
            row["TIME_PERIOD"] or ""
        ).strip()

        raw_value = (
            row["OBS_VALUE"] or ""
        ).strip()

        if not raw_date:
            raise ValueError(
                "ECB DFR CSV TIME_PERIOD "
                "must not be blank."
            )

        if not raw_value:
            raise ValueError(
                "ECB DFR CSV OBS_VALUE "
                "must not be blank."
            )

        try:
            as_of_date = date.fromisoformat(
                raw_date
            )
        except ValueError as exc:
            raise ValueError(
                "ECB DFR CSV TIME_PERIOD "
                "must be an ISO date."
            ) from exc

        if as_of_date in seen_dates:
            raise ValueError(
                "ECB DFR CSV contains duplicate "
                f"TIME_PERIOD {raw_date}."
            )

        seen_dates.add(
            as_of_date
        )

        try:
            value = Decimal(
                raw_value
            )
        except InvalidOperation as exc:
            raise ValueError(
                "ECB DFR CSV OBS_VALUE "
                "must be decimal."
            ) from exc

        datums.append(
            NormalizedMarketDatum(
                market_series_id=(
                    market_series_id
                ),
                field_name=(
                    "market_series.rate_percent"
                ),
                as_of_date=as_of_date,
                evidence_locator=(
                    f"CSV row {row_number}: "
                    f"KEY={provider_key}, "
                    f"TIME_PERIOD={raw_date}, "
                    "column OBS_VALUE"
                ),
                value=value,
                unit="PERCENT",
                evidence_label=(
                    "ECB Deposit Facility Rate "
                    f"{raw_date}"
                ),
            )
        )

    if not datums:
        raise ValueError(
            "ECB DFR CSV contains no observations."
        )

    return tuple(
        sorted(
            datums,
            key=lambda datum: (
                datum.as_of_date
            ),
        )
    )


def fetch_ecb_dfr(
    client: httpx.Client,
    catalog_entry: MarketSeriesCatalogEntry,
    *,
    last_n_observations: int = 3,
) -> EcbDfrFetchResult:
    """Retrieve and normalize controlled ECB DFR observations."""

    provider_series_id = (
        _validate_ecb_dfr_catalog_entry(
            catalog_entry
        )
    )

    retrieval = fetch_ecb_csv(
        client,
        provider_series_id,
        last_n_observations=(
            last_n_observations
        ),
    )

    datums = parse_ecb_dfr_csv(
        retrieval.content,
        market_series_id=(
            catalog_entry.market_series.market_series_id
        ),
        expected_provider_series_id=(
            provider_series_id
        ),
    )

    return EcbDfrFetchResult(
        retrieval=retrieval,
        datums=datums,
    )
