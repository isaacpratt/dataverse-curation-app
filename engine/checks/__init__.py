"""Registry of format checks, ported from the CUR_Res_CurationTools R scripts.

See docs/explanation/engine-port.md for port status and docs/reference/report-contract.md for the
check_id namespaces.
"""

from typing import Any

from engine.checks import (
    access_check,
    code_check,
    containers_check,
    csv_check,
    dta_check,
    extensions_check,
    fastq_check,
    gpkg_check,
    hdf5_check,
    images_check,
    ipynb_check,
    json_check,
    nc_check,
    pdf_check,
    readme_check,
    sas7bdat_check,
    sav_check,
    secret_check,
    sqlite_check,
    text_check,
    tiff_check,
    varmeta_check,
    xlsx_check,
    xml_check,
)
from engine.checks.base import Check, CheckResult

_MODULES = (
    extensions_check,
    access_check,
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
    secret_check,
    containers_check,
    fastq_check,
    varmeta_check,
    readme_check,
)

registry: dict[str, Any] = {}


def register_checks(module: Any, target: dict[str, Any] | None = None) -> dict[str, Any]:
    """Register one module's Check subclasses, insisting on a declared scope.

    The scope is not optional (dv-p1d): it decides whether a check's
    findings land in ``dataset_checks`` or in a file entry. Refusing here
    means a new check cannot inherit an accidental answer — ``extensions``
    only says which files it reads.
    """
    target = registry if target is None else target
    for _name in dir(module):
        _obj = getattr(module, _name)
        if (
            isinstance(_obj, type)
            and issubclass(_obj, Check)
            and _obj is not Check
            and getattr(_obj, "check_id", None) not in (None, "base.check")
        ):
            _scope = getattr(_obj, "scope", None)
            if _scope not in ("dataset", "file"):
                raise TypeError(
                    f"{_obj.__name__} must declare scope = 'dataset' or 'file' "
                    f"(got {_scope!r}); extensions only says which files it reads"
                )
            target[_obj.check_id] = _obj
    return target


for _module in _MODULES:
    register_checks(_module)

__all__ = ["Check", "CheckResult", "register_checks", "registry"]
