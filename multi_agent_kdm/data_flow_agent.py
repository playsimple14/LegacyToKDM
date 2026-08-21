import re

from .models import AgentFinding, AgentResult


class DataFlowAgent:
    name = "data-flow"

    def run(self, ast: dict) -> AgentResult:
        findings = []
        data_names = {
            item.get("name", "").upper()
            for item in ast.get("data_division", [])
            if item.get("name")
        }
        for paragraph in ast.get("procedure_division", []):
            subject = paragraph.get("paragraph_name") or "UNKNOWN"
            body = paragraph.get("statements_block", "")
            findings.extend(self._find_moves(subject, body))
            findings.extend(self._find_computes(subject, body))
            findings.extend(self._find_adds(subject, body))
            findings.extend(self._find_displays(subject, body, data_names))
            findings.extend(self._find_condition_reads(subject, body, data_names))
        return AgentResult(agent=self.name, findings=findings)

    def _find_moves(self, subject: str, body: str):
        return [
            AgentFinding(
                agent=self.name,
                subject=subject,
                finding_type="Writes",
                value=target,
                confidence=0.95,
            )
            for _, target in re.findall(
                r"MOVE\s+([^\s]+)\s+TO\s+([^\s\.]+)", body, re.IGNORECASE
            )
        ]

    def _find_computes(self, subject: str, body: str):
        return [
            AgentFinding(
                agent=self.name,
                subject=subject,
                finding_type="Computes",
                value=target,
                confidence=0.95,
            )
            for target in re.findall(r"COMPUTE\s+([^=\s]+)\s*=", body, re.IGNORECASE)
        ]

    def _find_adds(self, subject: str, body: str):
        return [
            AgentFinding(
                agent=self.name,
                subject=subject,
                finding_type="Writes",
                value=target,
                confidence=0.95,
            )
            for _, target in re.findall(
                r"ADD\s+([^\s]+)\s+TO\s+([^\.\s]+)", body, re.IGNORECASE
            )
        ]

    def _find_displays(self, subject: str, body: str, data_names: set[str]):
        findings = []
        for display_body in re.findall(r"\bDISPLAY\s+([^\.\n]+)", body, re.IGNORECASE):
            findings.append(
                AgentFinding(
                    agent=self.name,
                    subject=subject,
                    finding_type="Writes",
                    value="DISPLAY",
                    confidence=0.95,
                )
            )
            findings.extend(
                AgentFinding(
                    agent=self.name,
                    subject=subject,
                    finding_type="Reads",
                    value=name,
                    confidence=0.95,
                )
                for name in self._known_names(display_body, data_names)
            )
        return findings

    def _find_condition_reads(self, subject: str, body: str, data_names: set[str]):
        findings = []
        conditions = re.findall(
            r"\bIF\s+(.+?)(?=\s+THEN|\.|END-IF|\bELSE\b)",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        for condition in conditions:
            findings.extend(
                AgentFinding(
                    agent=self.name,
                    subject=subject,
                    finding_type="Reads",
                    value=name,
                    confidence=0.95,
                )
                for name in self._known_names(condition, data_names)
            )
        return findings

    @staticmethod
    def _known_names(text: str, data_names: set[str]) -> list[str]:
        return [
            name
            for name in data_names
            if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE)
        ]
