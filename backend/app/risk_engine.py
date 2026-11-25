"""Explainable Weighted Heat-Risk Calculation Engine.

Formula (initial model assumptions requiring empirical validation):
    Risk Score = (wE * E) + (wV * V) + (wC * C)
Default weights:
    wE = 0.40 (Environmental Heat Exposure, 0-100)
    wV = 0.35 (Social Vulnerability, 0-100)
    wC = 0.25 (Cooling-Access Deficit, 0-100)

Important safeguards:
1. Sub-indicators are normalized to 0-100 before aggregation.
2. Missing values (None) are NEVER treated as zero; weights are re-normalized
   over available indicators, and missing fields are explicitly surfaced.
3. Data confidence decreases proportionally when fields are missing or synthetic.
"""

from typing import Any, Dict, List, Optional, Tuple


DEFAULT_WEIGHTS = {
    "exposure": 0.40,
    "vulnerability": 0.35,
    "cooling_deficit": 0.25,
}

MODEL_ASSUMPTION_NOTE = (
    "Initial weighted linear model (0.40×Exposure + 0.35×Vulnerability + 0.25×Cooling Deficit) "
    "with min-max domain normalization. These weights are initial model assumptions requiring "
    "empirical epidemiological calibration against local heat-health outcomes."
)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _normalize_minmax(value: Optional[float], min_val: float, max_val: float, invert: bool = False) -> Optional[float]:
    if value is None:
        return None
    if max_val == min_val:
        return 50.0
    ratio = (value - min_val) / (max_val - min_val)
    score = _clamp(ratio * 100.0)
    return round(100.0 - score if invert else score, 2)


def _weighted_available_mean(items: List[Tuple[str, Optional[float], float]], missing_fields: List[str]) -> Tuple[Optional[float], Dict[str, Any]]:
    """Compute weighted mean over non-None indicators without treating missing values as zero."""
    available = []
    sub_breakdown: Dict[str, Any] = {}
    for field_name, score, weight in items:
        if score is None:
            missing_fields.append(field_name)
            sub_breakdown[field_name] = {"normalized_score": None, "status": "missing"}
        else:
            available.append((field_name, score, weight))
            sub_breakdown[field_name] = {"normalized_score": round(score, 1), "base_weight": weight, "status": "available"}

    if not available:
        return None, sub_breakdown

    total_w = sum(w for _, _, w in available)
    mean_val = sum(score * (w / total_w) for _, score, w in available)
    return round(mean_val, 2), sub_breakdown


def classify_risk(score: float) -> str:
    if score <= 25.0:
        return "Low Risk"
    if score <= 50.0:
        return "Moderate Risk"
    if score <= 75.0:
        return "High Risk"
    return "Very High Risk"


def compute_heat_risk(
    indicators: Dict[str, Optional[float]],
    weights: Optional[Dict[str, float]] = None,
    data_nature: str = "Synthetic",
) -> Dict[str, Any]:
    """Compute explainable E, V, C scores, overall risk, contributions, and data confidence."""
    raw_weights = dict(DEFAULT_WEIGHTS)
    if weights:
        for key in ("exposure", "vulnerability", "cooling_deficit"):
            if key in weights and weights[key] is not None and weights[key] >= 0:
                raw_weights[key] = float(weights[key])

    weight_sum = raw_weights["exposure"] + raw_weights["vulnerability"] + raw_weights["cooling_deficit"]
    if weight_sum <= 0:
        raw_weights = dict(DEFAULT_WEIGHTS)
        weight_sum = 1.0

    norm_weights = {k: v / weight_sum for k, v in raw_weights.items()}
    missing_fields: List[str] = []

    # 1. Environmental Heat Exposure (E, 0-100)
    lst_norm = _normalize_minmax(indicators.get("land_surface_temp_c"), 32.0, 54.0)
    air_norm = _normalize_minmax(indicators.get("air_temp_c"), 28.0, 46.0)
    veg_deficit_norm = _normalize_minmax(indicators.get("ndvi_vegetation_pct"), 0.0, 50.0, invert=True)
    built_up_norm = _normalize_minmax(indicators.get("built_up_intensity_pct"), 20.0, 98.0)
    albedo_deficit_norm = _normalize_minmax(indicators.get("albedo_index"), 0.12, 0.36, invert=True)

    exposure_score, exposure_subs = _weighted_available_mean(
        [
            ("land_surface_temp_c", lst_norm, 0.35),
            ("air_temp_c", air_norm, 0.20),
            ("ndvi_vegetation_pct", veg_deficit_norm, 0.20),
            ("built_up_intensity_pct", built_up_norm, 0.15),
            ("albedo_index", albedo_deficit_norm, 0.10),
        ],
        missing_fields,
    )

    # 2. Social Vulnerability (V, 0-100)
    elderly_norm = _normalize_minmax(indicators.get("elderly_pct"), 5.0, 20.0)
    housing_norm = _normalize_minmax(indicators.get("low_income_housing_pct"), 5.0, 75.0)
    worker_norm = _normalize_minmax(indicators.get("outdoor_worker_pct"), 10.0, 80.0)

    vulnerability_score, vulnerability_subs = _weighted_available_mean(
        [
            ("elderly_pct", elderly_norm, 0.30),
            ("low_income_housing_pct", housing_norm, 0.40),
            ("outdoor_worker_pct", worker_norm, 0.30),
        ],
        missing_fields,
    )

    # 3. Cooling-Access Deficit (C, 0-100)
    facility_deficit_norm = _normalize_minmax(indicators.get("cooling_facility_coverage_pct"), 0.0, 95.0, invert=True)
    healthcare_dist_norm = _normalize_minmax(indicators.get("healthcare_distance_km"), 0.4, 4.5)

    cooling_deficit_score, cooling_subs = _weighted_available_mean(
        [
            ("cooling_facility_coverage_pct", facility_deficit_norm, 0.65),
            ("healthcare_distance_km", healthcare_dist_norm, 0.35),
        ],
        missing_fields,
    )

    # Combine E, V, C without treating missing dimensions as zero
    dimension_pairs = [
        ("exposure", exposure_score, norm_weights["exposure"]),
        ("vulnerability", vulnerability_score, norm_weights["vulnerability"]),
        ("cooling_deficit", cooling_deficit_score, norm_weights["cooling_deficit"]),
    ]
    available_dims = [(k, val, w) for k, val, w in dimension_pairs if val is not None]

    if not available_dims:
        overall_score = 0.0
        effective_weights = {"exposure": 0.0, "vulnerability": 0.0, "cooling_deficit": 0.0}
    else:
        avail_w_sum = sum(w for _, _, w in available_dims)
        effective_weights = {
            k: round((w / avail_w_sum) if val is not None else 0.0, 4)
            for k, val, w in dimension_pairs
        }
        overall_score = round(sum(val * effective_weights[k] for k, val, _ in available_dims), 1)

    total_fields = 10
    present_fields = total_fields - len(missing_fields)
    completeness_pct = (present_fields / total_fields) * 100.0

    # Reflect synthetic/estimated provenance cleanly in confidence score
    provenance_cap = 92.0 if data_nature in ("Synthetic", "Estimated") else 98.0
    confidence_pct = round(min(completeness_pct, provenance_cap), 1)
    if confidence_pct >= 85.0 and len(missing_fields) == 0:
        confidence_label = "High"
    elif confidence_pct >= 65.0:
        confidence_label = "Medium"
    else:
        confidence_label = "Low"

    e_contrib = round((exposure_score or 0.0) * effective_weights["exposure"], 1) if exposure_score is not None else None
    v_contrib = round((vulnerability_score or 0.0) * effective_weights["vulnerability"], 1) if vulnerability_score is not None else None
    c_contrib = round((cooling_deficit_score or 0.0) * effective_weights["cooling_deficit"], 1) if cooling_deficit_score is not None else None

    contributions = {
        "exposure": {
            "score": exposure_score,
            "configured_weight": round(norm_weights["exposure"], 3),
            "effective_weight": effective_weights["exposure"],
            "points_contributed": e_contrib,
            "sub_indicators": exposure_subs,
        },
        "vulnerability": {
            "score": vulnerability_score,
            "configured_weight": round(norm_weights["vulnerability"], 3),
            "effective_weight": effective_weights["vulnerability"],
            "points_contributed": v_contrib,
            "sub_indicators": vulnerability_subs,
        },
        "cooling_deficit": {
            "score": cooling_deficit_score,
            "configured_weight": round(norm_weights["cooling_deficit"], 3),
            "effective_weight": effective_weights["cooling_deficit"],
            "points_contributed": c_contrib,
            "sub_indicators": cooling_subs,
        },
        "missing_fields": missing_fields,
        "missing_data_policy": "Missing indicators are excluded and remaining weights re-normalized; missing values are never substituted with zero.",
    }

    return {
        "exposure_score": exposure_score,
        "vulnerability_score": vulnerability_score,
        "cooling_deficit_score": cooling_deficit_score,
        "weight_exposure": round(norm_weights["exposure"], 3),
        "weight_vulnerability": round(norm_weights["vulnerability"], 3),
        "weight_cooling_deficit": round(norm_weights["cooling_deficit"], 3),
        "overall_risk_score": overall_score,
        "risk_category": classify_risk(overall_score),
        "data_confidence_pct": confidence_pct,
        "data_confidence_label": confidence_label,
        "missing_fields": missing_fields,
        "contributions": contributions,
        "model_note": MODEL_ASSUMPTION_NOTE,
    }
