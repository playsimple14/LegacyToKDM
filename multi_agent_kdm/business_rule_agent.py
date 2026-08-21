import re
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .models import AgentFinding, AgentResult


class BusinessRuleResponse(BaseModel):
    rules: list[str] = Field(default_factory=list)


class BusinessRuleAgent:
    name = "business-rules"

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key) if api_key else None
        self.model = model

    def run(self, ast: dict) -> AgentResult:
        if self.client:
            return self._run_llm(ast)
        return self._run_local(ast)

    def _run_llm(self, ast: dict) -> AgentResult:
        findings = []
        warnings = []
        for paragraph in ast.get("procedure_division", []):
            subject = paragraph.get("paragraph_name") or "UNKNOWN"
            body = paragraph.get("statements_block", "")
            prompt = f"""
Extract the business rules from this COBOL paragraph.
Return one concise rule for each meaningful condition or calculation.
Do not include execution logs or explanations outside the JSON response.

Paragraph: {subject}
COBOL:
{body}
"""
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=BusinessRuleResponse,
                        temperature=0.1,
                    ),
                )
                parsed = BusinessRuleResponse.model_validate_json(response.text)
                rules = parsed.rules or [f"Implements paragraph {subject}."]
                findings.extend(
                    AgentFinding(
                        agent=self.name,
                        subject=subject,
                        finding_type="BusinessRule",
                        value=rule.strip(),
                        confidence=0.8,
                    )
                    for rule in rules
                    if rule.strip()
                )
            except Exception as error:
                warnings.append(
                    f"LLM failed for {subject}; local fallback used: {error}"
                )
                findings.extend(self._local_findings(subject, body))
        return AgentResult(agent=self.name, findings=findings, warnings=warnings)

    def _run_local(self, ast: dict) -> AgentResult:
        findings = []
        for paragraph in ast.get("procedure_division", []):
            subject = paragraph.get("paragraph_name") or "UNKNOWN"
            body = paragraph.get("statements_block", "")
            findings.extend(self._local_findings(subject, body))
        return AgentResult(agent=self.name, findings=findings)

    def _local_findings(self, subject: str, body: str) -> list[AgentFinding]:
        findings = []
        conditions = re.findall(
            r"IF\s+(.+?)(?=\s+THEN|\.|END-IF)", body, re.IGNORECASE | re.DOTALL
        )
        for condition in conditions:
            normalized = " ".join(condition.split())
            findings.append(
                AgentFinding(
                    agent=self.name,
                    subject=subject,
                    finding_type="BusinessRule",
                    value=f"When {normalized}, execute the conditional processing.",
                    confidence=0.85,
                )
            )
        if not conditions:
            findings.append(
                AgentFinding(
                    agent=self.name,
                    subject=subject,
                    finding_type="BusinessRule",
                    value=f"Implements paragraph {subject}.",
                    confidence=0.6,
                )
            )
        return findings
