"""XML well-formedness inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_xml_Script.R: parse validity,
root element and namespace summary.
"""

from pathlib import Path
from typing import List

from engine.checks.base import Check, CheckResult


class XmlCheck(Check):
    """XML check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.xml"
    extensions = {".xml", ".xsd"}

    def run(self, files: List[Path]) -> List[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> List[CheckResult]:
        try:
            from lxml import etree
        except ImportError:
            from engine.checks._util import missing_library

            return [missing_library("format.xml.valid", "lxml")]

        name = path.name
        try:
            tree = etree.parse(str(path))
        except etree.XMLSyntaxError as exc:
            return [
                CheckResult(
                    check_id="format.xml.valid",
                    level="error",
                    passed=False,
                    message=f"{name}: not well-formed ({exc})",
                )
            ]

        root = tree.getroot()
        namespaces = {k for k in root.nsmap if k}
        message = f"{name}: well-formed, root <{etree.QName(root).localname}>"
        if namespaces:
            message += f", namespaces: {', '.join(sorted(namespaces))}"
        return [
            CheckResult(
                check_id="format.xml.valid",
                level="info",
                passed=True,
                message=message,
            )
        ]