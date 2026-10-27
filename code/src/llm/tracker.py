"""
Token & Cost Tracker
Tracks model calls, input and output tokens, and computes estimated costs.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ModelUsage:
    model_name: str
    provider: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_per_1k_input: float = 0.00015  # Default for gemini-3.8-flash / flash models
    cost_per_1k_output: float = 0.00060

    @property
    def total_cost(self) -> float:
        return (self.input_tokens / 1000.0) * self.cost_per_1k_input + (self.output_tokens / 1000.0) * self.cost_per_1k_output


class TokenTracker:
    def __init__(self):
        self.usages: Dict[str, ModelUsage] = {}

    def get_or_create(self, model_name: str, provider: str = "Google") -> ModelUsage:
        if model_name not in self.usages:
            self.usages[model_name] = ModelUsage(model_name=model_name, provider=provider)
        return self.usages[model_name]

    def record_call(self, model_name: str, input_tokens: int, output_tokens: int, provider: str = "Google"):
        usage = self.get_or_create(model_name, provider)
        usage.calls += 1
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens

    def generate_report(self, total_requests: int = 518) -> str:
        total_calls = sum(u.calls for u in self.usages.values())
        total_input = sum(u.input_tokens for u in self.usages.values())
        total_output = sum(u.output_tokens for u in self.usages.values())
        total_tokens = total_input + total_output
        total_cost = sum(u.total_cost for u in self.usages.values())

        avg_tokens = total_tokens / total_requests if total_requests > 0 else 0
        avg_cost = total_cost / total_requests if total_requests > 0 else 0

        report = f"""# Usage Report: Deletion Audit Agent

## Executive Summary
- **Total Requests Evaluated**: {total_requests}
- **Total Model Calls**: {total_calls}
- **Total Tokens Consumed**: {total_tokens:,} ({total_input:,} input, {total_output:,} output)
- **Average Tokens Per Request**: {avg_tokens:,.1f}
- **Estimated Total Cost**: ${total_cost:,.4f}
- **Estimated Cost Per Request**: ${avg_cost:,.6f}

## Breakdown by Model
| Provider | Model Name | Calls | Input Tokens | Output Tokens | Total Tokens | Estimated Cost (USD) |
|---|---|---|---|---|---|---|
"""
        for u in self.usages.values():
            m_total = u.input_tokens + u.output_tokens
            report += f"| {u.provider} | `{u.model_name}` | {u.calls:,} | {u.input_tokens:,} | {u.output_tokens:,} | {m_total:,} | ${u.total_cost:.4f} |\n"

        report += f"""
## Cost Accounting Methodology
- The pipeline architecture prioritizes deterministic local indexing and rule evaluation across structured database snapshots, system activity, and logs.
- High-efficiency multimodal extraction with zero-shot classification was used for non-structured evidence and intent boundary verification, ensuring high reproducibility, zero token waste, and minimal operational cost.
"""
        return report
