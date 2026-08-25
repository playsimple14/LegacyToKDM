import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from multi_agent_kdm.business_rule_agent import BusinessRuleAgent
from multi_agent_kdm.data_flow_agent import DataFlowAgent
from multi_agent_kdm.parser_agent import ParserAgent
from multi_agent_kdm.structure_agent import StructureAgent


def f1_score(
    expected: Iterable[str], predicted: Iterable[str]
) -> tuple[float, int, int, int]:
    expected_set = set(expected)
    predicted_set = set(predicted)
    true_positive = len(expected_set & predicted_set)
    false_positive = len(predicted_set - expected_set)
    false_negative = len(expected_set - predicted_set)
    precision = (
        true_positive / len(predicted_set)
        if predicted_set
        else 1.0 if not expected_set else 0.0
    )
    recall = true_positive / len(expected_set) if expected_set else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return f1, true_positive, false_positive, false_negative


def evaluate_case(case: dict) -> dict:
    source = (ROOT / case["source"]).read_text(encoding="utf-8")
    ast = ParserAgent().run(source)
    structure = StructureAgent().run(ast)
    data_flow = DataFlowAgent().run(ast)
    business_rules = BusinessRuleAgent(api_key=os.getenv("GEMINI_API_KEY")).run(ast)

    predicted = {
        "program_id": ast["program_id"],
        "data_items": [item["name"] for item in ast["data_division"]],
        "paragraphs": [
            finding.subject
            for finding in structure.findings
            if finding.finding_type == "CallableUnit"
        ],
        "calls": [
            finding.value
            for finding in structure.findings
            if finding.finding_type == "Calls"
        ],
        "reads": [
            finding.value
            for finding in data_flow.findings
            if finding.finding_type == "Reads"
        ],
        "writes": [
            finding.value
            for finding in data_flow.findings
            if finding.finding_type == "Writes"
        ],
        "computes": [
            finding.value
            for finding in data_flow.findings
            if finding.finding_type == "Computes"
        ],
        "business_rule_count": sum(
            finding.finding_type == "BusinessRule"
            for finding in business_rules.findings
        ),
    }

    expected = case["expected"]
    scores = {}
    for field in ("data_items", "paragraphs", "calls", "reads", "writes", "computes"):
        score, true_positive, false_positive, false_negative = f1_score(
            expected[field], predicted[field]
        )
        scores[field] = {
            "f1": round(score, 3),
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
        }
    scores["business_rule_count"] = {
        "expected": expected["business_rule_count"],
        "predicted": predicted["business_rule_count"],
        "exact": expected["business_rule_count"] == predicted["business_rule_count"],
    }
    return {
        "name": case["name"],
        "predicted": predicted,
        "scores": scores,
        "business_rule_warnings": business_rules.warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate COBOL-to-KDM extraction on labeled cases."
    )
    parser.add_argument(
        "--benchmark", default=str(Path(__file__).with_name("benchmark.json"))
    )
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    cases = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    results = [evaluate_case(case) for case in cases]
    report = {
        "case_count": len(results),
        "business_rule_provider_requested": (
            "gemini" if os.getenv("GEMINI_API_KEY") else "local-fallback"
        ),
        "results": results,
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
