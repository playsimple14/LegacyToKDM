import re
from typing import Optional

from antlr4 import CommonTokenStream, InputStream

from Cobol85Lexer import Cobol85Lexer
from Cobol85Parser import Cobol85Parser


class ParserAgent:
    name = "parser"
    non_paragraph_names = {
        "DATA",
        "WORKING-STORAGE",
        "ENVIRONMENT",
        "PROGRAM-ID",
        "IF",
        "ELSE",
        "END-IF",
        "PERFORM",
        "STOP",
        "RUN",
        "DISPLAY",
        "MOVE",
        "COMPUTE",
        "ADD",
    }

    def run(self, cobol_code: str) -> dict:
        input_stream = InputStream(cobol_code)
        lexer = Cobol85Lexer(input_stream)
        tokens = CommonTokenStream(lexer)
        parser = Cobol85Parser(tokens)
        tree = parser.startRule()
        ast = self._walk(tree, cobol_code)
        ast["source"] = cobol_code
        return ast

    def _walk(self, node, source_text: Optional[str]) -> dict:
        result = {
            "program_id": None,
            "data_division": [],
            "procedure_division": [],
        }
        seen_items = set()
        seen_paragraphs = set()

        def visit(current) -> None:
            if current is None:
                return
            text = current.getText()
            context_name = type(current).__name__

            if result["program_id"] is None:
                match = re.search(
                    r"PROGRAM-ID\s*\.\s*([A-Z0-9-]+)", text, re.IGNORECASE
                )
                if match:
                    result["program_id"] = match.group(1)

            if (
                "WorkingStorageSectionContext" in context_name
                or "DataDivisionContext" in context_name
            ):
                self._add_data_items(text, result, seen_items)

            if "ParagraphContext" in context_name:
                match = re.search(r"(?is)([A-Z0-9-]+)\s*\.\s*(.*)", text)
                if match:
                    name = match.group(1).strip()
                    body = match.group(2).strip()
                    if name.upper() not in self.non_paragraph_names:
                        key = (name, body)
                        if key not in seen_paragraphs:
                            seen_paragraphs.add(key)
                            result["procedure_division"].append(
                                {"paragraph_name": name, "statements_block": body}
                            )

            children = []
            if hasattr(current, "getChildren"):
                try:
                    children = list(current.getChildren())
                except Exception:
                    children = []
            for child in children:
                visit(child)

        visit(node)
        result["program_id"] = result["program_id"] or "UNKNOWN"

        if source_text:
            match = re.search(
                r"DATA DIVISION\.(.*?)(?=PROCEDURE DIVISION\.|$)",
                source_text,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                self._add_data_items(match.group(1), result, seen_items)
            self._recover_procedure_division(source_text, result, seen_paragraphs)
        return result

    @staticmethod
    def _recover_procedure_division(
        source_text: str, result: dict, seen_paragraphs: set
    ) -> None:
        procedure_match = re.search(
            r"PROCEDURE DIVISION\.(.*)", source_text, re.IGNORECASE | re.DOTALL
        )
        if not procedure_match:
            return

        procedure_text = procedure_match.group(1).strip()
        result["procedure_division"] = [
            paragraph
            for paragraph in result["procedure_division"]
            if paragraph["paragraph_name"].upper()
            not in ParserAgent.non_paragraph_names
        ]

        if result["procedure_division"] or not procedure_text:
            return

        paragraph_matches = [
            match
            for match in re.finditer(r"(?im)^\s*([A-Z0-9-]+)\.\s*$", procedure_text)
            if match.group(1).upper() not in ParserAgent.non_paragraph_names
        ]
        if not paragraph_matches:
            result["procedure_division"].append(
                {
                    "paragraph_name": "MAIN-LINE",
                    "statements_block": procedure_text,
                }
            )
            return

        for index, match in enumerate(paragraph_matches):
            name = match.group(1).strip()
            body_start = match.end()
            body_end = (
                paragraph_matches[index + 1].start()
                if index + 1 < len(paragraph_matches)
                else len(procedure_text)
            )
            body = procedure_text[body_start:body_end].strip()
            key = (name, body)
            if key not in seen_paragraphs:
                seen_paragraphs.add(key)
                result["procedure_division"].append(
                    {"paragraph_name": name, "statements_block": body}
                )

    @staticmethod
    def _add_data_items(text: str, result: dict, seen_items: set) -> None:
        for level, name, datatype in re.findall(
            r"(?im)^\s*(\d{2})\s+([A-Z0-9-]+)\s+PIC\s+([^\.\n]+)\.", text
        ):
            item = (level.strip(), name.strip(), datatype.strip())
            if item in seen_items:
                continue
            seen_items.add(item)
            result["data_division"].append(
                {
                    "node_type": "data_description_entry",
                    "level": level.strip(),
                    "name": name.strip(),
                    "datatype": datatype.strip(),
                }
            )
