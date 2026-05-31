import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from vitals_generator import generate_vitals_for_patient_stay, list_patient_stays
from provider_enrichment import run_provider_enrichment
from insurance_engine import (
    adjudicate_claims,
    file_claim,
    generate_policies_for_dataset,
)

# NOTE:
# This file can do two things:
#   1) Generate a brand-new synthetic hospital dataset (and reference JSON files)
#   2) Append new historical events to *existing* patients inside x/patient_dataset.json
#
# The file paths are resolved relative to this script's folder (x/),
# so running `python x/main.py` from anywhere behaves consistently.

BASE_DIR = Path(__file__).resolve().parent

DATA_FILE = BASE_DIR / "patient_dataset.json"
DISEASES_FILE = BASE_DIR / "disease_knowledge_base.json"
MEDICINES_FILE = BASE_DIR / "medicine_catalog.json"
LAB_TESTS_FILE = BASE_DIR / "lab_test_reference.json"
DRUG_INTERACTIONS_FILE = BASE_DIR / "drug_interactions.json"

# ------------------------------------------------
# PATIENT NAME POOLS (~100+)
# ------------------------------------------------

FIRST_NAMES=[
"Rajesh","Amit","Arjun","Karan","Rohit","Vikram","Deepak","Ankit","Rahul","Suresh",
"Mahesh","Pankaj","Nitin","Ajay","Vijay","Sanjay","Sunil","Manish","Rakesh","Naresh",
"Anil","Kapil","Harish","Dinesh","Tarun","Lokesh","Naveen","Prakash","Ravi","Gaurav",
"Abhishek","Aditya","Akash","Alok","Ashish","Atul","Bharat","Chandan","Devendra","Gopal",
"Hemant","Jitendra","Kishore","Lalit","Mohan","Mukesh","Narendra","Omkar","Pradeep",
"Rajiv","Sachin","Sameer","Sandeep","Satish","Shivam","Subhash","Sudhir","Suman",
"Tushar","Umesh","Varun","Yogesh","Zakir","Arvind","Bhavesh","Chirag","Darshan",
"Eshan","Farhan","Ganesh","Hitesh","Ishwar","Jagdish","Kartik","Mahavir","Nakul",
"Ojas","Pritam","Ranjit","Shankar","Tanmay","Utkarsh","Vikas","Wasim","Yash",
"Zuber","Param"
]

LAST_NAMES=[
"Singh","Kumar","Sharma","Gupta","Verma","Yadav","Patel","Reddy","Nair","Iyer",
"Choudhary","Bansal","Agarwal","Malhotra","Khanna","Kapoor","Mehta","Joshi",
"Saxena","Srivastava","Pandey","Tripathi","Dwivedi","Tiwari","Chatterjee",
"Banerjee","Mukherjee","Das","Ghosh","Bose","Saha","Pillai","Menon","Shetty",
"Naidu","Rao","Murthy","Khan","Ansari","Qureshi","Ali","Pathan","Mirza",
"Shaikh","Khatri","Sethi","Talwar","Bhat","Kaul","Gill","Sandhu","Dhillon",
"Sidhu","Brar","Randhawa","Ahuja","Arora"
]

# ------------------------------------------------
# DISEASE DATABASE (ICD-10)
# ------------------------------------------------

DISEASES={
"I10":{"name":"Hypertension","symptoms":["headache","dizziness"]},
"E11":{"name":"Type 2 Diabetes","symptoms":["fatigue","blurred vision"]},
"J18":{"name":"Pneumonia","symptoms":["cough","fever"]},
"J45":{"name":"Asthma","symptoms":["wheezing"]},
"K21":{"name":"GERD","symptoms":["acid reflux"]},
"M19":{"name":"Arthritis","symptoms":["joint pain"]},
"G43":{"name":"Migraine","symptoms":["headache"]},
"D64":{"name":"Anemia","symptoms":["fatigue"]},
"A90":{"name":"Dengue","symptoms":["fever","rash"]},
"B54":{"name":"Malaria","symptoms":["fever","chills"]},
"A01":{"name":"Typhoid","symptoms":["fever","abdominal pain"]},
"U07":{"name":"COVID","symptoms":["fever","cough"]},
"J32":{"name":"Sinusitis","symptoms":["facial pain"]},
"K35":{"name":"Appendicitis","symptoms":["abdominal pain"]},
"K80":{"name":"Gallstones","symptoms":["pain"]},
"L40":{"name":"Psoriasis","symptoms":["rash"]},
"E03":{"name":"Hypothyroidism","symptoms":["fatigue"]},
"E05":{"name":"Hyperthyroidism","symptoms":["weight loss"]},
"E66":{"name":"Obesity","symptoms":["weight gain"]},
"M81":{"name":"Osteoporosis","symptoms":["bone pain"]},
"H26":{"name":"Cataract","symptoms":["blurred vision"]},
"G40":{"name":"Epilepsy","symptoms":["seizures"]},
"A41":{"name":"Sepsis","symptoms":["fever"]},
"G03":{"name":"Meningitis","symptoms":["neck stiffness"]},
"K74":{"name":"Cirrhosis","symptoms":["fatigue"]},
"K58":{"name":"IBS","symptoms":["abdominal pain"]},
"K50":{"name":"Crohn Disease","symptoms":["diarrhea"]},
"N18":{"name":"Chronic Kidney Disease","symptoms":["fatigue"]},
"I21":{"name":"Heart Attack","symptoms":["chest pain"]},
"J20":{"name":"Bronchitis","symptoms":["cough"]},
"B34":{"name":"Viral Fever","symptoms":["fever"]},
"E78":{"name":"Hyperlipidemia","symptoms":["none"]},
"D50":{"name":"Iron Deficiency","symptoms":["fatigue"]},
"I50":{"name":"Heart Failure","symptoms":["breathlessness"]}
}

# ------------------------------------------------
# MEDICINE DATABASE (250)
# ------------------------------------------------

BASE_DRUGS=[
"Paracetamol","Ibuprofen","Amlodipine","Losartan","Metformin",
"Insulin","Azithromycin","Amoxicillin","Ceftriaxone","Levofloxacin",
"Prednisone","Salbutamol","Omeprazole","Pantoprazole","Atorvastatin"
]

MEDICINES=[random.choice(BASE_DRUGS)+"_"+str(i) for i in range(250)]

# ------------------------------------------------
# DRUG → DISEASE RELATIONSHIP
# ------------------------------------------------

DRUG_DATABASE={}

for drug in MEDICINES:

    DRUG_DATABASE[drug]={

        "drug_class":random.choice([
        "Antibiotic","Antiviral","Antidiabetic","Antihypertensive","Analgesic"
        ]),

        "treats":random.sample(list(DISEASES.keys()),3),

        "dose":random.choice(["5mg","10mg","50mg","500mg"])
    }

DISEASE_DRUG_MAP={}

for drug,data in DRUG_DATABASE.items():
    for disease in data["treats"]:
        DISEASE_DRUG_MAP.setdefault(disease,[]).append(drug)

# ------------------------------------------------
# LAB TESTS (150)
# ------------------------------------------------

LAB_TESTS={}
for i in range(150):
    LAB_TESTS[f"LAB_{i}"]={
    "name":f"Test_{i}",
    "range":[round(random.uniform(1,4),2),round(random.uniform(5,10),2)]
    }

# ------------------------------------------------
# DRUG INTERACTIONS
# ------------------------------------------------

DRUG_INTERACTIONS=[]


# ------------------------------------------------
# UTILITIES (load/save, safety)
# ------------------------------------------------


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: Path, obj: Any, *, indent: int = 4) -> None:
    """Write JSON safely: write to temp file then replace target."""
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


def _parse_date_yyyy_mm_dd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _format_date_yyyy_mm_dd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _build_disease_drug_map(drug_db: Dict[str, Any]) -> Dict[str, List[str]]:
    """Rebuild reverse index disease -> [drug,...] from a drug catalog."""
    disease_drug_map: Dict[str, List[str]] = {}
    for drug, data in drug_db.items():
        for disease in data.get("treats", []):
            disease_drug_map.setdefault(disease, []).append(drug)
    return disease_drug_map

for i in range(40):
    d1=random.choice(MEDICINES)
    d2=random.choice(MEDICINES)

    DRUG_INTERACTIONS.append({
    "drug1":d1,
    "drug2":d2,
    "severity":random.choice(["mild","moderate","severe"])
    })

# ------------------------------------------------
# PATIENT PROFILE
# ------------------------------------------------

def patient_profile():

    return{
    "patient_id":"P"+str(uuid.uuid4())[:8],
    "name":random.choice(FIRST_NAMES)+" "+random.choice(LAST_NAMES),
    "age":random.randint(18,80),
    "gender":random.choice(["Male","Female"]),
    "blood_group":random.choice(["A+","B+","O+","AB+"]),
    "address":random.choice(["Delhi","Mumbai","Pune","Hyderabad","Chennai"])
    }

# ------------------------------------------------
# LAB REPORT
# ------------------------------------------------

def lab_report():

    tests=random.sample(list(LAB_TESTS.keys()),3)

    report={}

    for t in tests:

        r=LAB_TESTS[t]["range"]

        report[t]=round(random.uniform(r[0],r[1]),2)

    return report

# ------------------------------------------------
# PRESCRIPTION (RELATION BASED)
# ------------------------------------------------

def generate_prescription(disease,event_id):

    drugs=DISEASE_DRUG_MAP.get(disease,[])

    if not drugs:
        return None

    drug=random.choice(drugs)

    return{

    "prescription_id":"RX"+str(random.randint(1000,9999)),
    "event_id":event_id,
    "medicine_name":drug,
    "drug_class":DRUG_DATABASE[drug]["drug_class"],
    "dosage":DRUG_DATABASE[drug]["dose"],
    "duration_days":random.choice([5,7,10])
    }

# ------------------------------------------------
# MEDICAL EVENT
# ------------------------------------------------

def medical_event(date):

    disease=random.choice(list(DISEASES.keys()))
    event_id="EVT"+str(random.randint(1000,9999))

    return{

    "event_id":event_id,
    "event_date":date.strftime("%Y-%m-%d"),
    "disease_code":disease,
    "disease":DISEASES[disease]["name"],
    "symptoms":DISEASES[disease]["symptoms"],
    "lab_report":lab_report(),
    "prescription":generate_prescription(disease,event_id),
    "doctor_notes":random.choice([
    "patient stable",
    "monitor vitals",
    "continue medication",
    "follow-up required"
    ])
    }

# ------------------------------------------------
# ADMISSION
# ------------------------------------------------

def admission(date):

    return{
    "admission_id":"ADM"+str(random.randint(1000,9999)),
    "admission_date":date.strftime("%Y-%m-%d"),
    "ward":random.choice(["general","ICU"])
    }

# ------------------------------------------------
# DISCHARGE
# ------------------------------------------------

def discharge(date):

    return{
    "discharge_date":date.strftime("%Y-%m-%d"),
    "outcome":random.choice(["recovered","improved","critical"])
    }

# ------------------------------------------------
# RELAPSE
# ------------------------------------------------

def relapse(disease):

    if random.random()<0.15:
        return{
        "relapse":True,
        "disease":DISEASES[disease]["name"]
        }

    return None

# ------------------------------------------------
# TIMELINE
# ------------------------------------------------

def patient_timeline():

    start=datetime(2023,1,1)+timedelta(days=random.randint(0,365))

    events=[]
    admissions=[]
    discharges=[]
    relapses=[]

    for i in range(random.randint(3,6)):

        date=start+timedelta(days=i*random.randint(10,30))

        e=medical_event(date)

        events.append(e)
        admissions.append(admission(date))
        discharges.append(discharge(date+timedelta(days=random.randint(2,6))))

        r=relapse(e["disease_code"])

        if r:
            relapses.append(r)

    return events,admissions,discharges,relapses

# ------------------------------------------------
# PATIENT RECORD
# ------------------------------------------------

def generate_patient():

    events,admissions,discharges,relapses=patient_timeline()

    return{
    "patient_profile":patient_profile(),
    "medical_events":events,
    "hospital_admissions":admissions,
    "hospital_discharges":discharges,
    "relapses":relapses
    }

# ------------------------------------------------
# DATASET GENERATION
# ------------------------------------------------

def generate_dataset(n):

    data=[generate_patient() for _ in range(n)]
    _atomic_write_json(DATA_FILE, data, indent=4)

# ------------------------------------------------
# EXPORT REFERENCE FILES
# ------------------------------------------------

def export_reference():

    _atomic_write_json(DISEASES_FILE, DISEASES, indent=4)
    _atomic_write_json(MEDICINES_FILE, DRUG_DATABASE, indent=4)
    _atomic_write_json(LAB_TESTS_FILE, LAB_TESTS, indent=4)
    _atomic_write_json(DRUG_INTERACTIONS_FILE, DRUG_INTERACTIONS, indent=4)


# ------------------------------------------------
# APPEND MODE (update existing patient_dataset.json)
# ------------------------------------------------


def load_references_from_disk() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Load existing reference JSON files from x/.

    Returns:
        diseases, drug_database, lab_tests, drug_interactions
    """
    diseases = _read_json(DISEASES_FILE)
    drug_database = _read_json(MEDICINES_FILE)
    lab_tests = _read_json(LAB_TESTS_FILE)
    drug_interactions = _read_json(DRUG_INTERACTIONS_FILE)
    return diseases, drug_database, lab_tests, drug_interactions


def lab_report_from_reference(lab_tests: Dict[str, Any]) -> Dict[str, float]:
    tests = random.sample(list(lab_tests.keys()), 3)
    report: Dict[str, float] = {}
    for t in tests:
        r = lab_tests[t]["range"]
        report[t] = round(random.uniform(r[0], r[1]), 2)
    return report


def generate_prescription_from_reference(
    disease: str,
    event_id: str,
    drug_database: Dict[str, Any],
    disease_drug_map: Dict[str, List[str]],
) -> Optional[Dict[str, Any]]:
    drugs = disease_drug_map.get(disease, [])
    if not drugs:
        return None
    drug = random.choice(drugs)
    return {
        "prescription_id": "RX" + str(random.randint(1000, 9999)),
        "event_id": event_id,
        "medicine_name": drug,
        "drug_class": drug_database[drug]["drug_class"],
        "dosage": drug_database[drug]["dose"],
        "duration_days": random.choice([5, 7, 10]),
    }


def medical_event_from_reference(
    date: datetime,
    diseases: Dict[str, Any],
    lab_tests: Dict[str, Any],
    drug_database: Dict[str, Any],
    disease_drug_map: Dict[str, List[str]],
) -> Dict[str, Any]:
    disease_code = random.choice(list(diseases.keys()))
    event_id = "EVT" + str(random.randint(1000, 9999))
    return {
        "event_id": event_id,
        "event_date": _format_date_yyyy_mm_dd(date),
        "disease_code": disease_code,
        "disease": diseases[disease_code]["name"],
        "symptoms": diseases[disease_code]["symptoms"],
        "lab_report": lab_report_from_reference(lab_tests),
        "prescription": generate_prescription_from_reference(
            disease_code, event_id, drug_database, disease_drug_map
        ),
        "doctor_notes": random.choice(
            [
                "patient stable",
                "monitor vitals",
                "continue medication",
                "follow-up required",
            ]
        ),
    }


def admission_record(date: datetime) -> Dict[str, Any]:
    return {
        "admission_id": "ADM" + str(random.randint(1000, 9999)),
        "admission_date": _format_date_yyyy_mm_dd(date),
        "ward": random.choice(["general", "ICU"]),
    }


def discharge_record(date: datetime) -> Dict[str, Any]:
    return {
        "discharge_date": _format_date_yyyy_mm_dd(date),
        "outcome": random.choice(["recovered", "improved", "critical"]),
    }


def relapse_record(disease_code: str, diseases: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if random.random() < 0.15:
        return {"relapse": True, "disease": diseases[disease_code]["name"]}
    return None


def append_events_to_patient(
    patient: Dict[str, Any],
    *,
    k_events: int,
    diseases: Dict[str, Any],
    lab_tests: Dict[str, Any],
    drug_database: Dict[str, Any],
    disease_drug_map: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Mutates patient in-place by appending k new events sequentially."""
    events: List[Dict[str, Any]] = patient.get("medical_events", [])
    admissions: List[Dict[str, Any]] = patient.get("hospital_admissions", [])
    discharges: List[Dict[str, Any]] = patient.get("hospital_discharges", [])
    relapses: List[Dict[str, Any]] = patient.get("relapses", [])

    if events:
        last_date = _parse_date_yyyy_mm_dd(events[-1]["event_date"])
    else:
        # If a malformed record has no events, start "today" (or could start in 2023).
        last_date = datetime.now()

    for _ in range(k_events):
        # Maintain sequential future dates.
        gap_days = random.randint(10, 30)
        new_date = last_date + timedelta(days=gap_days)

        new_event = medical_event_from_reference(
            new_date, diseases, lab_tests, drug_database, disease_drug_map
        )
        events.append(new_event)
        admissions.append(admission_record(new_date))
        discharges.append(discharge_record(new_date + timedelta(days=random.randint(2, 6))))

        r = relapse_record(new_event["disease_code"], diseases)
        if r:
            relapses.append(r)

        last_date = new_date

    patient["medical_events"] = events
    patient["hospital_admissions"] = admissions
    patient["hospital_discharges"] = discharges
    patient["relapses"] = relapses

    return patient


def append_mode_random_patients(
    *,
    n_range: Tuple[int, int] = (5, 15),
    k_range: Tuple[int, int] = (1, 3),
    create_backup: bool = True,
) -> None:
    """Append events to N random patients, with N and K selected randomly."""
    if not DATA_FILE.exists():
        print(f"ERROR: Dataset not found at {DATA_FILE}. Generate it first from the menu.")
        return

    diseases, drug_db, lab_tests, _drug_interactions = load_references_from_disk()
    disease_drug_map = _build_disease_drug_map(drug_db)

    dataset: List[Dict[str, Any]] = _read_json(DATA_FILE)
    if not dataset:
        print("ERROR: Dataset is empty.")
        return

    # Random N and K
    n_patients = random.randint(n_range[0], n_range[1])
    n_patients = min(n_patients, len(dataset))
    k_events = random.randint(k_range[0], k_range[1])

    chosen_indices = random.sample(range(len(dataset)), n_patients)
    updated_patients_report: List[Dict[str, Any]] = []

    for idx in chosen_indices:
        patient = dataset[idx]
        profile = patient.get("patient_profile", {})
        pid = profile.get("patient_id")
        pname = profile.get("name")
        before_events = len(patient.get("medical_events", []))

        append_events_to_patient(
            patient,
            k_events=k_events,
            diseases=diseases,
            lab_tests=lab_tests,
            drug_database=drug_db,
            disease_drug_map=disease_drug_map,
        )
        after_events = len(patient.get("medical_events", []))

        updated_patients_report.append(
            {
                "patient_id": pid,
                "name": pname,
                "events_before": before_events,
                "events_after": after_events,
                "appended_events": k_events,
            }
        )

    # Save
    backup_path = _backup_file(DATA_FILE) if create_backup else None
    _atomic_write_json(DATA_FILE, dataset, indent=4)

    # Report
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = BASE_DIR / f"append_report_{ts}.json"
    report = {
        "mode": "random_patients",
        "dataset_file": str(DATA_FILE),
        "backup_file": str(backup_path) if backup_path else None,
        "chosen_N": n_patients,
        "chosen_K": k_events,
        "updated_patients": updated_patients_report,
    }
    _atomic_write_json(report_path, report, indent=4)

    print("\nAPPEND COMPLETE")
    print(f"  Chosen N (patients): {n_patients}")
    print(f"  Chosen K (events per patient): {k_events}")
    if backup_path:
        print(f"  Backup created: {backup_path.name}")
    print(f"  Report saved: {report_path.name}")
    print("  Updated patients:")
    for p in updated_patients_report:
        print(
            f"   - {p['patient_id']} | {p['name']} | {p['events_before']} -> {p['events_after']} events"
        )


def append_mode_specific_patients(
    patient_ids: List[str],
    *,
    k_range: Tuple[int, int] = (1, 3),
    create_backup: bool = True,
) -> None:
    """Append events to specific patient_ids, with K selected randomly."""
    if not DATA_FILE.exists():
        print(f"ERROR: Dataset not found at {DATA_FILE}. Generate it first from the menu.")
        return
    if not patient_ids:
        print("ERROR: No patient IDs provided.")
        return

    diseases, drug_db, lab_tests, _drug_interactions = load_references_from_disk()
    disease_drug_map = _build_disease_drug_map(drug_db)

    dataset: List[Dict[str, Any]] = _read_json(DATA_FILE)
    if not dataset:
        print("ERROR: Dataset is empty.")
        return

    k_events = random.randint(k_range[0], k_range[1])

    wanted = set(patient_ids)
    updated_patients_report: List[Dict[str, Any]] = []
    missing: List[str] = []

    for pid in patient_ids:
        found = False
        for patient in dataset:
            profile = patient.get("patient_profile", {})
            if profile.get("patient_id") == pid:
                found = True
                before_events = len(patient.get("medical_events", []))
                append_events_to_patient(
                    patient,
                    k_events=k_events,
                    diseases=diseases,
                    lab_tests=lab_tests,
                    drug_database=drug_db,
                    disease_drug_map=disease_drug_map,
                )
                after_events = len(patient.get("medical_events", []))
                updated_patients_report.append(
                    {
                        "patient_id": pid,
                        "name": profile.get("name"),
                        "events_before": before_events,
                        "events_after": after_events,
                        "appended_events": k_events,
                    }
                )
                break
        if not found:
            missing.append(pid)

    backup_path = _backup_file(DATA_FILE) if create_backup else None
    _atomic_write_json(DATA_FILE, dataset, indent=4)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = BASE_DIR / f"append_report_{ts}.json"
    report = {
        "mode": "specific_patient_ids",
        "dataset_file": str(DATA_FILE),
        "backup_file": str(backup_path) if backup_path else None,
        "chosen_K": k_events,
        "requested_patient_ids": patient_ids,
        "missing_patient_ids": missing,
        "updated_patients": updated_patients_report,
    }
    _atomic_write_json(report_path, report, indent=4)

    print("\nAPPEND COMPLETE")
    print(f"  Chosen K (events per patient): {k_events}")
    if backup_path:
        print(f"  Backup created: {backup_path.name}")
    print(f"  Report saved: {report_path.name}")
    if missing:
        print("  WARNING: Some patient IDs were not found:")
        for pid in missing:
            print(f"   - {pid}")
    print("  Updated patients:")
    for p in updated_patients_report:
        print(
            f"   - {p['patient_id']} | {p['name']} | {p['events_before']} -> {p['events_after']} events"
        )


# ------------------------------------------------
# MENU
# ------------------------------------------------


def _input_int(prompt: str, *, default: Optional[int] = None) -> int:
    while True:
        s = input(prompt).strip()
        if not s and default is not None:
            return default
        try:
            return int(s)
        except ValueError:
            print("Please enter a valid integer.")


def _confirm(prompt: str) -> bool:
    s = input(prompt + " (y/n): ").strip().lower()
    return s in {"y", "yes"}


def dataset_summary() -> None:
    if not DATA_FILE.exists():
        print(f"Dataset not found at {DATA_FILE}.")
        return
    dataset: List[Dict[str, Any]] = _read_json(DATA_FILE)
    print("\nDATASET SUMMARY")
    print(f"  File: {DATA_FILE}")
    print(f"  Patient count: {len(dataset)}")
    if not dataset:
        return

    sample = dataset[:5]
    print("  Sample patient IDs:")
    for p in sample:
        profile = p.get("patient_profile", {})
        print(f"   - {profile.get('patient_id')} | {profile.get('name')}")


def generate_fresh_dataset_flow() -> None:
    print("\nThis will export reference JSON files and generate a NEW patient_dataset.json")
    print(f"Target folder: {BASE_DIR}")

    n = _input_int("How many patients to generate? [default 100]: ", default=100)

    if DATA_FILE.exists():
        if not _confirm(f"{DATA_FILE.name} already exists. Overwrite?"):
            print("Cancelled.")
            return

    export_reference()
    generate_dataset(n)
    print("\nHospital-grade dataset generated successfully")
    print(f"  References: {DISEASES_FILE.name}, {MEDICINES_FILE.name}, {LAB_TESTS_FILE.name}, {DRUG_INTERACTIONS_FILE.name}")
    print(f"  Dataset: {DATA_FILE.name}")


def append_random_flow() -> None:
    print("\nAppend mode: random patients")
    print("  N and K will be chosen randomly.")
    print("  Default ranges: N=5..15 patients, K=1..3 events per patient")
    append_mode_random_patients(n_range=(5, 15), k_range=(1, 3), create_backup=True)


def append_specific_flow() -> None:
    print("\nAppend mode: specific patient IDs")
    print("Enter patient IDs separated by spaces (example: P92053f22 Pf184960d)")
    ids_line = input("Patient IDs: ").strip()
    patient_ids = [x for x in ids_line.split() if x]
    print("  K will be chosen randomly (default range: 1..3)")
    append_mode_specific_patients(patient_ids, k_range=(1, 3), create_backup=True)


def generate_vitals_flow() -> None:
    """Menu flow: generate real-time ICU vitals for a single chosen stay (1C)."""
    if not DATA_FILE.exists():
        print(f"Dataset not found at {DATA_FILE}. Generate it first.")
        return

    dataset: List[Dict[str, Any]] = _read_json(DATA_FILE)
    if not dataset:
        print("Dataset is empty.")
        return

    pid = input("Enter patient_id (example: P92053f22): ").strip()
    if not pid:
        print("Cancelled (no patient_id).")
        return

    patient: Optional[Dict[str, Any]] = None
    for p in dataset:
        if p.get("patient_profile", {}).get("patient_id") == pid:
            patient = p
            break

    if patient is None:
        print(f"patient_id not found: {pid}")
        return

    profile = patient.get("patient_profile", {})
    print(f"\nSelected patient: {profile.get('patient_id')} | {profile.get('name')} | age {profile.get('age')}")

    stays = list_patient_stays(patient)
    if not stays:
        print("This patient has no stays (events/admissions) to generate vitals for.")
        return

    print("\nAvailable stays:")
    for s in stays:
        i = s["stay_index"]
        ev = s["event"]
        adm = s["admission"]
        dis = s["discharge"]
        print(
            f"  [{i}] {ev.get('event_date')} | {ev.get('disease_code')} {ev.get('disease')}"
            f" | ward={adm.get('ward')} | outcome={dis.get('outcome')}"
        )

    idx = _input_int("\nChoose stay index: ")

    # extra warning if ward not ICU
    chosen = next((s for s in stays if s["stay_index"] == idx), None)
    if chosen is None:
        print("Invalid stay index.")
        return
    ward = (chosen.get("admission", {}) or {}).get("ward")
    if ward != "ICU":
        print(f"WARNING: Selected ward is '{ward}', not ICU.")
        if not _confirm("Continue anyway?"):
            print("Cancelled.")
            return

    samples = _input_int("How many real-time samples? [default 30]: ", default=30)
    delay_str = input("Delay (seconds) between samples? [default 1]: ").strip()
    delay = 1.0
    if delay_str:
        try:
            delay = float(delay_str)
        except ValueError:
            print("Invalid delay; using default 1 second.")
            delay = 1.0

    print("\nStarting real-time vitals generation...")
    try:
        out_path = generate_vitals_for_patient_stay(
            base_dir=BASE_DIR,
            dataset_path=DATA_FILE,
            patient_id=pid,
            stay_index=idx,
            samples=samples,
            delay_seconds=delay,
            print_stream=True,
        )
    except Exception as e:
        print(f"ERROR generating vitals: {e}")
        return

    print("\nVITALS JSON GENERATED")
    print(f"  File: {out_path}")


def main_menu() -> None:
    while True:
        print("\n==============================")
        print(" Hospital Dataset Manager (x)")
        print("==============================")
        print("1) Generate fresh dataset")
        print("2) Append new events (random patients; random N & K)")
        print("3) Append new events (specific patient IDs; random K)")
        print("4) Show dataset summary")
        print("5) Generate ICU vitals JSON (real-time) for ONE patient stay")
        print("6) Generate doctors + hospitals, enrich patient history (in-place)")
        print("7) Insurance Claim System")
        print("8) Exit")

        choice = input("\nChoose an option [1-8]: ").strip()

        if choice == "1":
            generate_fresh_dataset_flow()
        elif choice == "2":
            append_random_flow()
        elif choice == "3":
            append_specific_flow()
        elif choice == "4":
            dataset_summary()
        elif choice == "5":
            generate_vitals_flow()
        elif choice == "6":
            print("\nThis will modify x/patient_dataset.json in-place and create a backup.")
            if not _confirm("Continue?"):
                print("Cancelled.")
                continue
            try:
                out = run_provider_enrichment(
                    base_dir=BASE_DIR,
                    dataset_path=DATA_FILE,
                    doctors_count=50,
                    hospitals_count=20,
                    create_backup=True,
                )
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            print("\nPROVIDER ENRICHMENT COMPLETE")
            if "backup" in out:
                print(f"  Backup: {out['backup'].name}")
            print(f"  Updated dataset: {out['dataset'].name}")
            print(f"  Doctors file: {out['doctors'].name}")
            print(f"  Hospitals file: {out['hospitals'].name}")
            print(f"  Doctor->patient index: {out['doctor_patient_index'].name}")
        elif choice == "7":
            insurance_menu()
        elif choice == "8":
            print("Goodbye.")
            return
        else:
            print("Invalid choice. Please select 1-8.")


def insurance_menu() -> None:
    """Insurance Claim System sub-menu."""
    while True:
        print("\n--------------------------------")
        print(" Insurance Claim System")
        print("--------------------------------")
        print("1) Generate policies + premium history")
        print("2) File a claim")
        print("3) Adjudicate pending claims")
        print("4) Back")

        c = input("\nChoose an option [1-4]: ").strip()

        if c == "1":
            try:
                out = generate_policies_for_dataset(
                    base_dir=BASE_DIR,
                    patient_dataset_path=DATA_FILE,
                    hospitals_path=BASE_DIR / "hospitals.json",
                    doctors_path=BASE_DIR / "doctors.json",
                )
            except Exception as e:
                print(f"ERROR generating policies: {e}")
                continue
            print("\nPOLICIES GENERATED")
            print(f"  File: {out}")

        elif c == "2":
            pid = input("Enter patient_id: ").strip()
            idx = _input_int("Enter stay_index: ")
            mode = input("Claim mode (HOSPITAL/SELF): ").strip().upper() or "SELF"
            if mode not in {"HOSPITAL", "SELF"}:
                print("Invalid claim mode. Use HOSPITAL or SELF.")
                continue
            try:
                out = file_claim(
                    base_dir=BASE_DIR,
                    patient_dataset_path=DATA_FILE,
                    patient_id=pid,
                    stay_index=idx,
                    claim_mode=mode,
                )
            except Exception as e:
                print(f"ERROR filing claim: {e}")
                continue
            print("\nCLAIM FILED")
            print(f"  Claims file: {out}")

        elif c == "3":
            try:
                out = adjudicate_claims(
                    base_dir=BASE_DIR,
                    patient_dataset_path=DATA_FILE,
                )
            except Exception as e:
                print(f"ERROR adjudicating claims: {e}")
                continue
            print("\nADJUDICATION COMPLETE")
            print(f"  Policies: {out['policies'].name}")
            print(f"  Claims: {out['claims'].name}")
            print(f"  Decisions: {out['decisions'].name}")
            print(f"  Fraud audit: {out['fraud_audit'].name}")

        elif c == "4":
            return
        else:
            print("Invalid choice. Please select 1-4.")

# ------------------------------------------------
# RUN
# ------------------------------------------------

if __name__=="__main__":

    main_menu()