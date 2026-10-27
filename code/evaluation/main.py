"""
Main Evaluation Entrypoint
Runs complete evaluation across sample dataset and extra participant-created cases.
"""

import os
import sys
from pathlib import Path

# Add code directory to path
CODE_DIR = Path(__file__).resolve().parent.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from evaluation.evaluate import Evaluator


def run_evaluation():
    repo_root = CODE_DIR.parent
    sample_expected = repo_root / "dataset" / "sample_output.csv"
    sample_predicted = repo_root / "sample_predicted_output.csv"

    print("=" * 60)
    print("Evaluating Public Sample Cases (32 requests)")
    print("=" * 60)
    if sample_predicted.exists() and sample_expected.exists():
        evaluator = Evaluator(str(sample_expected), str(sample_predicted))
        report = evaluator.generate_markdown_report("Sample Cases Evaluation")
        print(report)
    else:
        print("Sample output files not found. Run 'python code/main.py --sample' first.")

    extra_expected = CODE_DIR / "evaluation" / "extra_cases" / "extra_expected_output.csv"
    extra_predicted = CODE_DIR / "evaluation" / "extra_cases" / "extra_predicted_output.csv"
    if extra_expected.exists() and extra_predicted.exists():
        print("\n" + "=" * 60)
        print("Evaluating Participant Extra Cases")
        print("=" * 60)
        evaluator_extra = Evaluator(str(extra_expected), str(extra_predicted))
        print(evaluator_extra.generate_markdown_report("Extra Cases Evaluation"))


if __name__ == "__main__":
    run_evaluation()
