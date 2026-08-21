# Multi-Agent COBOL to KDM

This package adds a local multi-agent pipeline around the generated ANTLR COBOL parser.

## Agents

- `ParserAgent`: creates the intermediate AST.
- `StructureAgent`: finds paragraphs and `PERFORM` calls.
- `DataFlowAgent`: finds reads, writes, and computations.
- `BusinessRuleAgent`: extracts conditional rules.
- `KDMBuilderAgent`: combines agent findings into `KDMModel`.
- `ValidatorAgent`: checks the generated model.

The structure, data-flow, parsing, validation, and serialization agents are deterministic. The business-rule agent uses Gemini when `GEMINI_API_KEY` is set and automatically falls back to local rules when it is not set or an LLM request fails.

## Enable Gemini

Set the key in PowerShell before running:

```powershell
$env:GEMINI_API_KEY = "your_api_key_here"
```

The key is read by `run.py` and passed to `BusinessRuleAgent`. Do not put the key in source files or commit it to Git.

## Run

From the `cobol-parser` directory:

```powershell
python -m multi_agent_kdm.run sample.cbl -o output.kdm.xml
```

Or provide source through standard input:

```powershell
Get-Content sample.cbl -Raw | python -m multi_agent_kdm.run
```
