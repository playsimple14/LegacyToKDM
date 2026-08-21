import xml.dom.minidom
import xml.etree.ElementTree as ET

from .models import KDMModel


def generate_kdm_xml(kdm_data: KDMModel) -> str:
    root = ET.Element(
        "kdm:Segment",
        {
            "xmlns:xmi": "http://www.omg.org/XMI",
            "xmlns:kdm": "http://www.omg.org/spec/KDM/20160201/kdm",
            "xmlns:code": "http://www.omg.org/spec/KDM/20160201/code",
            "xmi:version": "2.0",
        },
    )
    model = ET.SubElement(
        root,
        "model",
        {
            "xmi:type": "code:CodeModel",
            "name": kdm_data.model_name,
            "language": kdm_data.language,
        },
    )
    for item in kdm_data.code_items:
        element = ET.SubElement(
            model,
            "codeElement",
            {"xmi:type": f"code:{item.type}", "name": item.name},
        )
        if item.business_rule:
            ET.SubElement(
                element,
                "attribute",
                {"tag": "businessRule", "value": item.business_rule},
            )
        for action in item.actions:
            ET.SubElement(
                element,
                "action",
                {
                    "kind": action.kind,
                    "target": action.target,
                    "description": action.description,
                },
            )
    return xml.dom.minidom.parseString(ET.tostring(root, encoding="utf-8")).toprettyxml(
        indent="  "
    )
