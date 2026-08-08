"""Shared Qt widgets (cabdecoding)."""

from __future__ import annotations

try:
    from PyQt5.QtWidgets import QDoubleSpinBox
    _HAS_GUI_DEPS = True
except Exception:  # pragma: no cover - headless
    QDoubleSpinBox = object  # type: ignore
    _HAS_GUI_DEPS = False


class CoordSpinBox(QDoubleSpinBox if _HAS_GUI_DEPS else object):
    """QDoubleSpinBox that strips insignificant trailing zeros.

    Example display: ``0`` (not ``0.000000``), ``10`` (not
    ``10.000000``), ``1.23`` (not ``1.230000``).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(10)
        self.setGroupSeparatorShown(False)

    def textFromValue(self, value: float) -> str:  # noqa: N802 (Qt)
        dec = max(0, int(self.decimals()))
        v = float(value)
        if abs(v) >= 1e15:
            return f"{v:.{dec}e}".replace("e+", "e").replace("e-0", "e-")
        s = f"{v:.{dec}f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-") else "0"
