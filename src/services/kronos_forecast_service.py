# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Local-only Kronos K-line forecasting service."""

from __future__ import annotations

import importlib
import json
import logging
import math
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, Sequence

import numpy as np
import pandas as pd

from src.config_parts.defaults import KRONOS_MODEL_SIZE_DEFAULT, KRONOS_MODEL_SIZES
from src.services.stock_code_utils import canonicalize_analysis_stock_code
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

KRONOS_MIN_LOOKBACK_DAYS = 30
KRONOS_MAX_LOOKBACK_DAYS = 512
KRONOS_MIN_HORIZON_DAYS = 1
KRONOS_MAX_HORIZON_DAYS = 30
KRONOS_DEFAULT_LOOKBACK_DAYS = 120
KRONOS_DEFAULT_HORIZON_DAYS = 5
KRONOS_DEFAULT_PATH_COUNT = 5
KRONOS_FLAT_RETURN_THRESHOLD = 0.001
KRONOS_FORECAST_DISCLAIMER = (
    "Experimental model forecast for research support only. It does not "
    "guarantee future performance and is not investment advice."
)
KRONOS_STOCK_CODE_PATTERN = (
    r"^(?:"
    r"[0-9]{6}|"
    r"(?:[Hh][Kk])?[0-9]{5}|"
    r"[A-Za-z]{1,5}(?:\.(?:[Uu][Ss]|[A-Za-z]))?|"
    r"(?:[Ss][Hh]|[Ss][Zz]|[Bb][Jj])[0-9]{6}|"
    r"[0-9]{6}\.(?:[Ss][Hh]|[Ss][Zz]|[Bb][Jj])|"
    r"[0-9]{1,5}\.[Hh][Kk]"
    r")$"
)
_OPTIONAL_DEPENDENCIES = (
    "torch",
    "einops",
    "huggingface_hub",
    "safetensors",
    "tqdm",
)
_MODEL_FILES = ("config.json", "model.safetensors")
_SAFETENSORS_MAX_HEADER_BYTES = 16 * 1024 * 1024
_SAFETENSORS_DTYPE_BYTES = MappingProxyType(
    {
        "BOOL": 1,
        "U8": 1,
        "I8": 1,
        "F8_E4M3": 1,
        "F8_E5M2": 1,
        "I16": 2,
        "U16": 2,
        "F16": 2,
        "BF16": 2,
        "I32": 4,
        "U32": 4,
        "F32": 4,
        "I64": 8,
        "U64": 8,
        "F64": 8,
    }
)


def _official_model_config(
    *,
    n_layers: int,
    d_model: int,
    n_heads: int,
    ff_dim: int,
    ffn_dropout_p: float,
    attn_dropout_p: float,
    resid_dropout_p: float,
    token_dropout_p: float,
) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "attn_dropout_p": attn_dropout_p,
            "d_model": d_model,
            "ff_dim": ff_dim,
            "ffn_dropout_p": ffn_dropout_p,
            "learn_te": True,
            "n_heads": n_heads,
            "n_layers": n_layers,
            "resid_dropout_p": resid_dropout_p,
            "s1_bits": 10,
            "s2_bits": 10,
            "token_dropout_p": token_dropout_p,
        }
    )


def _official_tokenizer_config(*, group_size: int) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "attn_dropout_p": 0.0,
            "beta": 0.05,
            "d_in": 6,
            "d_model": 256,
            "ff_dim": 512,
            "ffn_dropout_p": 0.0,
            "gamma": 1.1,
            "gamma0": 1.0,
            "group_size": group_size,
            "n_dec_layers": 4,
            "n_enc_layers": 4,
            "n_heads": 4,
            "resid_dropout_p": 0.0,
            "s1_bits": 10,
            "s2_bits": 10,
            "zeta": 0.05,
        }
    )


@dataclass(frozen=True)
class KronosModelSpec:
    """One supported official Kronos model/tokenizer pairing."""

    size: str
    model_repo_id: str
    tokenizer_repo_id: str
    model_directory: str
    tokenizer_directory: str
    context_length: int
    model_config: Mapping[str, Any]
    tokenizer_config: Mapping[str, Any]


KRONOS_MODEL_SPECS = MappingProxyType(
    {
        "mini": KronosModelSpec(
            size="mini",
            model_repo_id="NeoQuasar/Kronos-mini",
            tokenizer_repo_id="NeoQuasar/Kronos-Tokenizer-2k",
            model_directory="Kronos-mini",
            tokenizer_directory="Kronos-Tokenizer-2k",
            context_length=2048,
            model_config=_official_model_config(
                n_layers=4,
                d_model=256,
                n_heads=4,
                ff_dim=512,
                ffn_dropout_p=0.2,
                attn_dropout_p=0.0,
                resid_dropout_p=0.2,
                token_dropout_p=0.0,
            ),
            tokenizer_config=_official_tokenizer_config(group_size=5),
        ),
        "small": KronosModelSpec(
            size="small",
            model_repo_id="NeoQuasar/Kronos-small",
            tokenizer_repo_id="NeoQuasar/Kronos-Tokenizer-base",
            model_directory="Kronos-small",
            tokenizer_directory="Kronos-Tokenizer-base",
            context_length=512,
            model_config=_official_model_config(
                n_layers=8,
                d_model=512,
                n_heads=8,
                ff_dim=1024,
                ffn_dropout_p=0.25,
                attn_dropout_p=0.1,
                resid_dropout_p=0.25,
                token_dropout_p=0.1,
            ),
            tokenizer_config=_official_tokenizer_config(group_size=4),
        ),
        "base": KronosModelSpec(
            size="base",
            model_repo_id="NeoQuasar/Kronos-base",
            tokenizer_repo_id="NeoQuasar/Kronos-Tokenizer-base",
            model_directory="Kronos-base",
            tokenizer_directory="Kronos-Tokenizer-base",
            context_length=512,
            model_config=_official_model_config(
                n_layers=12,
                d_model=832,
                n_heads=16,
                ff_dim=2048,
                ffn_dropout_p=0.2,
                attn_dropout_p=0.0,
                resid_dropout_p=0.2,
                token_dropout_p=0.0,
            ),
            tokenizer_config=_official_tokenizer_config(group_size=4),
        ),
    }
)


@dataclass(frozen=True)
class KronosAvailability:
    """Registration readiness resolved without network access."""

    ready: bool
    reason: str
    message: str
    spec: KronosModelSpec | None = None
    model_dir: Path | None = None
    tokenizer_dir: Path | None = None


class KronosForecastError(RuntimeError):
    """Base typed failure returned by the optional forecasting tool."""

    code = "kronos_forecast_failed"
    retriable = False


class KronosInputError(KronosForecastError, ValueError):
    code = "invalid_request"


class KronosDataError(KronosForecastError):
    code = "history_unavailable"
    retriable = True


class KronosInferenceError(KronosForecastError):
    code = "inference_failed"


class KronosInferenceBackend(Protocol):
    """Narrow seam around the official stochastic predictor."""

    def predict_paths(
        self,
        history_frame: pd.DataFrame,
        history_timestamps: pd.Series,
        future_timestamps: pd.Series,
        *,
        path_count: int,
    ) -> Sequence[pd.DataFrame]:
        """Return independent forecast paths in future timestamp order."""


def _dependency_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except Exception:  # broad-exception: fallback_recorded - Any optional dependency import failure closes readiness and is reported by module name.
        logger.debug("Kronos optional dependency import failed module=%s", module_name)
        return False
    return True


def _artifact_file_ready(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _config_matches(
    path: Path,
    expected: Mapping[str, Any],
) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or set(payload) != set(expected):
        return False
    return all(
        type(payload[key]) is type(expected_value)
        and payload[key] == expected_value
        for key, expected_value in expected.items()
    )


def _safetensors_file_valid(path: Path) -> bool:
    try:
        file_size = path.stat().st_size
        with path.open("rb") as stream:
            raw_header_size = stream.read(8)
            if len(raw_header_size) != 8:
                return False
            header_size = int.from_bytes(raw_header_size, "little", signed=False)
            if (
                header_size <= 0
                or header_size % 8 != 0
                or header_size > _SAFETENSORS_MAX_HEADER_BYTES
                or header_size > file_size - 8
            ):
                return False
            raw_header = stream.read(header_size)
    except OSError:
        return False

    try:
        header = json.loads(raw_header.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(header, dict):
        return False

    data_size = file_size - 8 - header_size
    ranges: list[tuple[int, int]] = []
    tensor_count = 0
    for name, tensor in header.items():
        if name == "__metadata__":
            if not isinstance(tensor, dict):
                return False
            continue
        if type(name) is not str or not name or not isinstance(tensor, dict):
            return False
        dtype = tensor.get("dtype")
        shape = tensor.get("shape")
        offsets = tensor.get("data_offsets")
        if (
            type(dtype) is not str
            or dtype not in _SAFETENSORS_DTYPE_BYTES
            or type(shape) is not list
            or any(type(dimension) is not int or dimension < 0 for dimension in shape)
            or type(offsets) is not list
            or len(offsets) != 2
            or any(type(offset) is not int or offset < 0 for offset in offsets)
        ):
            return False
        start, end = offsets
        expected_bytes = math.prod(shape) * _SAFETENSORS_DTYPE_BYTES[dtype]
        if start > end or end > data_size or end - start != expected_bytes:
            return False
        ranges.append((start, end))
        tensor_count += 1

    cursor = 0
    for start, end in sorted(ranges):
        if start != cursor:
            return False
        cursor = end
    return tensor_count > 0 and cursor == data_size


def assess_kronos_availability(
    config: Any,
    *,
    dependency_probe: Callable[[str], bool] = _dependency_available,
) -> KronosAvailability:
    """Check the three registration gates without network access."""

    if getattr(config, "kronos_enabled", False) is not True:
        return KronosAvailability(
            ready=False,
            reason="disabled",
            message=(
                "Kronos agent tool is disabled. Set KRONOS_ENABLED=true only "
                "after installing requirements-kronos.txt and placing local weights."
            ),
        )

    size = str(
        getattr(config, "kronos_model_size", KRONOS_MODEL_SIZE_DEFAULT) or ""
    ).strip().lower()
    spec = KRONOS_MODEL_SPECS.get(size)
    if spec is None or size not in KRONOS_MODEL_SIZES:
        return KronosAvailability(
            ready=False,
            reason="model_size_invalid",
            message=(
                "Kronos model size is invalid. Set KRONOS_MODEL_SIZE to "
                f"one of: {', '.join(sorted(KRONOS_MODEL_SIZES))}."
            ),
        )

    missing_dependencies = []
    for module_name in _OPTIONAL_DEPENDENCIES:
        try:
            available = dependency_probe(module_name)
        except Exception:  # broad-exception: fallback_recorded - Probe failures close the optional registration gate and are reported by module name.
            logger.debug("Kronos dependency readiness probe failed module=%s", module_name)
            available = False
        if not available:
            missing_dependencies.append(module_name)
    if missing_dependencies:
        return KronosAvailability(
            ready=False,
            reason="dependencies_missing",
            message=(
                "Kronos dependencies are missing: "
                f"{', '.join(missing_dependencies)}. Install requirements-kronos.txt."
            ),
            spec=spec,
        )

    raw_weights_dir = str(getattr(config, "kronos_weights_dir", "") or "").strip()
    if not raw_weights_dir:
        return KronosAvailability(
            ready=False,
            reason="weights_dir_unconfigured",
            message=(
                "Kronos weights are not configured. Set KRONOS_WEIGHTS_DIR to "
                "a local directory containing the selected model and tokenizer."
            ),
            spec=spec,
        )
    if "\x00" in raw_weights_dir or "://" in raw_weights_dir:
        return KronosAvailability(
            ready=False,
            reason="weights_dir_invalid",
            message="KRONOS_WEIGHTS_DIR must be a local filesystem directory.",
            spec=spec,
        )

    root = Path(raw_weights_dir).expanduser()
    model_dir = root / spec.model_directory
    tokenizer_dir = root / spec.tokenizer_directory
    if not root.is_dir():
        return KronosAvailability(
            ready=False,
            reason="weights_dir_missing",
            message=(
                "The configured Kronos weights directory does not exist. "
                "Download the official Hugging Face artifacts elsewhere or "
                "place them manually, then restart StockPulse."
            ),
            spec=spec,
            model_dir=model_dir,
            tokenizer_dir=tokenizer_dir,
        )

    missing_artifacts = [
        f"{directory.name}/{file_name}"
        for directory in (model_dir, tokenizer_dir)
        for file_name in _MODEL_FILES
        if not _artifact_file_ready(directory / file_name)
    ]
    if missing_artifacts:
        return KronosAvailability(
            ready=False,
            reason="weights_incomplete",
            message=(
                "Kronos local weights are incomplete. Missing: "
                f"{', '.join(missing_artifacts)}. No automatic download was attempted."
            ),
            spec=spec,
            model_dir=model_dir,
            tokenizer_dir=tokenizer_dir,
        )

    invalid_artifacts = []
    for directory, expected_config in (
        (model_dir, spec.model_config),
        (tokenizer_dir, spec.tokenizer_config),
    ):
        if not _config_matches(directory / "config.json", expected_config):
            invalid_artifacts.append(f"{directory.name}/config.json")
        if not _safetensors_file_valid(directory / "model.safetensors"):
            invalid_artifacts.append(f"{directory.name}/model.safetensors")
    if invalid_artifacts:
        return KronosAvailability(
            ready=False,
            reason="weights_invalid",
            message=(
                "Kronos local artifacts do not match the selected official "
                f"model/tokenizer contract: {', '.join(invalid_artifacts)}. "
                "No automatic download was attempted."
            ),
            spec=spec,
            model_dir=model_dir,
            tokenizer_dir=tokenizer_dir,
        )

    return KronosAvailability(
        ready=True,
        reason="ready",
        message="Kronos local model and tokenizer are ready.",
        spec=spec,
        model_dir=model_dir,
        tokenizer_dir=tokenizer_dir,
    )


class OfficialKronosInferenceBackend:
    """Lazy adapter over the pinned official Kronos inference implementation."""

    def __init__(
        self,
        *,
        spec: KronosModelSpec,
        model_dir: Path,
        tokenizer_dir: Path,
    ) -> None:
        self._spec = spec
        self._model_dir = model_dir
        self._tokenizer_dir = tokenizer_dir
        self._predictor = None
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()

    def _get_predictor(self):
        if self._predictor is not None:
            return self._predictor
        with self._load_lock:
            if self._predictor is not None:
                return self._predictor
            from src.services._kronos_vendor import (
                Kronos,
                KronosPredictor,
                KronosTokenizer,
            )

            tokenizer = KronosTokenizer.from_pretrained(
                str(self._tokenizer_dir),
                local_files_only=True,
                strict=True,
            )
            model = Kronos.from_pretrained(
                str(self._model_dir),
                local_files_only=True,
                strict=True,
            )
            tokenizer.eval()
            model.eval()
            self._predictor = KronosPredictor(
                model,
                tokenizer,
                max_context=min(
                    self._spec.context_length,
                    KRONOS_MAX_LOOKBACK_DAYS,
                ),
            )
        return self._predictor

    def prepare(self) -> None:
        """Load and validate the configured local model/tokenizer pair once."""

        self._get_predictor()

    def predict_paths(
        self,
        history_frame: pd.DataFrame,
        history_timestamps: pd.Series,
        future_timestamps: pd.Series,
        *,
        path_count: int,
    ) -> Sequence[pd.DataFrame]:
        predictor = self._get_predictor()
        paths = []
        with self._inference_lock:
            for _ in range(path_count):
                paths.append(
                    predictor.predict(
                        df=history_frame,
                        x_timestamp=history_timestamps,
                        y_timestamp=future_timestamps,
                        pred_len=len(future_timestamps),
                        T=1.0,
                        top_p=0.9,
                        sample_count=1,
                        verbose=False,
                    )
                )
        return paths


class KronosForecastService:
    """Validate OHLCV input and aggregate stochastic Kronos forecast paths."""

    def __init__(
        self,
        *,
        spec: KronosModelSpec,
        backend: KronosInferenceBackend,
        history_loader: Callable[..., tuple[pd.DataFrame | None, str]] | None = None,
        path_count: int = KRONOS_DEFAULT_PATH_COUNT,
    ) -> None:
        if path_count < 2:
            raise ValueError("Kronos path_count must be at least 2")
        self._spec = spec
        self._backend = backend
        self._history_loader = history_loader
        self._path_count = path_count

    def forecast(
        self,
        *,
        stock_code: str,
        lookback_days: int = KRONOS_DEFAULT_LOOKBACK_DAYS,
        horizon_days: int = KRONOS_DEFAULT_HORIZON_DAYS,
    ) -> dict[str, Any]:
        canonical_code = validate_kronos_request(
            stock_code=stock_code,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
        )
        history_loader = self._history_loader
        if history_loader is None:
            from src.services.history_loader import load_history_df

            history_loader = load_history_df

        history, source = history_loader(canonical_code, days=lookback_days)
        prepared, history_timestamps = _prepare_history(
            history,
            lookback_days=lookback_days,
        )
        last_timestamp = history_timestamps.iloc[-1]
        future_timestamps = pd.Series(
            pd.bdate_range(
                start=last_timestamp + pd.offsets.BDay(1),
                periods=horizon_days,
            )
        )

        try:
            paths = self._backend.predict_paths(
                prepared,
                history_timestamps,
                future_timestamps,
                path_count=self._path_count,
            )
        except KronosForecastError:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - Optional local inference failures become a typed tool result.
            log_safe_exception(
                logger,
                "Kronos local inference failed",
                exc,
                error_code="kronos_local_inference_failed",
            )
            raise KronosInferenceError(
                "Kronos could not produce a forecast from the configured local weights."
            ) from None

        return _aggregate_paths(
            canonical_code=canonical_code,
            source=source,
            history=prepared,
            history_timestamps=history_timestamps,
            future_timestamps=future_timestamps,
            paths=paths,
            spec=self._spec,
        )


def validate_kronos_request(
    *,
    stock_code: object,
    lookback_days: object,
    horizon_days: object,
) -> str:
    """Validate the handler boundary even when a native runtime skips schema checks."""

    if (
        type(stock_code) is not str
        or re.fullmatch(KRONOS_STOCK_CODE_PATTERN, stock_code.strip()) is None
    ):
        raise KronosInputError("stock_code has an unsupported format")
    if (
        isinstance(lookback_days, bool)
        or type(lookback_days) is not int
        or not KRONOS_MIN_LOOKBACK_DAYS
        <= lookback_days
        <= KRONOS_MAX_LOOKBACK_DAYS
    ):
        raise KronosInputError(
            "lookback_days must be an integer between "
            f"{KRONOS_MIN_LOOKBACK_DAYS} and {KRONOS_MAX_LOOKBACK_DAYS}"
        )
    if (
        isinstance(horizon_days, bool)
        or type(horizon_days) is not int
        or not KRONOS_MIN_HORIZON_DAYS
        <= horizon_days
        <= KRONOS_MAX_HORIZON_DAYS
    ):
        raise KronosInputError(
            "horizon_days must be an integer between "
            f"{KRONOS_MIN_HORIZON_DAYS} and {KRONOS_MAX_HORIZON_DAYS}"
        )
    canonical_code = canonicalize_analysis_stock_code(stock_code)
    if not canonical_code:
        raise KronosInputError("stock_code could not be normalized")
    return canonical_code


def _prepare_history(
    history: pd.DataFrame | None,
    *,
    lookback_days: int,
) -> tuple[pd.DataFrame, pd.Series]:
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        raise KronosDataError("Historical OHLCV data is unavailable.")
    required = ("date", "open", "high", "low", "close")
    missing = [column for column in required if column not in history.columns]
    if missing:
        raise KronosDataError(
            f"Historical data is missing required columns: {', '.join(missing)}."
        )

    frame = history.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    numeric_columns = ["open", "high", "low", "close"]
    for optional in ("volume", "amount"):
        if optional in frame.columns:
            numeric_columns.append(optional)
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = (
        frame.dropna(subset=["date", "open", "high", "low", "close"])
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
    )
    finite_mask = np.isfinite(frame[["open", "high", "low", "close"]]).all(axis=1)
    valid_prices = (
        (frame[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (frame["high"] >= frame[["open", "close", "low"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close", "high"]].min(axis=1))
    )
    frame = frame.loc[finite_mask & valid_prices]
    if len(frame) < lookback_days:
        raise KronosDataError(
            "Historical OHLCV data has fewer valid records than lookback_days."
        )

    frame = frame.tail(lookback_days).reset_index(drop=True)
    if "volume" not in frame.columns:
        frame["volume"] = 0.0
    else:
        frame["volume"] = (
            pd.to_numeric(frame["volume"], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .clip(lower=0.0)
        )
    if "amount" not in frame.columns:
        frame["amount"] = frame["volume"] * frame[
            ["open", "high", "low", "close"]
        ].mean(axis=1)
    else:
        frame["amount"] = (
            pd.to_numeric(frame["amount"], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .clip(lower=0.0)
        )

    timestamps = pd.Series(frame.pop("date"), dtype="datetime64[ns]")
    return (
        frame[["open", "high", "low", "close", "volume", "amount"]],
        timestamps,
    )


def _validated_path(path: object, *, horizon_days: int) -> pd.DataFrame:
    if not isinstance(path, pd.DataFrame) or len(path) != horizon_days:
        raise KronosInferenceError("Kronos returned an invalid forecast path length.")
    required = ["open", "high", "low", "close"]
    if any(column not in path.columns for column in required):
        raise KronosInferenceError("Kronos returned an incomplete OHLC forecast path.")
    frame = path[required].apply(pd.to_numeric, errors="coerce")
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise KronosInferenceError("Kronos returned non-finite or non-positive prices.")
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
        raise KronosInferenceError("Kronos returned inconsistent high prices.")
    if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
        raise KronosInferenceError("Kronos returned inconsistent low prices.")
    return frame.reset_index(drop=True)


def _round(value: float) -> float:
    return round(float(value), 6)


def _interval(values: np.ndarray) -> dict[str, float]:
    if values.size == 0 or not np.isfinite(values).all():
        raise KronosInferenceError("Kronos produced a non-finite forecast metric.")
    lower, median, upper = np.quantile(values, [0.1, 0.5, 0.9])
    return {
        "p10": _round(lower),
        "p50": _round(median),
        "p90": _round(upper),
    }


def _path_volatility(last_close: float, closes: np.ndarray) -> float:
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        log_returns = np.diff(np.log(np.concatenate(([last_close], closes))))
    if len(log_returns) == 1:
        daily_volatility = abs(float(log_returns[0]))
    else:
        daily_volatility = float(np.std(log_returns, ddof=1))
    annualized = daily_volatility * math.sqrt(252.0) * 100.0
    if not math.isfinite(annualized):
        raise KronosInferenceError("Kronos produced non-finite forecast volatility.")
    return annualized


def _aggregate_paths(
    *,
    canonical_code: str,
    source: str,
    history: pd.DataFrame,
    history_timestamps: pd.Series,
    future_timestamps: pd.Series,
    paths: Sequence[pd.DataFrame],
    spec: KronosModelSpec,
) -> dict[str, Any]:
    if len(paths) < 2:
        raise KronosInferenceError(
            "Kronos must return at least two paths for probabilistic output."
        )
    validated = [
        _validated_path(path, horizon_days=len(future_timestamps))
        for path in paths
    ]
    arrays = np.stack(
        [path[["open", "high", "low", "close"]].to_numpy(dtype=float) for path in validated],
        axis=0,
    )
    last_close = float(history["close"].iloc[-1])
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        final_returns = arrays[:, -1, 3] / last_close - 1.0
    if not np.isfinite(final_returns).all():
        raise KronosInferenceError("Kronos produced non-finite forecast returns.")
    direction_counts = {
        "up": int(np.count_nonzero(final_returns > KRONOS_FLAT_RETURN_THRESHOLD)),
        "flat": int(
            np.count_nonzero(
                np.abs(final_returns) <= KRONOS_FLAT_RETURN_THRESHOLD
            )
        ),
        "down": int(np.count_nonzero(final_returns < -KRONOS_FLAT_RETURN_THRESHOLD)),
    }
    path_count = len(final_returns)
    direction_probabilities = {
        direction: _round(count / path_count)
        for direction, count in direction_counts.items()
    }
    dominant_count = max(direction_counts.values())
    dominant_candidates = [
        direction
        for direction, count in direction_counts.items()
        if count == dominant_count
    ]
    dominant_direction = (
        dominant_candidates[0]
        if len(dominant_candidates) == 1
        else "ambiguous"
    )

    volatility_values = np.array(
        [_path_volatility(last_close, path[:, 3]) for path in arrays],
        dtype=float,
    )
    daily_bands = []
    for index, timestamp in enumerate(future_timestamps):
        band: dict[str, Any] = {
            "date": pd.Timestamp(timestamp).date().isoformat(),
        }
        for column_index, column in enumerate(("open", "high", "low", "close")):
            band[column] = _interval(arrays[:, index, column_index])
        daily_bands.append(band)

    return {
        "schema_version": "kronos-forecast-v1",
        "status": "ok",
        "stock_code": canonical_code,
        "as_of": pd.Timestamp(history_timestamps.iloc[-1]).date().isoformat(),
        "data_source": source,
        "lookback_days": len(history),
        "horizon_days": len(future_timestamps),
        "model": {
            "family": "Kronos",
            "size": spec.size,
            "model_repo_id": spec.model_repo_id,
            "tokenizer_repo_id": spec.tokenizer_repo_id,
        },
        "sampling": {
            "path_count": len(validated),
            "temperature": 1.0,
            "top_p": 0.9,
            "flat_return_threshold_pct": _round(
                KRONOS_FLAT_RETURN_THRESHOLD * 100.0
            ),
        },
        "direction": {
            "dominant": dominant_direction,
            "probabilities": direction_probabilities,
        },
        "horizon_return_pct": _interval(final_returns * 100.0),
        "annualized_volatility_pct": _interval(volatility_values),
        "daily_ohlc_intervals": daily_bands,
        "disclaimer": KRONOS_FORECAST_DISCLAIMER,
        "limitations": [
            "Forecast probabilities are sampled model outputs, not calibrated guarantees.",
            "Business-day timestamps do not model exchange-specific holidays.",
            "Regime shifts can invalidate patterns learned from historical data.",
        ],
    }
