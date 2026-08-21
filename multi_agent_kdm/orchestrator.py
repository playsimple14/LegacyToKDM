import asyncio
from typing import Optional

from .business_rule_agent import BusinessRuleAgent
from .data_flow_agent import DataFlowAgent
from .kdm_builder_agent import KDMBuilderAgent
from .models import AnalysisBundle, KDMModel
from .parser_agent import ParserAgent
from .serializer import generate_kdm_xml
from .structure_agent import StructureAgent
from .validator_agent import ValidatorAgent


class MultiAgentOrchestrator:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.parser = ParserAgent()
        self.analysis_agents = [
            StructureAgent(),
            DataFlowAgent(),
            BusinessRuleAgent(api_key=api_key),
        ]
        self.builder = KDMBuilderAgent()
        self.validator = ValidatorAgent()

    def analyze(self, cobol_code: str) -> AnalysisBundle:
        ast = self.parser.run(cobol_code)
        results = [agent.run(ast) for agent in self.analysis_agents]
        return AnalysisBundle(ast=ast, results=results)

    def build(self, bundle: AnalysisBundle) -> KDMModel:
        model = self.builder.run(bundle.ast, bundle.results)
        validation = self.validator.run(model)
        errors = [
            warning for warning in validation.warnings if warning.startswith("ERROR:")
        ]
        if errors:
            raise ValueError("KDM validation failed: " + " ".join(errors))
        return model

    def run(self, cobol_code: str) -> str:
        return generate_kdm_xml(self.build(self.analyze(cobol_code)))

    async def analyze_async(self, cobol_code: str) -> AnalysisBundle:
        ast = await asyncio.to_thread(self.parser.run, cobol_code)
        results = await asyncio.gather(
            *(asyncio.to_thread(agent.run, ast) for agent in self.analysis_agents)
        )
        return AnalysisBundle(ast=ast, results=list(results))


def run_pipeline(cobol_code: str, api_key: Optional[str] = None) -> str:
    return MultiAgentOrchestrator(api_key=api_key).run(cobol_code)
