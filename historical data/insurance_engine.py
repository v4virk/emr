"""Rule-based insurance claim engine (synthetic).

Implements the requested adjudication lifecycle:
1) Eligibility check
2) Coverage check
3) Provider/network check
4) Pre-authorization check
5) Document completeness
6) Cost sanity + benefit limits
7) Fraud/anomaly checks
8) Decision (APPROVED / PARTIAL_APPROVED / REJECTED / NEEDS_INFO / MANUAL_REVIEW)

Supports claim_mode:
- HOSPITAL
- SELF

Synthetic data only. Not legal/medical advice.
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
# Storage paths
# -----------------------------


def default_paths(base_dir: Path) -> Dict[str, Path]:
    return {
        "policies": base_dir / "insurance_policies.json",
        "claims": base_dir / "insurance_claims.json",
        "decisions": base_dir / "claim_decisions.json",
        "fraud_audit": base_dir / "fraud_audit.json",
    }


# -----------------------------
# JSON utilities
# -----------------------------


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: Path, obj: Any, *, indent: int = 4) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent)
    tmp.replace(path)


def _new_id(prefix: str, n: int = 8) -> str:
    return prefix + str(uuid.uuid4()).replace("-", "")[:n]


def _parse_date_yyyy_mm_dd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _days_between(start: str, end: str) -> int:
    try:
        a = _parse_date_yyyy_mm_dd(start)
        b = _parse_date_yyyy_mm_dd(end)
        return max(1, (b - a).days)
    except Exception:
        return 1


# -----------------------------
# Policy generation
# -----------------------------


PLANS = [
    {
        "name": "Bronze",
        "sum_insured": 200000,
        "deductible": 10000,
        "copay_percent": 20,
        "icu_daily_cap": 12000,
        "room_daily_cap": 2500,
        "preauth_required_above": 80000,
    },
    {
        "name": "Silver",
        "sum_insured": 350000,
        "deductible": 8000,
        "copay_percent": 15,
        "icu_daily_cap": 15000,
        "room_daily_cap": 3500,
        "preauth_required_above": 100000,
    },
    {
        "name": "Gold",
        "sum_insured": 500000,
        "deductible": 5000,
        "copay_percent": 10,
        "icu_daily_cap": 20000,
        "room_daily_cap": 5000,
        "preauth_required_above": 120000,
    },
    {
        "name": "Platinum",
        "sum_insured": 800000,
        "deductible": 0,
        "copay_percent": 5,
        "icu_daily_cap": 28000,
        "room_daily_cap": 8000,
        "preauth_required_above": 150000,
    },
]


def _generate_premium_history(
    *,
    start_date: str,
    end_date: str,
    frequency: str,
) -> List[Dict[str, Any]]:
    """Generate premium payment history records with paid/missed/late statuses."""
    # For simplicity we will create 12 months for 2023-like policy.
    # (Can be expanded later.)
    months = [
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
        "12",
    ]
    year = start_date[:4]
    out: List[Dict[str, Any]] = []
    for m in months:
        due = f"{year}-{m}-05"
        r = random.random()
        if r < 0.82:
            status = "PAID_ON_TIME"
            paid_date = due
        elif r < 0.93:
            status = "PAID_LATE"
            paid_date = f"{year}-{m}-15"
        else:
            status = "MISSED"
            paid_date = None
        out.append({"due_date": due, "paid_date": paid_date, "status": status})
    return out


def generate_policies_for_dataset(
    *,
    base_dir: Path,
    patient_dataset_path: Path,
    hospitals_path: Optional[Path] = None,
    doctors_path: Optional[Path] = None,
) -> Path:
    """Generate one policy per patient + premium history."""
    patients: List[Dict[str, Any]] = _read_json(patient_dataset_path, default=[])
    if not patients:
        raise ValueError("patient dataset is empty")

    # Try to use hospitals.json to define network hospitals
    hospitals: List[Dict[str, Any]] = []
    if hospitals_path and hospitals_path.exists():
        hospitals = _read_json(hospitals_path, default=[])

    hospital_ids = [h.get("hospital_id") for h in hospitals if h.get("hospital_id")]

    policies: List[Dict[str, Any]] = []
    for p in patients:
        prof = p.get("patient_profile", {}) or {}
        patient_id = prof.get("patient_id")

        plan = random.choices(PLANS, weights=[0.35, 0.3, 0.25, 0.1], k=1)[0]

        start_date = "2023-01-01"
        end_date = "2023-12-31"
        frequency = random.choice(["monthly", "quarterly", "annual"])
        premium_history = _generate_premium_history(
            start_date=start_date, end_date=end_date, frequency=frequency
        )

        # Determine active/lapsed from missed premiums (strict-ish)
        missed = sum(1 for r in premium_history if r["status"] == "MISSED")
        status = "ACTIVE" if missed <= 1 else "LAPSED"

        # Network hospital list: pick 6-10 random hospitals
        network_hospitals = (
            random.sample(hospital_ids, min(len(hospital_ids), random.randint(6, 10)))
            if hospital_ids
            else []
        )

        policy = {
            "policy_id": _new_id("POL", 8),
            "patient_id": patient_id,
            "insurer": random.choice(["HealthSecure", "MediShield", "CarePlus", "LifeGuard"]),
            "plan": plan["name"],
            "status": status,
            "start_date": start_date,
            "end_date": end_date,
            "premium_frequency": frequency,
            "premium_history": premium_history,
            "waiting_period_days": random.choice([30, 60, 90, 180]),
            "preauth_required_above": plan["preauth_required_above"],
            "deductible": plan["deductible"],
            "copay_percent": plan["copay_percent"],
            "icu_daily_cap": plan["icu_daily_cap"],
            "room_daily_cap": plan["room_daily_cap"],
            "sum_insured_total": plan["sum_insured"],
            "sum_insured_used": 0,
            "excluded_diseases": random.sample(
                ["Cosmetic", "Dental", "Fertility", "Psychiatric"],
                k=random.randint(0, 2),
            ),
            "network_hospitals": network_hospitals,
            "kyc_verified": random.random() < 0.92,
        }
        policies.append(policy)

    paths = default_paths(base_dir)
    _atomic_write_json(paths["policies"], policies, indent=4)
    return paths["policies"]


# -----------------------------
# Claims
# -----------------------------


REQUIRED_DOCUMENTS = [
    "itemized_bill",
    "discharge_summary",
    "doctor_notes",
    "prescriptions",
    "lab_reports",
]


def _find_patient_and_stay(dataset: List[Dict[str, Any]], patient_id: str, stay_index: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    for p in dataset:
        prof = p.get("patient_profile", {}) or {}
        if prof.get("patient_id") == patient_id:
            care = p.get("care_history", []) or []
            for v in care:
                if v.get("stay_index") == stay_index:
                    return p, v
            raise ValueError(f"stay_index {stay_index} not found for patient {patient_id}")
    raise ValueError(f"patient_id not found: {patient_id}")


def file_claim(
    *,
    base_dir: Path,
    patient_dataset_path: Path,
    patient_id: str,
    stay_index: int,
    claim_mode: str,
    claim_type: str = "reimbursement",
    documents: Optional[List[str]] = None,
    claimed_amount_override: Optional[int] = None,
) -> Path:
    """Create a claim record in insurance_claims.json."""
    claim_mode = (claim_mode or "").upper()
    if claim_mode not in {"HOSPITAL", "SELF"}:
        raise ValueError("claim_mode must be HOSPITAL or SELF")

    dataset: List[Dict[str, Any]] = _read_json(patient_dataset_path, default=[])
    patient, visit = _find_patient_and_stay(dataset, patient_id, stay_index)

    billing = (visit.get("billing") or {}).get("totals") or {}
    official_total = int(billing.get("total_billed") or 0)
    if official_total <= 0:
        # fallback
        official_total = random.randint(10000, 250000)

    # Claimed amount depends on mode (hospital may inflate; self may be incorrect)
    if claimed_amount_override is not None:
        claimed_amount = int(claimed_amount_override)
    else:
        if claim_mode == "HOSPITAL":
            inflate = random.uniform(0.0, 0.25)  # hospital fraud potential
            claimed_amount = int(round(official_total * (1.0 + inflate)))
        else:
            # self claim: sometimes under/over; can be manipulated
            delta = random.uniform(-0.1, 0.35)
            claimed_amount = int(round(official_total * (1.0 + delta)))

    if documents is None:
        # Strictness: both modes can be missing docs
        docs = []
        for d in REQUIRED_DOCUMENTS:
            keep_prob = 0.88 if claim_mode == "HOSPITAL" else 0.8
            if random.random() < keep_prob:
                docs.append(d)
        documents = docs

    claim = {
        "claim_id": _new_id("CLM", 8),
        "patient_id": patient_id,
        "claim_mode": claim_mode,
        "claim_type": claim_type,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "stay_ref": {
            "stay_index": stay_index,
            "event_id": visit.get("event_id"),
            "visit_id": visit.get("visit_id"),
        },
        "provider_ref": {
            "hospital_id": visit.get("hospital_id"),
            "hospital_name": visit.get("hospital_name"),
            "doctor_id": visit.get("doctor_id"),
            "doctor_name": visit.get("doctor_name"),
        },
        "medical_ref": {
            "disease_code": visit.get("disease_code"),
            "disease": visit.get("disease"),
            "ward": visit.get("ward"),
            "outcome": visit.get("outcome"),
        },
        "official_billing": {
            "invoice_id": (visit.get("billing") or {}).get("invoice_id"),
            "total_billed": official_total,
        },
        "claimed_amount": claimed_amount,
        "documents": documents,
        "status": "SUBMITTED",
    }

    paths = default_paths(base_dir)
    claims: List[Dict[str, Any]] = _read_json(paths["claims"], default=[])
    claims.append(claim)
    _atomic_write_json(paths["claims"], claims, indent=4)
    return paths["claims"]


# -----------------------------
# Adjudication
# -----------------------------


def _policy_for_patient(policies: List[Dict[str, Any]], patient_id: str) -> Optional[Dict[str, Any]]:
    for pol in policies:
        if pol.get("patient_id") == patient_id:
            return pol
    return None


def _within_policy_dates(policy: Dict[str, Any], date_str: str) -> bool:
    try:
        d = _parse_date_yyyy_mm_dd(date_str)
        s = _parse_date_yyyy_mm_dd(policy["start_date"])
        e = _parse_date_yyyy_mm_dd(policy["end_date"])
        return s <= d <= e
    except Exception:
        return False


def _premiums_paid_enough(policy: Dict[str, Any]) -> bool:
    hist = policy.get("premium_history") or []
    missed = sum(1 for r in hist if r.get("status") == "MISSED")
    # strict: >1 missed => not eligible
    return missed <= 1


def _docs_missing(documents: List[str]) -> List[str]:
    have = set(documents or [])
    return [d for d in REQUIRED_DOCUMENTS if d not in have]


def _estimate_expected_total(visit: Dict[str, Any]) -> Tuple[int, int]:
    """Return (low, high) expected range based on ward, LOS, and outcome."""
    ward = (visit.get("ward") or "general").upper()
    outcome = (visit.get("outcome") or "improved").lower()
    bill = visit.get("billing") or {}
    los = int(bill.get("length_of_stay_days") or 1)

    base = 12000 * los
    if ward == "ICU":
        base = 65000 * max(1, los)
    if outcome == "critical":
        base *= 1.35
    if outcome == "recovered":
        base *= 0.95

    low = int(base * 0.6)
    high = int(base * 1.7)
    return low, high


def _apply_limits(
    *,
    policy: Dict[str, Any],
    visit: Dict[str, Any],
    claimed_amount: int,
) -> Tuple[int, List[str]]:
    """Apply deductible/copay/sub-limits and return (approved_amount, reasons)."""
    reasons: List[str] = []
    ward = (visit.get("ward") or "general").upper()
    bill = visit.get("billing") or {}
    los = int(bill.get("length_of_stay_days") or 1)

    sum_remaining = int(policy.get("sum_insured_total", 0)) - int(policy.get("sum_insured_used", 0))
    if sum_remaining <= 0:
        return 0, ["Sum insured exhausted"]

    approved = min(int(claimed_amount), int(sum_remaining))
    if approved < claimed_amount:
        reasons.append("Sum insured remaining cap applied")

    # Daily caps
    if ward == "ICU":
        cap = int(policy.get("icu_daily_cap", 0)) * max(1, los)
        if cap > 0 and approved > cap:
            approved = cap
            reasons.append("ICU daily cap applied")
    else:
        cap = int(policy.get("room_daily_cap", 0)) * max(1, los)
        if cap > 0 and approved > cap:
            approved = cap
            reasons.append("Room daily cap applied")

    # Deductible
    deductible = int(policy.get("deductible", 0))
    if deductible > 0:
        approved = max(0, approved - deductible)
        reasons.append("Deductible applied")

    # Copay
    copay = float(policy.get("copay_percent", 0)) / 100.0
    if copay > 0:
        copay_amt = int(round(approved * copay))
        approved = max(0, approved - copay_amt)
        reasons.append("Co-pay applied")

    return approved, reasons


def adjudicate_claims(
    *,
    base_dir: Path,
    patient_dataset_path: Path,
) -> Dict[str, Path]:
    """Adjudicate all SUBMITTED claims and write decisions."""
    paths = default_paths(base_dir)
    claims: List[Dict[str, Any]] = _read_json(paths["claims"], default=[])
    policies: List[Dict[str, Any]] = _read_json(paths["policies"], default=[])
    decisions: List[Dict[str, Any]] = _read_json(paths["decisions"], default=[])
    fraud_audit: List[Dict[str, Any]] = _read_json(paths["fraud_audit"], default=[])

    dataset: List[Dict[str, Any]] = _read_json(patient_dataset_path, default=[])
    if not dataset:
        raise ValueError("patient dataset is empty")

    # Provider risk tracking (derived from past fraud audit)
    provider_risk: Dict[str, float] = {}
    for fa in fraud_audit:
        hid = (fa.get("provider_ref") or {}).get("hospital_id")
        if not hid:
            continue
        provider_risk[hid] = max(provider_risk.get(hid, 0.0), float(fa.get("fraud_score") or 0.0))

    existing_claim_keys = set()
    for c in claims:
        key = (c.get("patient_id"), (c.get("stay_ref") or {}).get("stay_index"), (c.get("stay_ref") or {}).get("event_id"))
        existing_claim_keys.add(key)

    for claim in claims:
        if claim.get("status") != "SUBMITTED":
            continue

        patient_id = claim.get("patient_id")
        stay_index = int((claim.get("stay_ref") or {}).get("stay_index"))
        claim_mode = (claim.get("claim_mode") or "").upper()
        claimed_amount = int(claim.get("claimed_amount") or 0)

        patient, visit = _find_patient_and_stay(dataset, patient_id, stay_index)
        policy = _policy_for_patient(policies, patient_id)

        reasons: List[str] = []
        flags: List[str] = []
        fraud_score = 0.0

        # (1) Eligibility
        if not policy:
            decision_status = "REJECTED"
            reasons.append("No active policy found")
            approved_amount = 0
        else:
            visit_date = visit.get("visit_date") or (visit.get("billing") or {}).get("invoice_date")
            if policy.get("status") != "ACTIVE":
                reasons.append("Policy lapsed")
                decision_status = "REJECTED"
                approved_amount = 0
            elif not policy.get("kyc_verified"):
                reasons.append("KYC not verified")
                decision_status = "MANUAL_REVIEW"
                approved_amount = 0
                fraud_score += 0.25
            elif not visit_date or not _within_policy_dates(policy, visit_date):
                reasons.append("Visit date outside policy coverage")
                decision_status = "REJECTED"
                approved_amount = 0
            elif not _premiums_paid_enough(policy):
                reasons.append("Premiums unpaid/missed beyond allowed grace")
                decision_status = "REJECTED"
                approved_amount = 0
            else:
                decision_status = "PENDING"
                approved_amount = 0

        if decision_status in {"REJECTED", "MANUAL_REVIEW"}:
            # still record, but skip remaining checks in strict model
            pass
        else:
            # (2) Coverage
            disease = (visit.get("disease") or "")
            if disease in (policy.get("excluded_diseases") or []):
                reasons.append("Disease excluded by policy")
                decision_status = "REJECTED"
            # waiting period simulation (strict): if visit too early, reject
            # Here we just probabilistically apply for realism
            if random.random() < 0.05:
                reasons.append("Waiting period not satisfied")
                decision_status = "REJECTED"

        if decision_status == "REJECTED":
            approved_amount = 0
        elif decision_status == "MANUAL_REVIEW":
            approved_amount = 0
        elif decision_status == "PENDING":
            # (3) Provider/network
            hid = (claim.get("provider_ref") or {}).get("hospital_id")
            in_network = hid in (policy.get("network_hospitals") or [])
            if not in_network:
                flags.append("NON_NETWORK_HOSPITAL")
                fraud_score += 0.15
                # strict: hospital-mode + non-network is highly suspicious
                if claim_mode == "HOSPITAL":
                    reasons.append("Hospital-mode claim from non-network hospital")
                    decision_status = "MANUAL_REVIEW"
            # doctor specialization mismatch
            desired = (visit.get("specialization") or "")
            # if care_history specialization exists, accept; else review
            if not desired:
                flags.append("DOCTOR_SPECIALIZATION_UNKNOWN")
                fraud_score += 0.08

        if decision_status == "MANUAL_REVIEW":
            approved_amount = 0
        elif decision_status == "PENDING":
            # (4) Pre-auth
            ward = (visit.get("ward") or "general").upper()
            preauth_required = ward == "ICU" or claimed_amount >= int(policy.get("preauth_required_above", 10**9))
            preauth_present = random.random() < (0.78 if claim_mode == "HOSPITAL" else 0.6)
            if preauth_required and not preauth_present:
                reasons.append("Pre-authorization required but not found")
                decision_status = "REJECTED"

        if decision_status == "REJECTED":
            approved_amount = 0
        elif decision_status == "PENDING":
            # (5) Documents
            missing_docs = _docs_missing(claim.get("documents") or [])
            if missing_docs:
                # strict: missing itemized/discharge => needs info
                if "itemized_bill" in missing_docs or "discharge_summary" in missing_docs:
                    reasons.append("Missing critical documents: " + ", ".join(missing_docs))
                    decision_status = "NEEDS_INFO"
                else:
                    # some docs missing => review
                    reasons.append("Missing documents: " + ", ".join(missing_docs))
                    fraud_score += 0.1
                    decision_status = "MANUAL_REVIEW"

        if decision_status == "NEEDS_INFO":
            approved_amount = 0
        elif decision_status == "MANUAL_REVIEW":
            approved_amount = 0
        elif decision_status == "PENDING":
            # (6) Cost sanity + limits
            low, high = _estimate_expected_total(visit)
            if claimed_amount > high:
                flags.append("OVERBILLING_SUSPECT")
                fraud_score += 0.25
            if claimed_amount < low * 0.5:
                flags.append("UNDERBILLING_ODD")
                fraud_score += 0.05

            approved_amount, limit_reasons = _apply_limits(
                policy=policy,
                visit=visit,
                claimed_amount=claimed_amount,
            )
            reasons.extend(limit_reasons)

            # (7) Fraud/anomaly checks
            # Duplicate claim check
            key = (patient_id, stay_index, (claim.get("stay_ref") or {}).get("event_id"))
            # if more than 1 claim exists for same key => duplicate
            dup_count = sum(
                1
                for c in claims
                if (c.get("patient_id"), (c.get("stay_ref") or {}).get("stay_index"), (c.get("stay_ref") or {}).get("event_id"))
                == key
            )
            if dup_count > 1:
                flags.append("DUPLICATE_CLAIM")
                fraud_score += 0.3

            # Upcoding: ward=ICU but outcome not critical/improved? (rough)
            if (visit.get("ward") == "ICU") and (visit.get("outcome") == "recovered") and claimed_amount > high:
                flags.append("UPCODING_SUSPECT")
                fraud_score += 0.25

            # Provider risk boost
            hid = (claim.get("provider_ref") or {}).get("hospital_id")
            if hid and provider_risk.get(hid, 0.0) > 0.6:
                flags.append("HIGH_RISK_PROVIDER")
                fraud_score += 0.2

            # Self-claim stricter evidence match: compare claimed vs official billing
            official = int((claim.get("official_billing") or {}).get("total_billed") or 0)
            if claim_mode == "SELF" and official > 0:
                mismatch = abs(claimed_amount - official) / max(1, official)
                if mismatch > 0.2:
                    flags.append("SELF_DOC_MISMATCH")
                    fraud_score += 0.25

            # Hospital claim strictness: inflation vs official
            if claim_mode == "HOSPITAL" and official > 0:
                inflate = (claimed_amount - official) / max(1, official)
                if inflate > 0.15:
                    flags.append("HOSPITAL_INFLATION")
                    fraud_score += 0.25

            fraud_score = max(0.0, min(1.0, fraud_score))

            # (8) Decision
            if fraud_score >= 0.75:
                decision_status = "MANUAL_REVIEW"
                approved_amount = 0
                reasons.append("High fraud score")
            else:
                if approved_amount <= 0:
                    decision_status = "REJECTED"
                    reasons.append("No payable amount after limits")
                elif approved_amount < claimed_amount:
                    decision_status = "PARTIAL_APPROVED"
                else:
                    decision_status = "APPROVED"

        # Persist decision
        decision = {
            "decision_id": _new_id("DEC", 8),
            "claim_id": claim.get("claim_id"),
            "patient_id": patient_id,
            "status": decision_status,
            "claimed_amount": claimed_amount,
            "approved_amount": int(approved_amount),
            "reasons": reasons,
            "flags": flags,
            "fraud_score": round(float(fraud_score), 3),
            "decided_at": datetime.now().isoformat(timespec="seconds"),
        }
        decisions.append(decision)

        fraud_audit.append(
            {
                "claim_id": claim.get("claim_id"),
                "provider_ref": claim.get("provider_ref"),
                "claim_mode": claim_mode,
                "flags": flags,
                "fraud_score": round(float(fraud_score), 3),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

        claim["status"] = "ADJUDICATED"
        claim["last_decision_status"] = decision_status

        # Update policy sum insured used on approvals
        if policy and decision_status in {"APPROVED", "PARTIAL_APPROVED"}:
            policy["sum_insured_used"] = int(policy.get("sum_insured_used", 0)) + int(approved_amount)

    _atomic_write_json(paths["claims"], claims, indent=4)
    _atomic_write_json(paths["policies"], policies, indent=4)
    _atomic_write_json(paths["decisions"], decisions, indent=4)
    _atomic_write_json(paths["fraud_audit"], fraud_audit, indent=4)

    return {
        "claims": paths["claims"],
        "policies": paths["policies"],
        "decisions": paths["decisions"],
        "fraud_audit": paths["fraud_audit"],
    }
