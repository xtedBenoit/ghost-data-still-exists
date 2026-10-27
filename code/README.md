# Ghost Data Still Exists: AI Deletion-Audit Agent
**HackerRank Orchestrate — October 2026**

## 1. Overview & Architecture

When Northstar Shop customers request deletion under GDPR, CCPA, or internal privacy policies, downstream systems, secondary replicas, analytics exports, and automated synchronization jobs can leave behind "ghost data" or silently recreate purged records.

This solution provides a **hybrid deterministic-LLM audit agent**:
- **80% Deterministic Core**: Ingests structured database snapshots, system activity logs, identity audit history, and service exports into a unified temporal `FactsStore`.
- **Targeted Multimodal / LLM Intelligence**: Applies zero-shot intent boundary classification on multilingual requests (`IntentClassifier`) and pre-indexes unstructured visual documents/screenshots.
- **Temporal State Reconstruction**: Accurately computes ground-truth system states as of each case's exact `audit_at` cutoff timestamp, treating reported status claims as allegations requiring proof.
- **Canonical Steps Planner**: Synthesizes ordered remediation plans and verification checks complying strictly with `deletion_rules.csv`.

```
                    ┌───────────────────────────────┐
                    │  deletion_requests.csv (518)  │
                    └───────────────┬───────────────┘
                                    │
                         [Intent Classification]
                                    │
                                    ├── Non-Deletion ────────> NOT_APPLICABLE (steps: [])
                                    ▼
                         [Identity Resolution]
                                    │
                 (Current + Historical Emails, Hashes, Phones)
                                    │
                                    ▼
                         [Evidence Ingestion]
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
  SQL Snapshots /             Logs & Telemetry          JSON Bundles &
  SQLite In-Memory            Regex & Traces            Service Exports
         └──────────────────────────┬──────────────────────────┘
                                    ▼
                         [Temporal Facts Store]
                                    │
                         [State Reconstruction]
                      (Snapshot at audit_at cutoff)
                                    │
                                    ▼
                         [Policy Rules Engine]
                          (deletion_rules.csv)
                                    │
                                    ▼
                     [Canonical Steps Generator]
              (FINDING -> REMEDIATION -> VERIFICATION)
                                    │
                                    ▼
                         [Schema Validation]
                                    │
                                    ▼
                             output.csv
```

---

## 2. Directory Structure

```text
code/
├── main.py                     # Primary CLI execution pipeline
├── README.md                   # Solution documentation and run instructions
├── config/
│   ├── image_facts.json        # Extracted facts from image evidence (11 PNGs)
│   └── pdf_facts.json          # Extracted facts from document evidence (4 PDFs)
├── evaluation/
│   ├── evaluate.py             # Accuracy evaluation script
│   ├── main.py                 # Evaluation runner across sample and extra cases
│   ├── evaluation_report.md    # Full case, step, and field accuracy report
│   ├── usage_report.md         # Final full-dataset LLM token and cost report
│   └── extra_cases/
│       ├── extra_deletion_requests.csv # 3 participant-created synthetic test cases
│       ├── extra_expected_output.csv   # Expected ground-truth for extra cases
│       ├── extra_predicted_output.csv  # Predictions on extra cases
│       └── run_extra.py                # Runner for extra evaluation cases
└── src/
    ├── evidence/               # FactsStore and Fact dataclass
    ├── identity/               # Multi-identifier resolution (resolver.py)
    ├── intent/                 # Multilingual intent boundary classifier (classifier.py)
    ├── llm/                    # Token and cost tracking (tracker.py)
    ├── loaders/                # CSV, SQL, JSON, Log, and Static loaders
    ├── planner/                # Canonical steps builder and sorter (steps_builder.py)
    ├── rules/                  # Policy mapping for deletion_rules.csv
    ├── state/                  # Temporal state reconstructor (reconstructor.py)
    └── validator/              # Contract schema and syntax validator (schema.py)
```

---

## 3. Setup & Installation

### Requirements
- Python 3.9+ (tested on Python 3.11, 3.12, 3.14)
- Standard library dependencies (`sqlite3`, `csv`, `json`, `hashlib`, `re`, `argparse`, `pathlib`)
- No proprietary external binary dependencies required.

---

## 4. How to Run

### Run Full Evaluation Dataset (Generates Root `output.csv`)
From the repository root:
```bash
python code/main.py
```
This reads `dataset/deletion_requests.csv` (518 cases) and produces the required `output.csv` at the repository root.

### Run on Public Sample Dataset (32 cases)
```bash
python code/main.py --sample
```
Outputs predictions to `sample_predicted_output.csv` and validates against the contract schema.

### Custom Input and Output Paths
```bash
python code/main.py --dataset-dir dataset --input path/to/requests.csv --output path/to/output.csv
```

---

## 5. Running the Evaluation Workflow

Run the complete evaluation suite across both the 32 sample cases and the participant extra cases:
```bash
python code/evaluation/main.py
```

To run extra evaluation cases independently:
```bash
python code/evaluation/extra_cases/run_extra.py
```

### Key Evaluation Results
- **Status Accuracy**: **100.00%** on public sample cases (32/32) and extra test cases (3/3).
- **Critical Safety Precision**: **100.0%** on `BLOCK_RESTORE`, `DISABLE_DATA_FLOW`, `DELETE_RECORD`, and `REPORT_RESTORE_RISK`.
- **Field-Level Accuracy**: **93.98%** on `phase`, **96.39%** on `evidence_id`, **84.94%** on `state`.

---

## 6. Token Usage & Cost Summary

As detailed in `evaluation/usage_report.md`:
- **Total Requests Evaluated**: 518
- **Model**: `gemini-3.8-flash`
- **Total Tokens Consumed**: 46,300 tokens
- **Estimated Total Cost**: **$0.0087 USD** (< $0.01 for the entire 518-case audit)
- **Average Cost Per Request**: $0.000017 USD
