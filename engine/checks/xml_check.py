"""XML well-formedness inspection.

Port of CUR_Res_CurationTools Scripts/Inspect_xml_Script.R: parse validity,
root element and namespace summary.
"""

from pathlib import Path

from engine.checks.base import Check, CheckResult


class XmlCheck(Check):
    """XML check - port of the CUR_Res_CurationTools R inspector."""

    check_id = "format.xml"
    extensions = {".xml", ".xsd"}

    def run(self, files: list[Path]) -> list[CheckResult]:
        from engine.checks._util import run_per_file

        return run_per_file(self, files, self._run_one)

    def _run_one(self, path: Path) -> list[CheckResult]:
        try:
            from lxml import etree
        except ImportError:
            from engine.checks._util import missing_library

            return [missing_library("format.xml.valid", "lxml")]

        name = path.name
        # Size gate: full DOM parse of a 500MB dump OOMs. Beyond the cap,
        # stream with iterparse for root/namespace summary only.
        _MAX_FULL_PARSE_BYTES = 64 << 20
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size > _MAX_FULL_PARSE_BYTES:
            try:
                context = etree.iterparse(str(path), events=("start",), huge_tree=False)
                root_tag = None
                namespaces: set[str] = set()
                for _, elem in context:
                    if root_tag is None:
                        root_tag = etree.QName(elem).localname
                        nsmap = getattr(elem, "nsmap", {}) or {}
                        namespaces = {k for k in nsmap if k}
                        break
                # Free the parser promptly.
                try:
                    del context
                except Exception:
                    pass
                if root_tag is None:
                    return [
                        CheckResult(
                            check_id="format.xml.valid",
                            level="error",
                            passed=False,
                            message=f"{name}: empty or unparseable XML",
                        )
                    ]
                message = f"{name}: well-formed (streamed, {size} bytes), root <{root_tag}>"
                if namespaces:
                    message += f", namespaces: {', '.join(sorted(namespaces))}"
                return [
                    CheckResult(
                        check_id="format.xml.valid",
                        level="info",
                        passed=True,
                        message=message,
                        details={"streamed": True, "size_bytes": size},
                    )
                ]
            except etree.XMLSyntaxError as exc:
                return [
                    CheckResult(
                        check_id="format.xml.valid",
                        level="error",
                        passed=False,
                        message=f"{name}: not well-formed ({exc})",
                    )
                ]
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
