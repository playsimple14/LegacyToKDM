from .models import AgentResult, KDMModel


class ValidatorAgent:
    name = "validator"
    valid_action_kinds = {"Reads", "Writes", "Calls", "Computes"}

    def run(self, model: KDMModel) -> AgentResult:
        warnings = []
        errors = []
        names = [item.name for item in model.code_items]
        if len(names) != len(set(names)):
            errors.append("KDM contains duplicate code item names.")
        for item in model.code_items:
            for action in item.actions:
                if action.kind not in self.valid_action_kinds:
                    errors.append(f"Invalid action kind: {action.kind}.")
            if (
                item.type == "CallableUnit"
                and not item.actions
                and not item.business_rule
            ):
                warnings.append(f"CallableUnit {item.name} has no analysis findings.")
        for error in errors:
            warnings.append(f"ERROR: {error}")
        return AgentResult(agent=self.name, warnings=warnings)
