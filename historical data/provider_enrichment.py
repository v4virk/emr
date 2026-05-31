"""Doctor + hospital dataset generation and patient enrichment.

This module generates:
- hospitals.json (master)
- doctors.json (master)
- doctor_patient_index.json (doctor -> patients treated)

And enriches x/patient_dataset.json in-place by adding a `care_history` array
aligned with (medical_events, hospital_admissions, hospital_discharges).

The goal is to make the dataset more realistic by showing:
- patients visiting multiple doctors
- patients visiting multiple hospitals
- linking each visit to doctor + hospital + specialization

Synthetic data only. Not medical advice.
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# JSON utilities
# -----------------------------


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: Path, obj: Any, *, indent: int = 4) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent)
    tmp.replace(path)


def _backup_file(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}_backup_{ts}{path.suffix}")
    backup.write_bytes(path.read_bytes())
    return backup


# -----------------------------
# Providers model
# -----------------------------


SPECIALIZATIONS = [
    "General Medicine",
    "Emergency Medicine",
    "Internal Medicine",
    "Cardiology",
    "Pulmonology",
    "Endocrinology",
    "Gastroenterology",
    "Nephrology",
    "Neurology",
    "Dermatology",
    "Infectious Disease",
    "Orthopedics",
]


DOCTOR_FIRST_NAMES = [
    "Anjali",
    "Priya",
    "Neha",
    "Pooja",
    "Asha",
    "Meera",
    "Suman",
    "Kavya",
    "Isha",
    "Riya",
    "Rahul",
    "Amit",
    "Vikram",
    "Arjun",
    "Karan",
    "Rohit",
    "Suresh",
    "Manish",
    "Deepak",
    "Nitin",
]


DOCTOR_LAST_NAMES = [
    "Sharma",
    "Gupta",
    "Kumar",
    "Singh",
    "Mehta",
    "Joshi",
    "Iyer",
    "Nair",
    "Reddy",
    "Patel",
    "Khan",
    "Das",
    "Ghosh",
    "Verma",
    "Yadav",
]


HOSPITAL_BRANDS = [
    "CityCare",
    "Metro",
    "LifeSpring",
    "Apollo",
    "Fortis",
    "Medanta",
    "Max",
    "Aster",
    "Global",
    "Narayana",
]


HOSPITAL_TYPES = [
    "multi_specialty",
    "community",
    "teaching",
    "diagnostic_center",
    "emergency_center",
]


BILLING_LINE_CATALOG = [
    {"code": "CONSULT", "name": "Doctor consultation"},
    {"code": "ROOM", "name": "Room charges"},
    {"code": "ICU", "name": "ICU charges"},
    {"code": "NURSING", "name": "Nursing charges"},
    {"code": "LAB", "name": "Lab tests"},
    {"code": "IMAGING", "name": "Imaging"},
    {"code": "MED", "name": "Medicines"},
    {"code": "PROC", "name": "Procedures"},
    {"code": "SURG", "name": "Surgery"},
    {"code": "MISC", "name": "Miscellaneous"},
]


def _parse_date_yyyy_mm_dd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _days_between(start: str, end: str) -> int:
    """Inclusive-ish day count; minimum 1."""
    try:
        a = _parse_date_yyyy_mm_dd(start)
        b = _parse_date_yyyy_mm_dd(end)
        d = (b - a).days
        return max(1, d if d > 0 else 1)
    except Exception:
        return 1


def _hospital_cost_multiplier(hospital_type: str) -> float:
    t = (hospital_type or "").lower()
    if t == "multi_specialty":
        return 1.25
    if t == "teaching":
        return 1.15
    if t == "community":
        return 0.95
    if t == "diagnostic_center":
        return 0.9
    if t == "emergency_center":
        return 1.05
    return 1.0


def _severity_multiplier(outcome: str) -> float:
    o = (outcome or "").lower()
    if o == "recovered":
        return 0.95
    if o == "improved":
        return 1.05
    if o == "critical":
        return 1.35
    return 1.0


def generate_billing_for_visit(
    *,
    visit_date: str,
    admission_date: str,
    discharge_date: str,
    ward: str,
    outcome: str,
    hospital_type: str,
    tests_count: int,
) -> Dict[str, Any]:
    """Generate an itemized bill for a single visit/stay."""
    los_days = _days_between(admission_date, discharge_date)

    mult = _hospital_cost_multiplier(hospital_type) * _severity_multiplier(outcome)
    ward = ward or "general"

    # Base rates (synthetic INR)
    room_rate = 2500 if ward != "ICU" else 0
    icu_rate = 15000 if ward == "ICU" else 0
    nursing_rate = 800 if ward != "ICU" else 2000

    consult_fee = int(round(random.uniform(600, 1800) * mult))
    room_charges = int(round(room_rate * los_days * mult))
    icu_charges = int(round(icu_rate * los_days * mult))
    nursing_charges = int(round(nursing_rate * los_days * mult))

    # Tests & imaging depend on tests_count
    lab_qty = max(1, tests_count)
    lab_unit = int(round(random.uniform(400, 1500) * mult))
    lab_amount = int(lab_qty * lab_unit)

    imaging_qty = 1 if random.random() < (0.25 + 0.15 * (ward == "ICU")) else 0
    imaging_unit = int(round(random.uniform(1500, 9000) * mult)) if imaging_qty else 0
    imaging_amount = int(imaging_qty * imaging_unit)

    med_amount = int(round(random.uniform(700, 6000) * los_days * mult))

    # Procedures / surgery are rare; more common in ICU
    proc_qty = 1 if random.random() < (0.12 + 0.12 * (ward == "ICU")) else 0
    proc_amount = int(round(random.uniform(5000, 40000) * mult)) if proc_qty else 0

    surg_qty = 1 if random.random() < 0.04 else 0
    surg_amount = int(round(random.uniform(40000, 180000) * mult)) if surg_qty else 0

    misc_amount = int(round(random.uniform(200, 2500) * mult))

    line_items: List[Dict[str, Any]] = []

    def add(code: str, name: str, qty: int, unit_price: int, amount: int) -> None:
        if qty <= 0 or amount <= 0:
            return
        line_items.append(
            {
                "code": code,
                "name": name,
                "qty": qty,
                "unit_price": unit_price,
                "amount": amount,
            }
        )

    add("CONSULT", "Doctor consultation", 1, consult_fee, consult_fee)
    if ward == "ICU":
        add("ICU", "ICU charges", los_days, int(round(icu_rate * mult)), icu_charges)
    else:
        add("ROOM", "Room charges", los_days, int(round(room_rate * mult)), room_charges)
    add("NURSING", "Nursing charges", los_days, int(round(nursing_rate * mult)), nursing_charges)
    add("LAB", "Lab tests", lab_qty, lab_unit, lab_amount)
    if imaging_qty:
        add("IMAGING", "Imaging", imaging_qty, imaging_unit, imaging_amount)
    add("MED", "Medicines", max(1, los_days), int(round(med_amount / max(1, los_days))), med_amount)
    if proc_qty:
        add("PROC", "Procedures", 1, proc_amount, proc_amount)
    if surg_qty:
        add("SURG", "Surgery", 1, surg_amount, surg_amount)
    add("MISC", "Miscellaneous", 1, misc_amount, misc_amount)

    subtotal = sum(i["amount"] for i in line_items)
    tax_rate = random.uniform(0.05, 0.18)
    tax = int(round(subtotal * tax_rate))
    total = int(subtotal + tax)

    billing_mode = random.choice(
        ["cash", "card", "upi", "insurance_cashless", "insurance_reimbursement"]
    )

    return {
        "invoice_id": _new_id("INV", 8),
        "invoice_date": discharge_date or visit_date,
        "currency": "INR",
        "billing_mode": billing_mode,
        "length_of_stay_days": los_days,
        "tax_rate": round(tax_rate, 3),
        "line_items": line_items,
        "totals": {"subtotal": subtotal, "tax": tax, "total_billed": total},
    }


def _new_id(prefix: str, n: int = 6) -> str:
    return prefix + str(uuid.uuid4()).replace("-", "")[:n]


def _choose_weighted(items: List[str], weights: List[float]) -> str:
    # random.choices returns list
    return random.choices(items, weights=weights, k=1)[0]


def disease_to_specialization(disease_code: str, disease_name: str) -> str:
    """Heuristic mapping: disease -> plausible doctor specialization."""
    dc = (disease_code or "").upper()
    dn = (disease_name or "").lower()

    # Respiratory
    if dc in {"J18", "J45", "J20", "U07", "J32"} or any(x in dn for x in ["pneum", "asth", "bronch", "covid", "sinus"]):
        return _choose_weighted(
            ["Pulmonology", "Internal Medicine", "Emergency Medicine"],
            [0.55, 0.25, 0.20],
        )

    # Cardio
    if dc in {"I10", "I21", "I50", "E78"} or any(x in dn for x in ["hypertens", "heart", "lipid"]):
        return _choose_weighted(["Cardiology", "Internal Medicine", "General Medicine"], [0.6, 0.25, 0.15])

    # Endocrine
    if dc in {"E11", "E03", "E05", "E66"} or any(x in dn for x in ["diabet", "thyroid", "obes"]):
        return _choose_weighted(["Endocrinology", "Internal Medicine", "General Medicine"], [0.65, 0.2, 0.15])

    # GI
    if dc in {"K21", "K35", "K58", "K50", "K74", "K80"} or any(x in dn for x in ["gerd", "append", "ibs", "crohn", "cirrhos", "gall"]):
        return _choose_weighted(["Gastroenterology", "Internal Medicine", "Emergency Medicine"], [0.6, 0.25, 0.15])

    # Kidney
    if dc in {"N18"} or "kidney" in dn:
        return _choose_weighted(["Nephrology", "Internal Medicine"], [0.7, 0.3])

    # Neuro
    if dc in {"G40", "G03", "G43"} or any(x in dn for x in ["epilep", "mening", "migraine"]):
        return _choose_weighted(["Neurology", "Internal Medicine"], [0.7, 0.3])

    # Derm
    if dc in {"L40"} or any(x in dn for x in ["psoria", "rash"]):
        return _choose_weighted(["Dermatology", "General Medicine"], [0.75, 0.25])

    # Infection
    if dc in {"A90", "B54", "A01", "A41", "B34"} or any(x in dn for x in ["dengue", "malaria", "typh", "sepsis", "viral"]):
        return _choose_weighted(
            ["Infectious Disease", "Internal Medicine", "Emergency Medicine"],
            [0.55, 0.25, 0.20],
        )

    return _choose_weighted(["General Medicine", "Internal Medicine"], [0.6, 0.4])


def generate_hospitals(*, cities: List[str], count: int) -> List[Dict[str, Any]]:
    hospitals: List[Dict[str, Any]] = []
    used_names: set[str] = set()
    for _ in range(count):
        # Ensure unique-ish name
        for _try in range(50):
            brand = random.choice(HOSPITAL_BRANDS)
            city = random.choice(cities)
            suffix = random.choice(["Hospital", "Medical Center", "Care", "Clinic", "Institute"])
            name = f"{brand} {suffix} ({city})"
            if name not in used_names:
                used_names.add(name)
                break
        hospital_id = _new_id("H", 6)
        hospitals.append(
            {
                "hospital_id": hospital_id,
                "name": name,
                "city": city,
                "type": random.choice(HOSPITAL_TYPES),
            }
        )
    return hospitals


def generate_doctors(*, count: int, hospitals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not hospitals:
        raise ValueError("hospitals list is empty")

    doctors: List[Dict[str, Any]] = []
    used_names: set[str] = set()

    hospital_ids = [h["hospital_id"] for h in hospitals]
    for _ in range(count):
        for _try in range(50):
            fname = random.choice(DOCTOR_FIRST_NAMES)
            lname = random.choice(DOCTOR_LAST_NAMES)
            name = f"Dr. {fname} {lname}"
            if name not in used_names:
                used_names.add(name)
                break

        doctor_id = _new_id("D", 6)
        specialization = random.choice(SPECIALIZATIONS)

        # Assign the doctor to 1-3 hospitals
        n_h = random.randint(1, 3)
        doc_hospitals = random.sample(hospital_ids, n_h)

        doctors.append(
            {
                "doctor_id": doctor_id,
                "name": name,
                "specialization": specialization,
                "hospitals": doc_hospitals,
            }
        )
    return doctors


def _index_by(items: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    return {i[key]: i for i in items}


def _group_doctors_by_specialization(doctors: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by: Dict[str, List[Dict[str, Any]]] = {}
    for d in doctors:
        by.setdefault(d["specialization"], []).append(d)
    return by


def _pick_hospital_for_patient(patient: Dict[str, Any], hospitals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Bias hospital choice by patient address/city if possible."""
    city = (patient.get("patient_profile", {}) or {}).get("address")
    if city:
        city_h = [h for h in hospitals if h.get("city") == city]
        if city_h and random.random() < 0.75:
            return random.choice(city_h)
    return random.choice(hospitals)


def _pick_doctor(
    *,
    desired_specialization: str,
    hospital_id: str,
    doctors_by_spec: Dict[str, List[Dict[str, Any]]],
    all_doctors: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Pick a doctor matching specialization, preferably one that practices at hospital_id."""
    candidates = doctors_by_spec.get(desired_specialization, [])
    if not candidates:
        candidates = all_doctors

    # Prefer doctors who work at the chosen hospital
    in_hospital = [d for d in candidates if hospital_id in (d.get("hospitals") or [])]
    if in_hospital and random.random() < 0.85:
        return random.choice(in_hospital)
    return random.choice(candidates)


def enrich_patients_with_providers(
    patients: List[Dict[str, Any]],
    *,
    hospitals: List[Dict[str, Any]],
    doctors: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (enriched_patients, doctor_patient_index)."""
    hospitals_by_id = _index_by(hospitals, "hospital_id")
    doctors_by_id = _index_by(doctors, "doctor_id")
    doctors_by_spec = _group_doctors_by_specialization(doctors)

    # doctor_id -> set of (patient_id, patient_name, disease)
    doctor_patient_map: Dict[str, Dict[str, Any]] = {}

    for patient in patients:
        profile = patient.get("patient_profile", {}) or {}
        patient_id = profile.get("patient_id")
        patient_name = profile.get("name")

        events = patient.get("medical_events", []) or []
        admissions = patient.get("hospital_admissions", []) or []
        discharges = patient.get("hospital_discharges", []) or []
        n = min(len(events), len(admissions), len(discharges))

        care_history: List[Dict[str, Any]] = []
        visited_doctors: List[Dict[str, Any]] = []
        visited_hospitals: List[Dict[str, Any]] = []

        prev_hospital_id: Optional[str] = None
        prev_doctor_id: Optional[str] = None

        for i in range(n):
            ev = events[i]
            adm = admissions[i]
            dis = discharges[i]

            disease_code = ev.get("disease_code")
            disease_name = ev.get("disease")
            ward = adm.get("ward")

            desired_spec = disease_to_specialization(disease_code, disease_name)

            # With some probability, keep the same hospital/doctor to model continuity.
            # With some probability, change doctor/hospital to model referrals/second opinions.
            if prev_hospital_id and random.random() < 0.65:
                hospital = hospitals_by_id.get(prev_hospital_id) or _pick_hospital_for_patient(patient, hospitals)
            else:
                hospital = _pick_hospital_for_patient(patient, hospitals)

            hospital_id = hospital["hospital_id"]

            if prev_doctor_id and random.random() < 0.55:
                doctor = doctors_by_id.get(prev_doctor_id)
                if not doctor:
                    doctor = _pick_doctor(
                        desired_specialization=desired_spec,
                        hospital_id=hospital_id,
                        doctors_by_spec=doctors_by_spec,
                        all_doctors=doctors,
                    )
            else:
                doctor = _pick_doctor(
                    desired_specialization=desired_spec,
                    hospital_id=hospital_id,
                    doctors_by_spec=doctors_by_spec,
                    all_doctors=doctors,
                )

            doctor_id = doctor["doctor_id"]

            hospital_type = (hospital.get("type") or "")
            tests_count = 0
            # tests can be in older "tests_conducted" list or implicitly from lab_report keys
            if isinstance(ev.get("tests_conducted"), list):
                tests_count += len(ev.get("tests_conducted") or [])
            if isinstance(ev.get("lab_report"), dict):
                tests_count += len(ev.get("lab_report") or {})

            billing = generate_billing_for_visit(
                visit_date=(ev.get("event_date") or adm.get("admission_date") or ""),
                admission_date=(adm.get("admission_date") or ev.get("event_date") or ""),
                discharge_date=(dis.get("discharge_date") or ev.get("event_date") or ""),
                ward=ward,
                outcome=(dis.get("outcome") or ""),
                hospital_type=hospital_type,
                tests_count=tests_count,
            )

            visit = {
                "visit_id": _new_id("VIS", 8),
                "stay_index": i,
                "event_id": ev.get("event_id"),
                "visit_date": ev.get("event_date") or adm.get("admission_date"),
                "ward": ward,
                "outcome": dis.get("outcome"),
                "disease_code": disease_code,
                "disease": disease_name,
                "hospital_id": hospital_id,
                "hospital_name": hospital.get("name"),
                "hospital_city": hospital.get("city"),
                "hospital_type": hospital_type,
                "doctor_id": doctor_id,
                "doctor_name": doctor.get("name"),
                "specialization": desired_spec,
                "billing": billing,
            }
            care_history.append(visit)

            # Update doctor->patients index
            entry = doctor_patient_map.setdefault(
                doctor_id,
                {
                    "doctor_id": doctor_id,
                    "doctor_name": doctor.get("name"),
                    "specialization": doctor.get("specialization"),
                    "patients": {},  # dict for uniqueness
                },
            )
            entry["patients"][patient_id] = {
                "patient_id": patient_id,
                "patient_name": patient_name,
                "disease": disease_name,
                "disease_code": disease_code,
            }

            prev_hospital_id = hospital_id
            prev_doctor_id = doctor_id

        # Attach to patient record
        patient["care_history"] = care_history
        patient["visited_doctors"] = [
            {"doctor_id": v["doctor_id"], "doctor_name": v["doctor_name"]}
            for v in _unique_by(care_history, key="doctor_id")
        ]
        patient["visited_hospitals"] = [
            {"hospital_id": v["hospital_id"], "hospital_name": v["hospital_name"], "city": v["hospital_city"]}
            for v in _unique_by(care_history, key="hospital_id")
        ]

    # Convert doctor_patient_map into output list; convert nested dict patients->list
    doctor_patient_index: List[Dict[str, Any]] = []
    for d in doctor_patient_map.values():
        patients_dict = d.pop("patients")
        d["patients"] = list(patients_dict.values())
        doctor_patient_index.append(d)

    # Sort for stability
    doctor_patient_index.sort(key=lambda x: x["doctor_name"])

    return patients, doctor_patient_index


def _unique_by(items: List[Dict[str, Any]], *, key: str) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        v = it.get(key)
        if v is None or v in seen:
            continue
        seen.add(v)
        out.append(it)
    return out


# -----------------------------
# High-level runner for menu
# -----------------------------


def run_provider_enrichment(
    *,
    base_dir: Path,
    dataset_path: Path,
    doctors_count: int = 50,
    hospitals_count: int = 20,
    create_backup: bool = True,
) -> Dict[str, Path]:
    """Generate doctors/hospitals, enrich patient dataset in-place, and export index files.

    Returns dict of output paths.
    """
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    patients: List[Dict[str, Any]] = _read_json(dataset_path)
    if not patients:
        raise ValueError("Dataset is empty")

    # derive cities from patient addresses to keep hospitals realistic
    cities = sorted(
        {((p.get("patient_profile", {}) or {}).get("address") or "Unknown") for p in patients}
    )
    if not cities:
        cities = ["Delhi", "Mumbai", "Pune", "Hyderabad", "Chennai"]

    hospitals = generate_hospitals(cities=cities, count=hospitals_count)
    doctors = generate_doctors(count=doctors_count, hospitals=hospitals)

    enriched, doctor_patient_index = enrich_patients_with_providers(
        patients,
        hospitals=hospitals,
        doctors=doctors,
    )

    hospitals_path = base_dir / "hospitals.json"
    doctors_path = base_dir / "doctors.json"
    index_path = base_dir / "doctor_patient_index.json"

    _atomic_write_json(hospitals_path, hospitals, indent=4)
    _atomic_write_json(doctors_path, doctors, indent=4)
    _atomic_write_json(index_path, doctor_patient_index, indent=4)

    backup_path = _backup_file(dataset_path) if create_backup else None
    _atomic_write_json(dataset_path, enriched, indent=4)

    out: Dict[str, Path] = {
        "hospitals": hospitals_path,
        "doctors": doctors_path,
        "doctor_patient_index": index_path,
        "dataset": dataset_path,
    }
    if backup_path:
        out["backup"] = backup_path
    return out
