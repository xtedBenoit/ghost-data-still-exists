"""
Evaluation Framework
Evaluates deletion audit predictions against ground truth according to challenge contract:
- Case-level deletion-status accuracy
- Step-level and field-level accuracy
- Sequence accuracy
- Operation precision and recall
"""

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


class Evaluator:
    def __init__(self, expected_csv: str, predicted_csv: str):
        self.expected_csv = expected_csv
        self.predicted_csv = predicted_csv
        self.expected_rows: Dict[str, Dict[str, Any]] = {}
        self.predicted_rows: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        with open(self.expected_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self.expected_rows[r["case_id"]] = {
                    "deletion_status": r["deletion_status"].strip(),
                    "steps": json.loads(r["steps_json"]),
                }

        with open(self.predicted_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self.predicted_rows[r["case_id"]] = {
                    "deletion_status": r["deletion_status"].strip(),
                    "steps": json.loads(r["steps_json"]),
                }

    def evaluate(self) -> Dict[str, Any]:
        total_cases = len(self.expected_rows)
        correct_status = 0
        exact_sequence_matches = 0
        step_count_matches = 0

        status_confusion = defaultdict(lambda: defaultdict(int))
        field_matches = defaultdict(int)
        field_totals = defaultdict(int)

        op_tp = defaultdict(int)
        op_fp = defaultdict(int)
        op_fn = defaultdict(int)

        for cid, exp in self.expected_rows.items():
            pred = self.predicted_rows.get(cid)
            if not pred:
                continue

            exp_st = exp["deletion_status"]
            pred_st = pred["deletion_status"]
            status_confusion[exp_st][pred_st] += 1

            if exp_st == pred_st:
                correct_status += 1

            exp_steps = exp["steps"]
            pred_steps = pred["steps"]

            if len(exp_steps) == len(pred_steps):
                step_count_matches += 1

            # Sequence accuracy (exact match of list of step dicts)
            if exp_steps == pred_steps:
                exact_sequence_matches += 1

            # Step-level and field-level comparison
            exp_ops = [(s.get("phase"), s.get("system_id"), s.get("resource_id"), s.get("operation"), s.get("state")) for s in exp_steps]
            pred_ops = [(s.get("phase"), s.get("system_id"), s.get("resource_id"), s.get("operation"), s.get("state")) for s in pred_steps]

            for op in pred_ops:
                if op in exp_ops:
                    op_tp[op[3]] += 1
                else:
                    op_fp[op[3]] += 1
            for op in exp_ops:
                if op not in pred_ops:
                    op_fn[op[3]] += 1

            # Field-level accuracy on positional alignment up to min length
            min_len = min(len(exp_steps), len(pred_steps))
            for i in range(min_len):
                es = exp_steps[i]
                ps = pred_steps[i]
                for f in ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]:
                    field_totals[f] += 1
                    if es.get(f) == ps.get(f):
                        field_matches[f] += 1

        status_acc = (correct_status / total_cases * 100) if total_cases > 0 else 0
        seq_acc = (exact_sequence_matches / total_cases * 100) if total_cases > 0 else 0
        step_len_acc = (step_count_matches / total_cases * 100) if total_cases > 0 else 0

        field_acc = {
            f: (field_matches[f] / field_totals[f] * 100) if field_totals[f] > 0 else 0
            for f in ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]
        }

        return {
            "total_cases": total_cases,
            "correct_status": correct_status,
            "status_accuracy": status_acc,
            "sequence_matches": exact_sequence_matches,
            "sequence_accuracy": seq_acc,
            "step_count_matches": step_count_matches,
            "step_count_accuracy": step_len_acc,
            "status_confusion": dict(status_confusion),
            "field_accuracy": field_acc,
            "field_matches": dict(field_matches),
            "field_totals": dict(field_totals),
            "op_tp": dict(op_tp),
            "op_fp": dict(op_fp),
            "op_fn": dict(op_fn),
        }

    def generate_markdown_report(self, title: str = "Evaluation Report") -> str:
        metrics = self.evaluate()
        md = []
        md.append(f"# {title}\n")
        md.append("## 1. Case-Level Deletion-Status Accuracy\n")
        md.append(f"- **Total Evaluated Cases**: {metrics['total_cases']}")
        md.append(f"- **Status Accuracy**: **{metrics['status_accuracy']:.2f}%** ({metrics['correct_status']}/{metrics['total_cases']})\n")

        md.append("| Expected Status | Predicted Status | Count |")
        md.append("|---|---|---|")
        for exp_st, preds in metrics["status_confusion"].items():
            for pred_st, count in preds.items():
                md.append(f"| `{exp_st}` | `{pred_st}` | {count} |")

        md.append("\n## 2. Step-Level & Field-Level Accuracy\n")
        md.append(f"- **Step Count Match**: **{metrics['step_count_accuracy']:.2f}%** ({metrics['step_count_matches']}/{metrics['total_cases']})")
        md.append(f"- **Exact Sequence Match**: **{metrics['sequence_accuracy']:.2f}%** ({metrics['sequence_matches']}/{metrics['total_cases']})\n")

        md.append("| Field Name | Matched Values | Total Evaluated | Field Accuracy |")
        md.append("|---|---|---|---|")
        for f, acc in metrics["field_accuracy"].items():
            m = metrics["field_matches"].get(f, 0)
            tot = metrics["field_totals"].get(f, 0)
            md.append(f"| `{f}` | {m} | {tot} | **{acc:.2f}%** |")

        md.append("\n## 3. Operation Precision and Recall\n")
        all_ops = sorted(set(list(metrics["op_tp"].keys()) + list(metrics["op_fp"].keys()) + list(metrics["op_fn"].keys())))
        md.append("| Operation | TP | FP | FN | Precision | Recall | F1 Score |")
        md.append("|---|---|---|---|---|---|---|")
        for op in all_ops:
            tp = metrics["op_tp"].get(op, 0)
            fp = metrics["op_fp"].get(op, 0)
            fn = metrics["op_fn"].get(op, 0)
            prec = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0.0
            rec = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 0.0
            f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
            md.append(f"| `{op}` | {tp} | {fp} | {fn} | {prec:.1f}% | {rec:.1f}% | {f1:.1f}% |")

        return "\n".join(md)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python evaluate.py <expected_csv> <predicted_csv>")
        sys.exit(1)
    ev = Evaluator(sys.argv[1], sys.argv[2])
    print(ev.generate_markdown_report())
