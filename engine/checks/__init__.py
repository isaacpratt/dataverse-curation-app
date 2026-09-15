"""Registry of format checks, ported from the CUR_Res_CurationTools R scripts.

See docs/engine-port.md for port status and docs/report-contract.md for the
check_id namespaces.
"""

from engine.checks.base import Check, CheckResult
from engine.checks import (
    extensions_check,
    csv_check,
    xlsx_check,
    sav_check,
    sas7bdat_check,
    dta_check,
    json_check,
    xml_check,
    ipynb_check,
    sqlite_check,
    hdf5_check,
    nc_check,
    gpkg_check,
    tiff_check,
    images_check,
    pdf_check,
    text_check,
    code_check,
    containers_check,
    fastq_check,
)

_MODULES = (
    extensions_check,
    csv_check,
    xlsx_check,
    sav_check,
    sas7bdat_check,
    dta_check,
    json_check,
    xml_check,
    ipynb_check,
    sqlite_check,
    hdf5_check,
    nc_check,
    gpkg_check,
    tiff_check,
    images_check,
    pdf_check,
    text_check,
    code_check,
    containers_check,
    fastq_check,
)

registry: dict = {}
for _module in _MODULES:
    for _name in dir(_module):
        _obj = getattr(_module, _name)
        if (
            isinstance(_obj, type)
            and issubclass(_obj, Check)
            and _obj is not Check
            and getattr(_obj, "check_id", None) not in (None, "base.check")
        ):
            registry[_obj.check_id] = _obj

__all__ = ["Check", "CheckResult", "registry"]