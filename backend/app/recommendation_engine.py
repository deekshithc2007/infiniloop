"""Rule-based & Explainable AI Cooling Recommendation Engine.

Generates location-specific, practical cooling recommendations across 6 core
intervention categories without fabricating measurements or falsely claiming
completion of interventions.
"""

from typing import Any, Dict, List, Optional


def _priority_rank(level: str) -> int:
    return {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}.get(level, 4)


def generate_recommendations_for_neighbourhood(
    neighbourhood: Dict[str, Any],
    indicator: Dict[str, Any],
    risk_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Evaluate deterministic urban-heat rules and build explainable NLG rationales."""
    recs: List[Dict[str, Any]] = []

    name = neighbourhood["name"]
    zone = neighbourhood["zone"]
    pop = neighbourhood.get("population_estimate") or 50000
    lst = indicator.get("land_surface_temp_c")
    air = indicator.get("air_temp_c")
    veg = indicator.get("ndvi_vegetation_pct")
    built = indicator.get("built_up_intensity_pct")
    albedo = indicator.get("albedo_index")
    low_income = indicator.get("low_income_housing_pct")
    outdoor_workers = indicator.get("outdoor_worker_pct")
    elderly = indicator.get("elderly_pct")
    cooling_cov = indicator.get("cooling_facility_coverage_pct")
    health_dist = indicator.get("healthcare_distance_km")

    e_score = risk_result.get("exposure_score") or 0.0
    v_score = risk_result.get("vulnerability_score") or 0.0
    c_score = risk_result.get("cooling_deficit_score") or 0.0
    overall = risk_result.get("overall_risk_score") or 0.0

    # 1. Cool-roof initiatives (High built-up + low albedo / high LST + vulnerable housing)
    if (built is not None and built >= 70.0) or (lst is not None and lst >= 45.0):
        priority = "Critical" if (lst or 0) >= 48.0 and (low_income or 0) >= 45.0 else "High"
        est_households = int((pop * ((low_income or 25.0) / 100.0)) / 4.2)
        rationale_parts = []
        triggered = []
        if lst is not None:
            rationale_parts.append(f"satellite land-surface temperature reaches {lst:.1f}°C")
            triggered.append(f"LST >= 45°C ({lst:.1f}°C)")
        if built is not None:
            rationale_parts.append(f"built-up surface intensity is {built:.1f}%")
            triggered.append(f"Built-up >= 70% ({built:.1f}%)")
        if albedo is not None and albedo < 0.23:
            rationale_parts.append(f"surface albedo is low ({albedo:.2f}), increasing rooftop heat absorption")
            triggered.append(f"Albedo < 0.23 ({albedo:.2f})")
        if low_income is not None and low_income >= 35.0:
            rationale_parts.append(f"{low_income:.0f}% of households live in heat-vulnerable/tin-sheet or dense housing")
            triggered.append(f"Vulnerable housing >= 35% ({low_income:.0f}%)")

        recs.append({
            "intervention_type": "Cool-roof initiatives",
            "title": f"Reflective Cool-Roof Coating Drive in {name}",
            "rationale": (
                f"Recommended because in {name}, " + "; ".join(rationale_parts) + ". "
                "Solar-reflective white lime or elastomeric cool-roof coatings reduce rooftop surface heat gain "
                "and indoor thermal stress in dense low-rise structures (indicative model rationale; requires site roof audit)."
            ),
            "target_location": f"High-density residential clusters & industrial sheds in {name} ({zone})",
            "priority_level": priority,
            "expected_beneficiaries": f"~{est_households:,} residents across heat-vulnerable rooftops (estimated)",
            "estimated_cost_range": "INR 12–28 Lakhs per 500 roofs (indicative municipal HAP benchmark)",
            "maintenance_considerations": "Re-coat reflective lime/elastomeric layer every 2–3 years before peak summer; wash monsoon dust annually.",
            "triggered_rules": triggered,
        })

    # 2. Tree plantation in suitable public spaces (Low vegetation / high exposure)
    if veg is not None and veg < 25.0:
        priority = "Critical" if veg < 10.0 and e_score >= 65.0 else ("High" if veg < 18.0 else "Medium")
        triggered = [f"NDVI Vegetation < 25% ({veg:.1f}%)"]
        if e_score >= 60:
            triggered.append(f"Exposure Score >= 60 ({e_score:.1f})")
        recs.append({
            "intervention_type": "Tree plantation in suitable public spaces",
            "title": f"Native Urban Canopy & Miyawaki Pocket Plantation — {name}",
            "rationale": (
                f"Vegetation coverage in {name} is only {veg:.1f}% (exposure score {e_score:.1f}/100). "
                "Planting drought-tolerant native shade species (Neem, Peepal, Karanj) along school yards, ward roads, "
                "and open municipal plots provides evapotranspiration cooling and long-term shade."
            ),
            "target_location": f"Municipal school campuses, road medians & open plots in {name}",
            "priority_level": priority,
            "expected_beneficiaries": f"~{int(pop * 0.18):,} daily pedestrians, students & nearby households (estimated)",
            "estimated_cost_range": "INR 8–18 Lakhs for 1,200 native saplings + 3-year tree guards (indicative estimate)",
            "maintenance_considerations": "Requires drip irrigation/tanker watering during first 24 months and community ward-level survival monitoring.",
            "triggered_rules": triggered,
        })

    # 3. Installation of shade structures (High outdoor workforce or high risk at transit hubs)
    if (outdoor_workers is not None and outdoor_workers >= 35.0) or overall >= 55.0:
        priority = "Critical" if (outdoor_workers or 0) >= 60.0 else "High"
        triggered = []
        if outdoor_workers is not None:
            triggered.append(f"Outdoor Workforce >= 35% ({outdoor_workers:.0f}%)")
        if overall >= 55.0:
            triggered.append(f"Overall Risk >= 55 ({overall:.1f})")
        recs.append({
            "intervention_type": "Installation of shade structures",
            "title": f"Modular Shade Canopies at Markets & Transit Stops in {name}",
            "rationale": (
                f"{name} has an estimated {outdoor_workers or 'significant'}% outdoor workforce and an overall heat-risk score "
                f"of {overall:.1f}/100. Immediate tensile shade canopies or bamboo/cool-net pergolas at bus stops, labour nakas, "
                "and street markets provide fast midday relief while tree canopy matures."
            ),
            "target_location": f"BRTS/AMTS bus stops, daily labour chowks & street vendor zones in {name}",
            "priority_level": priority,
            "expected_beneficiaries": f"~{int(pop * ((outdoor_workers or 30) / 100.0) * 0.35):,} outdoor workers & daily commuters (estimated)",
            "estimated_cost_range": "INR 6–15 Lakhs for 8–12 modular UV-stabilized shade canopies (indicative estimate)",
            "maintenance_considerations": "Inspect structural anchors before pre-monsoon winds; clean or replace shade fabric every 3–4 years.",
            "triggered_rules": triggered,
        })

    # 4. Public drinking-water facilities (High cooling-access deficit or high temp)
    if (cooling_cov is not None and cooling_cov < 55.0) or (c_score >= 50.0):
        priority = "Critical" if c_score >= 70.0 else "High"
        triggered = [f"Cooling Deficit Score {c_score:.1f}/100"]
        if cooling_cov is not None:
            triggered.append(f"Cooling Facility Coverage < 55% ({cooling_cov:.0f}%)")
        if health_dist is not None and health_dist >= 2.0:
            triggered.append(f"Health/Cooling Facility Distance {health_dist:.1f} km")
        recs.append({
            "intervention_type": "Public drinking-water facilities",
            "title": f"Chilled Drinking-Water & ORS Kiosks Network in {name}",
            "rationale": (
                f"Cooling-access deficit in {name} is {c_score:.1f}/100 with existing cooling facility coverage at "
                f"{cooling_cov if cooling_cov is not None else 'unverified'}%. Adding municipal water ATMs / shaded "
                "pyao kiosks with ORS packets reduces dehydration risk during peak afternoon heat."
            ),
            "target_location": f"Transit junctions, ward clinics & market entry points in {name}",
            "priority_level": priority,
            "expected_beneficiaries": f"~{int(pop * 0.25):,} residents, delivery workers & market visitors (estimated)",
            "estimated_cost_range": "INR 5–12 Lakhs for 4–6 solar-chilled water kiosks (indicative estimate)",
            "maintenance_considerations": "Daily water-quality testing, filter replacement every 3 months, and seasonal ORS restocking.",
            "triggered_rules": triggered,
        })

    # 5. Shaded walking routes (High elderly % or high built-up + low canopy corridors)
    if (elderly is not None and elderly >= 11.5) or ((built or 0) >= 65.0 and (veg or 100) < 22.0):
        priority = "High" if overall >= 60.0 else "Medium"
        triggered = []
        if elderly is not None and elderly >= 11.5:
            triggered.append(f"Elderly Population >= 11.5% ({elderly:.1f}%)")
        if built is not None:
            triggered.append(f"High Built-up Corridor ({built:.1f}%)")
        recs.append({
            "intervention_type": "Shaded walking routes",
            "title": f"Cool Walking Corridors to Schools & Health Centres in {name}",
            "rationale": (
                f"With {elderly or 'elevated'}% elderly residents and {veg or 'low'}% vegetation cover, pedestrians walking "
                "to clinics, primary schools, and transit stops face sustained radiant heat. Combining continuous avenue shade, "
                "cool-pavement coatings, and rest benches lowers pedestrian heat stress."
            ),
            "target_location": f"Primary pedestrian links connecting residential lanes to clinics & schools in {name}",
            "priority_level": priority,
            "expected_beneficiaries": f"~{int(pop * 0.14):,} senior citizens, students & daily walkers (estimated)",
            "estimated_cost_range": "INR 18–35 Lakhs per 1.5 km corridor (requires engineering survey)",
            "maintenance_considerations": "Keep pedestrian paths encroachment-free; maintain benches, avenue trees, and high-albedo pavement markings.",
            "triggered_rules": triggered,
        })

    # 6. Green-space development (Moderate-to-high built-up or low cooling coverage, or preventive buffer)
    if (built is not None and built >= 50.0) or (veg is not None and veg < 35.0) or not recs:
        priority = "High" if (built or 0) >= 75.0 else ("Medium" if overall >= 35.0 else "Low")
        triggered = []
        if built is not None:
            triggered.append(f"Built-up Intensity {built:.1f}%")
        if veg is not None:
            triggered.append(f"Vegetation Coverage {veg:.1f}%")
        recs.append({
            "intervention_type": "Green-space development",
            "title": f"Neighbourhood Pocket Park & Permeable Green Buffer in {name}",
            "rationale": (
                f"To counter urban heat-island retention in {name} (built-up {built or 'N/A'}%, vegetation {veg or 'N/A'}%), "
                "converting underutilized municipal plots into shaded pocket parks with permeable paving and misting/water "
                "features creates local cool-island microclimates."
            ),
            "target_location": f"Underutilized municipal plots & buffer strips in {name}",
            "priority_level": priority,
            "expected_beneficiaries": f"~{int(pop * 0.22):,} neighbourhood families & children (estimated)",
            "estimated_cost_range": "INR 25–60 Lakhs depending on municipal land availability (requires site survey)",
            "maintenance_considerations": "Assign ward parks department upkeep, rainwater harvesting recharge pits, and evening lighting.",
            "triggered_rules": triggered or ["Preventive Urban Heat Resilience"],
        })

    recs.sort(key=lambda r: _priority_rank(r["priority_level"]))
    return recs
