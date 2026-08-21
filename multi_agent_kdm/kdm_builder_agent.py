from typing import Dict, List

from .models import (
    AgentResult,
    KDMActionElement,
    KDMCodeItem,
    KDMModel,
)


class KDMBuilderAgent:
    name = "kdm-builder"

    def run(self, ast: dict, results: List[AgentResult]) -> KDMModel:
        findings = [finding for result in results for finding in result.findings]
        items: Dict[str, KDMCodeItem] = {}

        for data_item in ast.get("data_division", []):
            name = data_item.get("name")
            if name:
                items[name] = KDMCodeItem(name=name, type="StorableUnit")

        for finding in findings:
            if finding.finding_type == "CallableUnit":
                items.setdefault(
                    finding.subject,
                    KDMCodeItem(name=finding.subject, type="CallableUnit"),
                )

        for finding in findings:
            item = items.get(finding.subject)
            if item is None:
                continue
            if finding.finding_type in {"Calls", "Reads", "Writes", "Computes"}:
                item.actions.append(
                    KDMActionElement(
                        kind=finding.finding_type,
                        target=finding.value,
                        description=f"{finding.finding_type} operation involving {finding.value}.",
                    )
                )
            elif finding.finding_type == "BusinessRule":
                item.business_rule = finding.value

        return KDMModel(
            model_name=ast.get("program_id", "UNKNOWN"),
            language="COBOL",
            code_items=list(items.values()),
        )
