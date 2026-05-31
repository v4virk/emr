"""ICU core vitals generator (real-time streaming) for one chosen patient stay.

This module is designed to integrate with the terminal menu in x/main.py.

Outputs a JSON file under x/ named:
    vitals_<patient_id>_<timestamp>.json

The output includes:
- patient_profile (referential link)
- selected stay metadata (event + admission + discharge)
- history summary (referential link)
- vitals_stream readings (time-series)

Disclaimer: Synthetic data only. Not medical advice.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Utility helpers
# -----------------------------


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: Path, obj: Any, *, indent: int = 4) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent)
    tmp.replace(path)


def _parse_date_yyyy_mm_dd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _map_value(x: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
    if in_max == in_min:
        return out_min
    t = (x - in_min) / (in_max - in_min)
    t = _clamp(t, 0.0, 1.0)
    return out_min + t * (out_max - out_min)


def _calc_map(sbp: float, dbp: float) -> float:
    # MAP ≈ DBP + 1/3(PP)
    return dbp + (sbp - dbp) / 3.0


def _severity_from_outcome(outcome: str) -> float:
    """Return a severity scalar in [0..1]."""
    outcome = (outcome or "").lower()
    if outcome == "recovered":
        return 0.25
    if outcome == "improved":
        return 0.55
    if outcome == "critical":
        return 0.85
    return 0.5


# -----------------------------
# Simple physiology-ish model
# -----------------------------


@dataclass
class VitalsState:
    hr: float
    sbp: float
    dbp: float
    spo2: float
    rr: float
    temp_c: float


def _baseline_vitals() -> VitalsState:
    return VitalsState(
        hr=80.0,
        sbp=120.0,
        dbp=80.0,
        spo2=97.0,
        rr=16.0,
        temp_c=37.0,
    )


def _disease_profile(disease_code: str) -> Dict[str, float]:
    """Return per-disease bias deltas.

    Values here are synthetic heuristics to make data *plausible-looking*.
    """
    dc = (disease_code or "").upper()

    # Default: small/no change
    prof = {
        "hr": 0.0,
        "sbp": 0.0,
        "dbp": 0.0,
        "spo2": 0.0,
        "rr": 0.0,
        "temp": 0.0,
    }

    # Respiratory/infectious-ish
    if dc in {"J18", "U07", "J20"}:  # Pneumonia, COVID, Bronchitis
        prof.update({"spo2": -4.0, "rr": +6.0, "hr": +10.0, "temp": +0.8})
    if dc in {"J45"}:  # Asthma
        prof.update({"spo2": -2.5, "rr": +7.0, "hr": +8.0})
    if dc in {"A90", "B54", "A01", "B34"}:  # Dengue, Malaria, Typhoid, Viral fever
        prof.update({"temp": +1.3, "hr": +12.0, "rr": +2.0})
    if dc in {"A41"}:  # Sepsis
        prof.update({"temp": +1.2, "hr": +18.0, "sbp": -15.0, "dbp": -10.0, "rr": +6.0})

    # Cardiovascular
    if dc in {"I10"}:  # Hypertension
        prof.update({"sbp": +15.0, "dbp": +10.0})
    if dc in {"I21", "I50"}:  # Heart attack / heart failure
        prof.update({"sbp": -10.0, "dbp": -6.0, "hr": +12.0, "spo2": -2.0, "rr": +4.0})

    # Metabolic
    if dc in {"E11"}:  # Type 2 diabetes
        prof.update({"hr": +4.0})
    if dc in {"E05"}:  # Hyperthyroidism
        prof.update({"hr": +14.0, "temp": +0.3})
    if dc in {"E03"}:  # Hypothyroidism
        prof.update({"hr": -8.0, "temp": -0.2})

    # Neurologic
    if dc in {"G03"}:  # Meningitis
        prof.update({"temp": +1.2, "hr": +10.0})

    return prof


def _apply_bias(state: VitalsState, *, disease_code: str, outcome: str) -> VitalsState:
    severity = _severity_from_outcome(outcome)
    d = _disease_profile(disease_code)

    # scale disease deltas by severity
    state.hr += d["hr"] * (0.7 + severity)
    state.sbp += d["sbp"] * (0.7 + severity)
    state.dbp += d["dbp"] * (0.7 + severity)
    state.spo2 += d["spo2"] * (0.7 + severity)
    state.rr += d["rr"] * (0.7 + severity)
    state.temp_c += d["temp"] * (0.7 + severity)

    # additional systemic effects by outcome
    if (outcome or "").lower() == "critical":
        # More unstable, lower perfusion and oxygenation
        state.sbp -= 8.0
        state.dbp -= 5.0
        state.spo2 -= 2.0
        state.rr += 2.0
        state.hr += 6.0

    return state


def _next_reading(
    state: VitalsState,
    *,
    sample_idx: int,
    total_samples: int,
    disease_code: str,
    outcome: str,
) -> VitalsState:
    """Update state with drift + noise to produce next reading."""
    severity = _severity_from_outcome(outcome)

    # Trend: recovered/improved tends to normalize; critical may worsen or oscillate.
    progress = sample_idx / max(1, total_samples - 1)
    if (outcome or "").lower() in {"recovered", "improved"}:
        # Move toward baseline as time goes
        k = _map_value(progress, 0.0, 1.0, 0.02, 0.08)
        base = _baseline_vitals()
        state.hr += (base.hr - state.hr) * k
        state.sbp += (base.sbp - state.sbp) * k
        state.dbp += (base.dbp - state.dbp) * k
        state.spo2 += (base.spo2 - state.spo2) * k
        state.rr += (base.rr - state.rr) * k
        state.temp_c += (base.temp_c - state.temp_c) * k
    else:
        # Critical: slight drift away + jitter
        drift = 0.02 + 0.03 * severity
        state.hr += random.uniform(-2.0, 3.0) * drift
        state.sbp += random.uniform(-4.0, 2.0) * drift
        state.dbp += random.uniform(-3.0, 1.5) * drift
        state.spo2 += random.uniform(-1.5, 0.6) * drift
        state.rr += random.uniform(-1.0, 2.0) * drift
        state.temp_c += random.uniform(-0.2, 0.25) * drift

    # Always add measurement-ish noise
    state.hr += random.gauss(0, 2.0 + 2.0 * severity)
    state.sbp += random.gauss(0, 3.0 + 3.0 * severity)
    state.dbp += random.gauss(0, 2.0 + 2.0 * severity)
    state.spo2 += random.gauss(0, 0.6 + 0.6 * severity)
    state.rr += random.gauss(0, 1.0 + 1.0 * severity)
    state.temp_c += random.gauss(0, 0.05 + 0.08 * severity)

    # occasional desaturation episodes in respiratory disease
    if disease_code in {"J18", "U07", "J45", "J20"} and random.random() < (0.05 + 0.1 * severity):
        state.spo2 -= random.uniform(2.0, 5.0) * (0.5 + severity)
        state.rr += random.uniform(2.0, 6.0) * (0.5 + severity)
        state.hr += random.uniform(4.0, 10.0) * (0.5 + severity)

    # Clamp to plausible physiologic ranges
    state.hr = _clamp(state.hr, 35, 180)
    state.sbp = _clamp(state.sbp, 60, 220)
    state.dbp = _clamp(state.dbp, 35, 140)
    if state.dbp >= state.sbp:
        state.dbp = max(35.0, state.sbp - 10.0)
    state.spo2 = _clamp(state.spo2, 70, 100)
    state.rr = _clamp(state.rr, 6, 45)
    state.temp_c = _clamp(state.temp_c, 34.0, 41.0)

    return state


# -----------------------------
# Public API used by menu
# -----------------------------


def list_patient_stays(patient: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return a list of stays aligned by index (event, admission, discharge)."""
    events = patient.get("medical_events", [])
    admissions = patient.get("hospital_admissions", [])
    discharges = patient.get("hospital_discharges", [])

    stays: List[Dict[str, Any]] = []
    n = min(len(events), len(admissions), len(discharges))
    for i in range(n):
        stays.append({
            "stay_index": i,
            "event": events[i],
            "admission": admissions[i],
            "discharge": discharges[i],
        })
    return stays


def generate_vitals_for_patient_stay(
    *,
    base_dir: Path,
    dataset_path: Path,
    patient_id: str,
    stay_index: int,
    samples: int = 30,
    delay_seconds: float = 1.0,
    print_stream: bool = True,
) -> Path:
    """Generate a real-time vitals stream for one stay and save to JSON.

    Returns the output JSON path.
    """
    dataset: List[Dict[str, Any]] = _read_json(dataset_path)
    patient: Optional[Dict[str, Any]] = None
    for p in dataset:
        prof = p.get("patient_profile", {})
        if prof.get("patient_id") == patient_id:
            patient = p
            break

    if patient is None:
        raise ValueError(f"patient_id not found: {patient_id}")

    stays = list_patient_stays(patient)
    if not stays:
        raise ValueError("Selected patient has no stays to generate vitals for")
    if stay_index < 0 or stay_index >= len(stays):
        raise ValueError(f"stay_index out of range. Max index: {len(stays)-1}")

    stay = stays[stay_index]
    event = stay["event"]
    admission = stay["admission"]
    discharge = stay["discharge"]

    disease_code = event.get("disease_code")
    outcome = discharge.get("outcome")

    # Simulated timeline anchor: start at admission date, 08:00
    admission_date = _parse_date_yyyy_mm_dd(admission.get("admission_date"))
    simulated_start = admission_date.replace(hour=8, minute=0, second=0, microsecond=0)

    # Initial state = baseline + bias
    state = _baseline_vitals()
    state = _apply_bias(state, disease_code=disease_code, outcome=outcome)

    readings: List[Dict[str, Any]] = []
    for i in range(samples):
        now = datetime.now()
        simulated_ts = simulated_start + timedelta(minutes=5 * i)

        # update state
        state = _next_reading(
            state,
            sample_idx=i,
            total_samples=samples,
            disease_code=disease_code,
            outcome=outcome,
        )

        reading = {
            "real_timestamp": now.isoformat(timespec="seconds"),
            "simulated_timestamp": simulated_ts.isoformat(timespec="seconds"),
            "hr_bpm": int(round(state.hr)),
            "bp_systolic_mmhg": int(round(state.sbp)),
            "bp_diastolic_mmhg": int(round(state.dbp)),
            "map_mmhg": int(round(_calc_map(state.sbp, state.dbp))),
            "spo2_percent": int(round(state.spo2)),
            "rr_bpm": int(round(state.rr)),
            "temp_c": round(state.temp_c, 1),
        }
        readings.append(reading)

        if print_stream:
            print(
                f"[{i+1:03d}/{samples}] HR={reading['hr_bpm']} | BP={reading['bp_systolic_mmhg']}/{reading['bp_diastolic_mmhg']} (MAP {reading['map_mmhg']})"
                f" | SpO2={reading['spo2_percent']} | RR={reading['rr_bpm']} | Temp={reading['temp_c']}C"
            )

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    profile = patient.get("patient_profile", {})
    history = [
        {
            "event_date": e.get("event_date"),
            "disease_code": e.get("disease_code"),
            "disease": e.get("disease"),
        }
        for e in patient.get("medical_events", [])
    ]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = base_dir / f"vitals_{patient_id}_{ts}.json"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_dataset": str(dataset_path),
        "patient_profile": profile,
        "selected_stay": {
            "stay_index": stay_index,
            "event": {
                "event_id": event.get("event_id"),
                "event_date": event.get("event_date"),
                "disease_code": event.get("disease_code"),
                "disease": event.get("disease"),
                "symptoms": event.get("symptoms"),
            },
            "admission": admission,
            "discharge": discharge,
        },
        "history_summary": {
            "medical_event_count": len(patient.get("medical_events", [])),
            "events": history,
        },
        "vitals_stream": {
            "samples": samples,
            "delay_seconds": delay_seconds,
            "readings": readings,
        },
    }
    _atomic_write_json(out_path, payload, indent=4)
    return out_path
