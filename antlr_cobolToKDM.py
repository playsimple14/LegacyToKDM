import json
import os
import re
import xml.dom.minidom

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


import xml.etree.ElementTree as ET
from typing import List, Optional
from pydantic import BaseModel, Field

from tree_sitter import Parser
from tree_sitter_language_pack import get_language

from google import genai
from google.genai import types


# ---------------------------------------------------------------------------
# 1. Pydantic Schemas for KDM Output
# ---------------------------------------------------------------------------
class KDMActionElement(BaseModel):
    kind: str = Field(
        description="KDM Action kind: 'Reads', 'Writes', 'Calls', 'Computes'"
    )
    target: str = Field(description="Target variable, data element, or paragraph name")
    description: str = Field(
        description="Semantic explanation of what this action does"
    )


class KDMCodeItem(BaseModel):
    name: str = Field(description="Name of the routine, paragraph, or data structure")
    type: str = Field(
        description="KDM element type: 'CallableUnit', 'StorableUnit', 'DataSegment'"
    )
    actions: List[KDMActionElement] = Field(default_factory=list)
    business_rule: Optional[str] = Field(
        description="Extracted high-level business logic"
    )


class KDMModel(BaseModel):
    model_name: str = Field(description="Name of the KDM CodeModel segment")
    language: str = Field(description="Original source language (e.g., COBOL)")
    code_items: List[KDMCodeItem]


# ---------------------------------------------------------------------------
# 2. AST Extractor using antlr4-based COBOL Parser
# ---------------------------------------------------------------------------
from antlr4 import InputStream, CommonTokenStream
from Cobol85Lexer import Cobol85Lexer
from Cobol85Parser import Cobol85Parser


def parse_cobol_with_antlr(cobol_code: str) -> dict:
    input_stream = InputStream(cobol_code)
    lexer = Cobol85Lexer(input_stream)
    tokens = CommonTokenStream(lexer)
    parser = Cobol85Parser(tokens)

    tree = parser.startRule()
    return walk_cobol_ast(tree, source_text=cobol_code)


def walk_cobol_ast(node, source_text: Optional[str] = None):
    result = {
        "program_id": None,
        "data_division": [],
        "procedure_division": [],
    }
    seen_items = set()
    seen_paragraphs = set()

    def visit(current):
        if current is None:
            return

        text = current.getText()
        current_name = type(current).__name__

        if result["program_id"] is None:
            match = re.search(r"PROGRAM-ID\s*\.\s*([A-Z0-9-]+)", text, re.IGNORECASE)
            if match:
                result["program_id"] = match.group(1).strip()

        if (
            "WorkingStorageSectionContext" in current_name
            or "DataDivisionContext" in current_name
        ):
            for level, name, datatype in re.findall(
                r"(?im)^\s*(\d{2})\s+([A-Z0-9-]+)\s+PIC\s+([^\.\n]+)\.",
                text,
            ):
                item = (level.strip(), name.strip(), datatype.strip())
                if item not in seen_items:
                    seen_items.add(item)
                    result["data_division"].append(
                        {
                            "node_type": "data_description_entry",
                            "level": level.strip(),
                            "name": name.strip(),
                            "datatype": datatype.strip(),
                        }
                    )

        if "ParagraphContext" in current_name:
            match = re.search(r"(?is)([A-Z0-9-]+)\s*\.\s*(.*)", text)
            if match:
                paragraph_name = match.group(1).strip()
                body = match.group(2).strip()
                if paragraph_name and paragraph_name.upper() not in {
                    "DATA",
                    "WORKING-STORAGE",
                    "ENVIRONMENT",
                }:
                    paragraph_key = (paragraph_name, body)
                    if paragraph_key not in seen_paragraphs:
                        seen_paragraphs.add(paragraph_key)
                        result["procedure_division"].append(
                            {
                                "paragraph_name": paragraph_name,
                                "statements_block": body,
                            }
                        )

        # Safely iterate children for both ParserRuleContext and TerminalNodeImpl
        try:
            children = list(current.getChildren())
        except Exception:
            # TerminalNodeImpl in the ANTLR4 Python runtime does not have getChildren;
            # fall back to getChildCount/getChild when available.
            children = []
            if hasattr(current, "getChildCount"):
                try:
                    count = current.getChildCount()
                    for i in range(count):
                        try:
                            children.append(current.getChild(i))
                        except Exception:
                            pass
                except Exception:
                    pass

        for child in children:
            visit(child)

    visit(node)

    if result["program_id"] is None:
        result["program_id"] = "UNKNOWN"

    # If source text is available, extract data-division items from it
    if source_text:
        result["source"] = source_text
        m = re.search(
            r"DATA DIVISION\.(.*?)(?=PROCEDURE DIVISION\.|$)",
            source_text,
            re.IGNORECASE | re.S,
        )
        if m:
            data_block = m.group(1)
            for level, name, datatype in re.findall(
                r"(?im)^\s*(\d{2})\s+([A-Z0-9-]+)\s+PIC\s+([^\.\n]+)\.", data_block
            ):
                item = (level.strip(), name.strip(), datatype.strip())
                if item not in seen_items:
                    seen_items.add(item)
                    result["data_division"].append(
                        {
                            "node_type": "data_description_entry",
                            "level": level.strip(),
                            "name": name.strip(),
                            "datatype": datatype.strip(),
                        }
                    )

    return result


# ---------------------------------------------------------------------------
# 3. GenAI Semantic Mapper
# ---------------------------------------------------------------------------
def map_ast_to_kdm_local(intermediate_ast: dict) -> KDMModel:
    # Deterministic mapping without GenAI: map data items to StorableUnit and
    # paragraphs to CallableUnit with simple action inference from statements.
    code_items: List[KDMCodeItem] = []

    model_name = intermediate_ast.get("program_id") or "UNKNOWN"

    # Add storable units from data_division
    for item in intermediate_ast.get("data_division", []):
        name = item.get("name")
        if not name:
            continue
        ci = KDMCodeItem(
            name=name,
            type="StorableUnit",
            actions=[],
            business_rule=None,
        )
        code_items.append(ci)

    # Helper to normalize targets
    def norm_target(t: str) -> str:
        return re.sub(r"[\(\)\s]+", "", t).strip()

    # Prefer using original source (if present) to extract paragraph bodies with spacing
    source_text = intermediate_ast.get("source")

    # Parse procedure division paragraphs
    for para in intermediate_ast.get("procedure_division", []):
        pname = para.get("paragraph_name")
        # Try to find the paragraph body in the original source for better spacing
        body = ""
        if source_text and pname:
            # match paragraph by name followed by a dot and capture until next paragraph or end
            pm = re.search(
                rf"(?ims)^\s*{re.escape(pname)}\.\s*(.*?)(?=^\s*[A-Z0-9\-]+\.|\Z)",
                source_text,
            )
            if pm:
                body = pm.group(1)
        if not body:
            body = para.get("statements_block") or ""
        actions: List[KDMActionElement] = []

        # PERFORM -> Calls
        for m in re.finditer(r"PERFORM\s+([A-Z0-9-]+)", body, re.IGNORECASE):
            target = m.group(1).strip()
            actions.append(
                KDMActionElement(
                    kind="Calls",
                    target=target,
                    description=f"Invokes paragraph {target}.",
                )
            )

        # MOVE -> Writes
        for m in re.finditer(r"MOVE\s+([^\s]+)\s+TO\s+([^\s\.]+)", body, re.IGNORECASE):
            src = m.group(1).strip()
            tgt = norm_target(m.group(2))
            actions.append(
                KDMActionElement(
                    kind="Writes",
                    target=tgt,
                    description=f"Assigns value from {src} to {tgt}.",
                )
            )

        # COMPUTE -> Computes
        for m in re.finditer(
            r"COMPUTE\s+([^=\s]+)\s*=\s*([^\.]+)", body, re.IGNORECASE
        ):
            tgt = norm_target(m.group(1))
            expr = m.group(2).strip()
            actions.append(
                KDMActionElement(
                    kind="Computes",
                    target=tgt,
                    description=f"Computes {tgt} using expression: {expr}.",
                )
            )

        # ADD ... TO -> Writes/Updates
        for m in re.finditer(r"ADD\s+([^\s]+)\s+TO\s+([^\.\s]+)", body, re.IGNORECASE):
            src = m.group(1).strip()
            tgt = norm_target(m.group(2))
            actions.append(
                KDMActionElement(
                    kind="Writes",
                    target=tgt,
                    description=f"Adds {src} into {tgt} (update).",
                )
            )

        # DISPLAY -> Read then output
        for m in re.finditer(
            r"DISPLAY\s+['\"]?([^'\"]+)['\"]?\s*([^\.\n]*)", body, re.IGNORECASE
        ):
            text = m.group(1).strip()
            varpart = (m.group(2) or "").strip()
            if varpart:
                # likely DISPLAY 'str' VAR
                var = norm_target(varpart)
                actions.append(
                    KDMActionElement(
                        kind="Reads",
                        target=var,
                        description=f"Reads {var} to display: {text}.",
                    )
                )
                actions.append(
                    KDMActionElement(
                        kind="Writes",
                        target="DISPLAY",
                        description=f"Outputs formatted text and {var} to console.",
                    )
                )
            else:
                actions.append(
                    KDMActionElement(
                        kind="Writes",
                        target="DISPLAY",
                        description=f"Outputs text to console: {text}.",
                    )
                )

        business = None
        # Simple business rule inference: one-sentence summary from paragraph name
        if pname:
            business = f"Implements paragraph {pname}."

        code_items.append(
            KDMCodeItem(
                name=pname or "UNKNOWN",
                type="CallableUnit",
                actions=actions,
                business_rule=business,
            )
        )

    return KDMModel(model_name=model_name, language="COBOL", code_items=code_items)


def map_ast_to_kdm(intermediate_ast: dict, api_key: Optional[str] = None) -> KDMModel:
    # Prefer GenAI mapping when API key is provided, otherwise use local deterministic mapper.
    if api_key:
        client = genai.Client(api_key=api_key)

        prompt = f"""
        You are an expert software modernization engine specializing in OMG KDM (Knowledge Discovery Metamodel).

        Analyze the following Tree-sitter parsed COBOL AST and convert it into a KDM Code Model representation:
        1. Map paragraphs in procedure_division to 'CallableUnit'.
        2. Map items in data_division to 'StorableUnit'.
        3. Infer business rules and identify granular KDM actions ('Reads', 'Writes', 'Calls', 'Computes') for statements.

        CRITICAL CONSTRAINTS:
        - Keep `business_rule` concise (1 sentence max).
        - Exclude internal log chatter or execution trace notes.

        Parsed AST:
        {json.dumps(intermediate_ast, indent=2)}
        """

        chat = client.chats.create(
            model="gemini-3.6-flash",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=KDMModel,
                temperature=0.1,
            ),
        )

        response = chat.send_message(prompt)
        return KDMModel.model_validate_json(response.text)

    # No API key -> local mapper
    return map_ast_to_kdm_local(intermediate_ast)


# ---------------------------------------------------------------------------
# 4. KDM XML Serialization
# ---------------------------------------------------------------------------
def generate_kdm_xml(kdm_data: KDMModel) -> str:
    kdm_root = ET.Element(
        "kdm:Segment",
        {
            "xmlns:xmi": "http://www.omg.org/XMI",
            "xmlns:kdm": "http://www.omg.org/spec/KDM/20160201/kdm",
            "xmlns:code": "http://www.omg.org/spec/KDM/20160201/code",
            "xmi:version": "2.0",
        },
    )

    model_node = ET.SubElement(
        kdm_root,
        "model",
        {
            "xmi:type": "code:CodeModel",
            "name": kdm_data.model_name,
            "language": kdm_data.language,
        },
    )

    for item in kdm_data.code_items:
        code_element = ET.SubElement(
            model_node,
            "codeElement",
            {"xmi:type": f"code:{item.type}", "name": item.name},
        )
        if item.business_rule:
            ET.SubElement(
                code_element,
                "attribute",
                {"tag": "businessRule", "value": item.business_rule},
            )
        for action in item.actions:
            ET.SubElement(
                code_element,
                "action",
                {
                    "kind": action.kind,
                    "target": action.target,
                    "description": action.description,
                },
            )

    raw_xml = ET.tostring(kdm_root, encoding="utf-8")
    parsed_dom = xml.dom.minidom.parseString(raw_xml)
    return parsed_dom.toprettyxml(indent="  ")


# ---------------------------------------------------------------------------
# 5. Pipeline Execution
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample_cobol = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALC-PAYROLL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  EMP-COUNT        PIC 9(02) VALUE 3.
       01  IDX              PIC 9(02).
       01  TAX-RATE         PIC V99   VALUE .20.
       01  TOTAL-PAYROLL    PIC 9(7)V99 VALUE 0.

       01  EMPLOYEE-TABLE.
           05 EMP-RECORD OCCURS 3 TIMES.
              10 EMP-ID     PIC 9(04).
              10 HOURS-WORKED PIC 9(03).
              10 HOURLY-RATE  PIC 9(03)V99.
              10 GROSS-PAY    PIC 9(05)V99.
              10 NET-PAY      PIC 9(05)V99.

       PROCEDURE DIVISION.
       0000-MAIN-LINE.
           PERFORM 1000-INITIALIZE-DATA.
           PERFORM 2000-PROCESS-PAYROLL VARYING IDX FROM 1 BY 1 
              UNTIL IDX > EMP-COUNT.
           PERFORM 3000-DISPLAY-SUMMARY.
           STOP RUN.

       1000-INITIALIZE-DATA.
           MOVE 1001 TO EMP-ID(1).
           MOVE 40   TO HOURS-WORKED(1).
           MOVE 25.00 TO HOURLY-RATE(1).

           MOVE 1002 TO EMP-ID(2).
           MOVE 45   TO HOURS-WORKED(2).
           MOVE 30.00 TO HOURLY-RATE(2).

           MOVE 1003 TO EMP-ID(3).
           MOVE 35   TO HOURS-WORKED(3).
           MOVE 20.00 TO HOURLY-RATE(3).

       2000-PROCESS-PAYROLL.
           COMPUTE GROSS-PAY(IDX) = HOURS-WORKED(IDX) * HOURLY-RATE(IDX).
           IF HOURS-WORKED(IDX) > 40 THEN
              COMPUTE GROSS-PAY(IDX) = GROSS-PAY(IDX) + 
                 ((HOURS-WORKED(IDX) - 40) * HOURLY-RATE(IDX) * 0.5)
           END-IF.
           COMPUTE NET-PAY(IDX) = GROSS-PAY(IDX) * (1 - TAX-RATE).
           ADD NET-PAY(IDX) TO TOTAL-PAYROLL.

       3000-DISPLAY-SUMMARY.
           DISPLAY 'TOTAL PAYROLL DISBURSED: ' TOTAL-PAYROLL.
    """
    ast = parse_cobol_with_antlr(sample_cobol)
    # ast = parse_cobol_with_treesitter(sample_cobol)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not set — using local deterministic mapper.")

    kdm_structured = map_ast_to_kdm(ast, api_key=api_key)

    xml_output = generate_kdm_xml(kdm_structured)
    print(xml_output)
