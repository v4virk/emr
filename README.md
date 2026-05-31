# Electronic Medical Records Insurance App

A cleaned Flask + React healthcare insurance simulation app. It supports patient and doctor login flows, JSON-backed electronic medical records, bill uploads, claim filing, on-demand vitals generation, optional Kafka/Spark vitals streaming, and rule-based insurance adjudication.

## Project Highlights

- Full-stack EMR and insurance workflow with separate patient and doctor dashboards.
- Modular Flask backend organized into presentation, service/object, and model layers.
- React + Vite frontend with dashboards for claims, bills, providers, analytics, and vitals.
- JSON seed dataset for patients, hospitals, doctors, medicines, lab references, and policies.
- SQLite runtime database for users, uploaded bills, assignments, requests, and submitted claims.
- Dynamic vitals generation from patient stay metadata, with optional Kafka event publishing and Spark-based aggregation.
- Rule-based claim evaluation and a deeper synthetic insurance adjudication engine.

## System Architecture

```text
                         +-----------------------------+
                         |       React + Vite UI       |
                         |  Patient / Doctor Dashboard |
                         +--------------+--------------+
                                        |
                                        | REST API
                                        v
                         +-----------------------------+
                         |        Flask API Layer      |
                         | emr_app/presentation/api.py |
                         +--------------+--------------+
                                        |
        +-------------------------------+--------------------------------+
        |                               |                                |
        v                               v                                v
+---------------+              +----------------+              +------------------+
| Auth/Profile  |              | Claims & Bills |              | Vitals Pipeline  |
| Services      |              | Services       |              | Kafka/Spark Hook |
+-------+-------+              +-------+--------+              +--------+---------+
        |                              |                                |
        v                              v                                v
+----------------+            +----------------+              +------------------+
| SQLite Runtime |            | JSON Seed Data |              | Vitals JSON      |
| instance/app.db|            | data/*.json    |              | data/vitals_*.json|
+----------------+            +----------------+              +------------------+
                                        |
                                        v
                         +-----------------------------+
                         | Optional Insurance Engine   |
                         | Policies / Decisions / Audit|
                         +-----------------------------+
```

Optional streaming path:

```text
Dashboard vitals request
        |
        v
Flask API -> Vitals Pipeline -> Kafka request topic -> Vitals worker
        |              |                              |
        |              v                              v
        |        Local generator              Kafka result topic
        |              |
        v              v
Immediate UI response + Spark/local summary
```

The dashboard does not require Kafka or Spark to run. Kafka/Spark are optional extensions: Kafka records vitals jobs/results as events, and Spark can summarize generated readings. If they are disabled, the app still generates vitals locally and returns them immediately.

## Architecture Design

| Layer | Folder | Responsibility |
| --- | --- | --- |
| Presentation | `emr_app/presentation/` | HTTP routes, request parsing, response formatting |
| Service/Object | `emr_app/objects/` | Business workflows: auth, claims, vitals, datasets, providers, insurance adjudication |
| Model/Persistence | `emr_app/models/` | SQLite connection, schema creation, persistent runtime state |
| Configuration | `emr_app/config.py` | Central paths and Kafka/Spark environment settings |
| Static Data | `data/` | Seed EMR records, reference data, doctors, hospitals, policies |
| Client | `frontend/` | User-facing patient and doctor dashboards |

Core backend modules:

- `auth_service.py` - registration/login helpers with bcrypt hashing.
- `data_manager.py` - combines SQLite records with JSON medical history.
- `claim_engine.py` - lightweight claim scoring using bill and care-history context.
- `insurance_engine.py` - advanced synthetic policy/claim adjudication.
- `dataset_generator.py` - initial dataset generation and enrichment menu.
- `provider_enrichment.py` - doctor/hospital generation and patient-provider mapping.
- `vitals_generator.py` - synthetic vital-sign stream generation.
- `vitals_pipeline.py` - on-demand dashboard vitals, Kafka events, and Spark/local summaries.

## Core Workflows

Patient flow:

```text
Patient login -> centralized profile -> medical history / bills -> claim submission
              -> claim engine reads SQLite bills + JSON care-history billing
              -> status, reason, and risk score are stored in SQLite
```

Doctor flow:

```text
Doctor login -> assigned patients -> patient details -> bill verification
             -> claim review / claim creation -> analytics and vitals dashboard
```

Vitals flow:

```text
Dashboard asks for vitals -> latest file is returned if present
                           -> otherwise a new stream is generated dynamically
                           -> optional Kafka request/result events are published
                           -> optional Spark summary is attached to the response
```

## Current Architecture

The project uses a POM-style layered structure:

- `emr_app/presentation/` - presentation/API layer. Contains Flask routes in `api.py`.
- `emr_app/objects/` - object/service layer. Contains auth, claims, data bridging, initial dataset generation, provider enrichment, vitals generation, Kafka/Spark vitals orchestration, and insurance adjudication.
- `emr_app/models/` - model/persistence layer. Contains SQLite connection and schema setup.
- `emr_app/utils/` - shared helpers.
- `emr_app/config.py` - centralized filesystem paths and Kafka/Spark settings.
- `data/` - seed JSON datasets and reference data.
- `frontend/` - React + Vite client.
- `tests/` - focused runnable tests.

The files that were in `subisdary files/` are now represented inside `emr_app/objects/`:

- `main.py` -> `emr_app/objects/dataset_generator.py`
- `provider_enrichment.py` -> `emr_app/objects/provider_enrichment.py`
- `insurance_engine.py` -> `emr_app/objects/insurance_engine.py`
- `vitals_generator.py` -> `emr_app/objects/vitals_generator.py`

Runtime/generated files are intentionally not committed:

- `instance/app.db`
- `instance/uploads/`
- `frontend/node_modules/`
- `frontend/dist/`
- generated `data/vitals_*.json`
- generated claim decision/audit files

## Project Layout

```text
electronic_medical_records/
  run.py
  main.py
  run_vitals_worker.py
  requirements.txt
  requirements-streaming.txt
  README.md
  .gitignore
  data/
    patient_dataset.json
    insurance_policies.json
    doctors.json
    hospitals.json
    doctor_patient_index.json
    disease_knowledge_base.json
    medicine_catalog.json
    lab_test_reference.json
    drug_interactions.json
  emr_app/
    config.py
    presentation/
      api.py
    objects/
      auth_service.py
      claim_engine.py
      data_manager.py
      dataset_generator.py
      insurance_engine.py
      provider_enrichment.py
      vitals_generator.py
      vitals_pipeline.py
    models/
      database.py
    utils/
      files.py
  frontend/
    src/
    package.json
    vite.config.js
  tests/
    test_dual_bill_sources.py
```

## Backend Setup

```bash
cd electronic_medical_records
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Backend API:

```text
http://127.0.0.1:5000/api
```

The SQLite database is created automatically at `instance/app.db` when the backend starts.

## Initial Dataset Tools

The old subsidiary `main.py` menu is available as:

```bash
cd electronic_medical_records
python main.py
```

Use it only when you intentionally want to regenerate or enrich seed data. It writes to `data/`.

## Frontend Setup

```bash
cd electronic_medical_records/frontend
npm install
npm run dev
```

Frontend app:

```text
http://localhost:5173
```

The frontend uses `VITE_API_BASE_URL` when provided. See `frontend/.env.example`.

## Dynamic Vitals Flow

Vitals are generated dynamically through the dashboard:

- Doctor dashboard calls `GET /api/doctor/patient/<patient_id>/vitals/latest`.
- If no vitals file exists, the backend automatically generates vitals for stay `0`.
- The "Generate / Refresh Vitals" button calls `POST /api/doctor/patient/<patient_id>/vitals/generate`.
- Patient vitals endpoints follow the same on-demand behavior.
- Generated vitals are saved as ignored `data/vitals_<patient_id>_<timestamp>.json` files.

The implementation lives in:

- `emr_app/objects/vitals_generator.py` - synthetic vitals generation.
- `emr_app/objects/vitals_pipeline.py` - dashboard-triggered generation, Kafka events, and Spark/local summaries.

By default the app works without Kafka or Spark. It generates vitals locally and attaches a local summary to the payload.

## Optional Kafka/Spark Vitals Pipeline

Install optional streaming dependencies:

```bash
cd electronic_medical_records
source .venv/bin/activate
pip install -r requirements-streaming.txt
```

Enable Kafka and Spark with environment variables:

```bash
export EMR_KAFKA_ENABLED=true
export EMR_KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export EMR_KAFKA_VITALS_REQUEST_TOPIC=emr.vitals.requests
export EMR_KAFKA_VITALS_RESULT_TOPIC=emr.vitals.results

export EMR_SPARK_ENABLED=true
export EMR_SPARK_APP_NAME="EMR Vitals Pipeline"
```

Run the backend:

```bash
python run.py
```

When Kafka is enabled, each dashboard vitals request publishes a request event and a result event. When Spark is enabled, vitals readings are summarized using a local Spark session; if Spark is disabled or unavailable, the backend falls back to local Python summary generation.

Optional Kafka worker:

```bash
python run_vitals_worker.py
```

Use the worker for external Kafka-produced vitals jobs. The dashboard API already generates vitals immediately so the UI gets a response without waiting for a separate consumer.

## Tests

The retained focused test lives in `tests/`.

```bash
cd electronic_medical_records
python3 tests/test_dual_bill_sources.py
```

Optional verification commands:

```bash
python3 -m compileall emr_app tests run.py main.py run_vitals_worker.py
cd frontend
npm run build
```

## Sample Login IDs

Patient IDs:

- `Pfabd4cd2`
- `P1a4531a3`
- `P33a53cdc`
- `P99a45bd2`
- `P90df29e4`

Doctor IDs:

- `D322b94`
- `D86d773`
- `D665ddf`
- `Dd5973a`
- `Decdec2`

## Important Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/patient/legacy-login` | Login with a sample patient ID |
| `POST` | `/api/auth/doctor/legacy-login` | Login with a sample doctor ID |
| `GET` | `/api/patient/<user_id>/centralized` | Get unified patient data |
| `POST` | `/api/patient/<user_id>/claims` | Submit a claim |
| `GET` | `/api/patient/<user_id>/claims` | List patient claims |
| `POST` | `/api/patient/<user_id>/bills` | Upload a bill |
| `GET` | `/api/patient/<user_id>/bills` | List uploaded bills |
| `GET` | `/api/doctor/patient/<patient_id>/vitals/latest` | Get or auto-generate latest doctor dashboard vitals |
| `POST` | `/api/doctor/patient/<patient_id>/vitals/generate` | Force-generate doctor dashboard vitals |
| `GET` | `/api/patient/<user_id>/vitals/latest` | Get or auto-generate patient dashboard vitals |
| `POST` | `/api/patient/<user_id>/vitals/generate` | Force-generate patient dashboard vitals |
| `GET` | `/api/backend/patients` | List seed patients |
| `GET` | `/api/backend/doctors` | List seed doctors |
| `POST` | `/api/backend/claims/file` | File a synthetic insurance-engine claim |
| `POST` | `/api/backend/claims/adjudicate` | Run insurance adjudication |

## Data Flow

- Static seed data lives in `data/*.json`.
- SQLite stores users, patient identities, uploaded bill metadata, doctor assignments, requests, and simple claims.
- `emr_app.objects.data_manager` combines SQLite records with JSON medical records.
- `emr_app.objects.claim_engine` evaluates simple patient/doctor claim submissions.
- `emr_app.objects.insurance_engine` handles the deeper synthetic adjudication workflow.
- `emr_app.objects.vitals_pipeline` handles dashboard-triggered vitals generation, optional Kafka events, and Spark/local summaries.
- Uploaded files are stored in `instance/uploads/`.

## Cleanup Notes

The old flat files such as `api.py`, `db.py`, `auth.py`, `claim_engine.py`, and `data_manager.py` were moved into `emr_app/`. The old `backend/` directory was replaced by `data/` for JSON data and `emr_app/objects/` for backend logic.
