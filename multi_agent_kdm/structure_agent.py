import re

from .models import AgentFinding, AgentResult


class StructureAgent:
    name = "structure"

    def run(self, ast: dict) -> AgentResult:
        findings = []
        paragraphs = ast.get("procedure_division", [])
        paragraph_names = {item.get("paragraph_name") for item in paragraphs}

        for paragraph in paragraphs:
            name = paragraph.get("paragraph_name") or "UNKNOWN"
            findings.append(
                AgentFinding(
                    agent=self.name,
                    subject=name,
                    finding_type="CallableUnit",
                    value="COBOL procedure paragraph",
                )
            )
            body = paragraph.get("statements_block", "")
            for target in re.findall(r"PERFORM\s+([A-Z0-9-]+)", body, re.IGNORECASE):
                confidence = 1.0 if target in paragraph_names else 0.8
                findings.append(
                    AgentFinding(
                        agent=self.name,
                        subject=name,
                        finding_type="Calls",
                        value=target,
                        confidence=confidence,
                    )
                )
        return AgentResult(agent=self.name, findings=findings)
