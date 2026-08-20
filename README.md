# Legacy COBOL → KDM

This repository contains a small pipeline that parses COBOL (ANTLR) and maps the parsed AST to an OMG KDM (Knowledge Discovery Metamodel) CodeModel.

Quick start

1. Create a Python virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Run the example:

```powershell
# set GEMINI_API_KEY in your session if you want GenAI-backed mapping
$env:GEMINI_API_KEY = "your_api_key_here"
python antlr_cobolToKDM.py
```

Notes

- The ANTLR-generated lexer/parser (`Cobol85Lexer.py`, `Cobol85Parser.py`) are included for convenience.
- If you want to re-generate the parser, use the `antlr-4.13.1-complete.jar` and the grammar files `.g4`.

License: (add a license file if desired)
