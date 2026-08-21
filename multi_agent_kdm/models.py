from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class KDMActionElement(BaseModel):
    kind: str
    target: str
    description: str


class KDMCodeItem(BaseModel):
    name: str
    type: str
    actions: List[KDMActionElement] = Field(default_factory=list)
    business_rule: Optional[str] = None


class KDMModel(BaseModel):
    model_name: str
    language: str
    code_items: List[KDMCodeItem] = Field(default_factory=list)


class AgentFinding(BaseModel):
    agent: str
    subject: str
    finding_type: str
    value: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AgentResult(BaseModel):
    agent: str
    findings: List[AgentFinding] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class AnalysisBundle(BaseModel):
    ast: Dict
    results: List[AgentResult] = Field(default_factory=list)
