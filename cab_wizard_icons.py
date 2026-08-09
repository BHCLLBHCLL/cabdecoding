"""STpre-style schematic icons for Condition Wizard (nav + BC New buttons).

Icons are drawn with QPainter so the repo does not ship binary assets.
Layouts follow STpreCwiz New-panel imagery (cube face + arrows / profiles).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Callable, Optional

try:
    from PyQt5.QtCore import QPointF, QRectF, Qt
    from PyQt5.QtGui import (
        QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap,
        QPolygonF,
    )
    from PyQt5.QtWidgets import QPushButton, QSizePolicy, QWidget
    _HAS_GUI = True
except Exception:  # pragma: no cover
    _HAS_GUI = False
    QWidget = object  # type: ignore


def _pm(size: int = 48) -> "QPixmap":
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    return pm


def _painter(pm: "QPixmap") -> "QPainter":
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    return p


def _cube_face(p: "QPainter", *, x=8, y=10, w=32, h=28,
               face=QColor(180, 180, 185), edge=QColor(90, 90, 95)) -> None:
    p.setBrush(QBrush(face))
    p.setPen(QPen(edge, 1.5))
    p.drawRect(x, y, w, h)
    # top / side bevel
    p.setBrush(QBrush(face.lighter(115)))
    p.drawPolygon(QPolygonF([
        QPointF(x, y), QPointF(x + 6, y - 5),
        QPointF(x + w + 6, y - 5), QPointF(x + w, y),
    ]))
    p.setBrush(QBrush(face.darker(110)))
    p.drawPolygon(QPolygonF([
        QPointF(x + w, y), QPointF(x + w + 6, y - 5),
        QPointF(x + w + 6, y + h - 5), QPointF(x + w, y + h),
    ]))


def _arrow(p: "QPainter", x0: float, y0: float, x1: float, y1: float,
           color=QColor(40, 110, 220), width: float = 2.2) -> None:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
    # head
    import math
    ang = math.atan2(y1 - y0, x1 - x0)
    ah = 6.0
    p.setBrush(QBrush(color))
    p.drawPolygon(QPolygonF([
        QPointF(x1, y1),
        QPointF(x1 - ah * math.cos(ang - 0.45),
                y1 - ah * math.sin(ang - 0.45)),
        QPointF(x1 - ah * math.cos(ang + 0.45),
                y1 - ah * math.sin(ang + 0.45)),
    ]))


# -- nav status / page icons ----------------------------------------------

@lru_cache(maxsize=64)
def nav_status_icon(defined: bool, *, group: bool = False) -> "QIcon":
    """Orange check (defined) or grey ring (undefined); folder tint for groups."""
    if not _HAS_GUI:
        return QIcon()
    pm = _pm(16)
    p = _painter(pm)
    if group:
        # small folder
        p.setBrush(QBrush(QColor(230, 190, 90) if defined else QColor(190, 190, 190)))
        p.setPen(QPen(QColor(120, 90, 40) if defined else QColor(120, 120, 120), 1))
        p.drawRoundedRect(1, 5, 14, 10, 1, 1)
        p.drawRect(1, 3, 6, 3)
    else:
        if defined:
            p.setBrush(QBrush(QColor(230, 120, 40)))
            p.setPen(QPen(QColor(180, 80, 20), 1))
            p.drawEllipse(1, 1, 14, 14)
            pen = QPen(QColor(255, 255, 255), 2)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(4, 8, 7, 11)
            p.drawLine(7, 11, 12, 5)
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(160, 160, 160), 1.5))
            p.drawEllipse(2, 2, 12, 12)
    p.end()
    return QIcon(pm)


# -- BC schematics --------------------------------------------------------

@lru_cache(maxsize=32)
def bc_icon(kind: str, size: int = 48) -> "QIcon":
    if not _HAS_GUI:
        return QIcon()
    drawers = {
        "opening": _draw_opening,
        "total_pres": _draw_total_pres,
        "pressure_loss": _draw_pressure_loss,
        "fan": _draw_fan,
        "power_law": _draw_power_law_flow,
        "freeslip": _draw_freeslip,
        "noslip": _draw_noslip,
        "rough": _draw_rough,
        "power_law_wall": _draw_power_law_wall,
        "heat_transfer": _draw_heat_transfer,
        "enclosure": _draw_enclosure,
        "radiation": _draw_radiation,
        "solar_lamp": _draw_solar_lamp,
        "symmetry": _draw_symmetry,
        "existing": _draw_existing,
        "initial_value": _draw_initial_value,
        "turb_field": _draw_turb_field,
    }
    fn = drawers.get(kind, _draw_existing)
    pm = _pm(size)
    p = _painter(pm)
    fn(p, size)
    p.end()
    return QIcon(pm)


def _draw_opening(p, size):
    _cube_face(p)
    _arrow(p, 14, 24, 28, 24)
    _arrow(p, 34, 30, 20, 30, QColor(40, 140, 230))


def _draw_total_pres(p, size):
    _cube_face(p)
    p.setPen(QPen(QColor(40, 110, 220), 1.5))
    f = QFont()
    f.setPointSize(7)
    f.setBold(True)
    p.setFont(f)
    p.drawText(4, 20, "P")
    p.drawText(4, 30, "T")
    _arrow(p, 16, 24, 36, 24)


def _draw_pressure_loss(p, size):
    _cube_face(p, face=QColor(200, 210, 230))
    # screen dots
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(120, 150, 200)))
    for i in range(4):
        for j in range(3):
            p.drawEllipse(12 + i * 6, 14 + j * 7, 3, 3)
    _arrow(p, 36, 24, 46, 24)


def _draw_fan(p, size):
    _cube_face(p)
    cx, cy = 24, 24
    p.setBrush(QBrush(QColor(60, 170, 80)))
    p.setPen(QPen(QColor(30, 110, 50), 1))
    for i in range(4):
        path = QPainterPath()
        path.moveTo(cx, cy)
        path.quadTo(cx + 10, cy - 8 + i, cx + 2, cy - 12)
        p.save()
        p.translate(cx, cy)
        p.rotate(i * 90)
        p.translate(-cx, -cy)
        p.drawEllipse(QRectF(cx - 2, cy - 12, 8, 12))
        p.restore()
    p.setBrush(QBrush(QColor(40, 120, 50)))
    p.drawEllipse(cx - 3, cy - 3, 6, 6)


def _draw_power_law_flow(p, size):
    _cube_face(p)
    for i, L in enumerate((6, 10, 14)):
        y = 16 + i * 6
        _arrow(p, 12, y, 12 + L, y, QColor(40, 110, 220), 1.6)
    f = QFont()
    f.setPointSize(5)
    p.setFont(f)
    p.setPen(QColor(40, 110, 220))
    p.drawText(10, 40, "Power law")


def _draw_wall_base(p, rough: bool = False):
    p.setBrush(QBrush(QColor(160, 160, 165)))
    p.setPen(QPen(QColor(90, 90, 95), 1.2))
    if rough:
        path = QPainterPath()
        path.moveTo(6, 34)
        for i, dy in enumerate((0, -4, 0, -3, 0, -4, 0)):
            path.lineTo(6 + i * 5.5, 34 + dy)
        path.lineTo(44, 42)
        path.lineTo(6, 42)
        path.closeSubpath()
        p.drawPath(path)
    else:
        p.drawRect(6, 34, 36, 8)


def _draw_freeslip(p, size):
    _draw_wall_base(p, False)
    for i in range(3):
        y = 12 + i * 7
        _arrow(p, 10, y, 38, y, QColor(40, 110, 220), 1.8)


def _draw_noslip(p, size):
    _draw_wall_base(p, False)
    lengths = (6, 14, 22, 30)
    for i, L in enumerate(lengths):
        y = 10 + i * 6
        _arrow(p, 10, y, 10 + L, y, QColor(40, 110, 220), 1.6)


def _draw_rough(p, size):
    _draw_wall_base(p, True)
    lengths = (6, 14, 22, 30)
    for i, L in enumerate(lengths):
        y = 8 + i * 6
        _arrow(p, 10, y, 10 + L, y, QColor(40, 110, 220), 1.6)


def _draw_power_law_wall(p, size):
    _draw_noslip(p, size)
    f = QFont()
    f.setPointSize(5)
    p.setFont(f)
    p.setPen(QColor(40, 110, 220))
    p.drawText(8, 8, "Power-law")


def _draw_heat_transfer(p, size):
    p.setBrush(QBrush(QColor(170, 170, 175)))
    p.setPen(QPen(QColor(90, 90, 95), 1.2))
    p.drawRect(8, 28, 32, 12)
    for x in (14, 24, 34):
        _arrow(p, x, 26, x, 10, QColor(220, 60, 40), 2.0)


def _draw_enclosure(p, size):
    p.setPen(QPen(QColor(90, 90, 95), 1.5))
    p.setBrush(Qt.NoBrush)
    p.drawRect(8, 8, 32, 32)
    p.setBrush(QBrush(QColor(80, 170, 90)))
    p.drawRect(16, 22, 16, 12)
    p.setPen(QPen(QColor(220, 80, 40), 1.5))
    for x in (18, 24, 30):
        path = QPainterPath()
        path.moveTo(x, 20)
        path.cubicTo(x - 2, 14, x + 2, 10, x, 6)
        p.drawPath(path)


def _draw_radiation(p, size):
    p.setBrush(QBrush(QColor(220, 50, 40)))
    p.setPen(QPen(QColor(160, 30, 20), 1))
    p.drawRect(18, 18, 12, 12)
    for ang in range(0, 360, 45):
        import math
        rad = math.radians(ang)
        _arrow(p, 24 + 8 * math.cos(rad), 24 + 8 * math.sin(rad),
               24 + 18 * math.cos(rad), 24 + 18 * math.sin(rad),
               QColor(220, 60, 40), 1.5)


def _draw_solar_lamp(p, size):
    # sun
    p.setBrush(QBrush(QColor(255, 200, 40)))
    p.setPen(QPen(QColor(200, 140, 20), 1))
    p.drawEllipse(6, 6, 14, 14)
    # lamp
    p.setBrush(QBrush(QColor(240, 220, 80)))
    p.drawEllipse(28, 8, 12, 10)
    p.setBrush(QBrush(QColor(120, 120, 120)))
    p.drawRect(32, 4, 4, 5)
    # rays to surface
    p.setBrush(QBrush(QColor(170, 170, 175)))
    p.drawRect(6, 34, 36, 8)
    for x0, x1 in ((12, 14), (20, 22), (34, 30)):
        _arrow(p, x0, 18, x1, 32, QColor(230, 160, 40), 1.4)


def _draw_symmetry(p, size):
    p.setBrush(QBrush(QColor(90, 90, 95)))
    p.setPen(Qt.NoPen)
    p.drawRect(8, 8, 16, 28)
    p.setBrush(QBrush(QColor(140, 190, 230)))
    p.drawRect(24, 8, 16, 28)
    p.setPen(QPen(QColor(30, 30, 30), 1.5))
    # double curved arrow
    path = QPainterPath()
    path.moveTo(14, 40)
    path.quadTo(24, 46, 34, 40)
    p.drawPath(path)
    _arrow(p, 12, 40, 10, 38, QColor(30, 30, 30), 1.2)
    _arrow(p, 36, 40, 38, 38, QColor(30, 30, 30), 1.2)


def _draw_existing(p, size):
    _cube_face(p, face=QColor(90, 180, 100), edge=QColor(40, 110, 50))
    # RGB axes (STpre Existing conditions glyph)
    _arrow(p, 18, 30, 34, 30, QColor(220, 50, 40), 1.8)
    _arrow(p, 18, 30, 18, 14, QColor(50, 90, 220), 1.8)
    _arrow(p, 18, 30, 28, 38, QColor(40, 160, 70), 1.6)
    p.setBrush(QBrush(QColor(255, 255, 255)))
    p.setPen(QPen(QColor(60, 60, 60), 1))
    p.drawRect(30, 12, 12, 12)
    p.drawLine(32, 16, 40, 16)
    p.drawLine(32, 19, 38, 19)


def _draw_initial_value(p, size):
    # Pale-green field with inset "?" badge (STpre Initial value).
    _cube_face(p, face=QColor(160, 210, 150), edge=QColor(70, 130, 70))
    p.setBrush(QBrush(QColor(245, 245, 245)))
    p.setPen(QPen(QColor(80, 80, 80), 1.2))
    p.drawRoundedRect(26, 22, 14, 14, 2, 2)
    f = QFont()
    f.setPointSize(8)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(60, 60, 60))
    p.drawText(QRectF(26, 22, 14, 14), Qt.AlignCenter, "?")


def _draw_turb_field(p, size):
    # Blue field + left arrow + "?" (STpre Initial turbulence field / LES).
    _cube_face(p, face=QColor(120, 170, 230), edge=QColor(50, 90, 150))
    _arrow(p, 34, 24, 14, 24, QColor(30, 70, 160), 2.2)
    p.setBrush(QBrush(QColor(245, 245, 245)))
    p.setPen(QPen(QColor(80, 80, 80), 1.2))
    p.drawRoundedRect(28, 28, 12, 12, 2, 2)
    f = QFont()
    f.setPointSize(7)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(60, 60, 60))
    p.drawText(QRectF(28, 28, 12, 12), Qt.AlignCenter, "?")


def icon_action_button(parent, label: str, icon_kind: str,
                       slot: Optional[Callable] = None,
                       *, icon_size: int = 24) -> "QPushButton":
    """Compact icon+label button for STpre New / Existing panels.

    Schematics are drawn at 48px then scaled down so buttons stay short
    and a shared column width stays consistent across long/short labels.
    """
    from PyQt5.QtCore import QSize
    btn = QPushButton(parent)
    btn.setIcon(bc_icon(icon_kind, 48))
    btn.setIconSize(QSize(icon_size, icon_size))
    btn.setText(label)
    btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    btn.setMinimumHeight(icon_size + 8)
    btn.setStyleSheet(
        "QPushButton { text-align: left; padding: 2px 6px; "
        "border: 1px solid #bbb; border-radius: 3px; background: #f7f7f7; }"
        "QPushButton:hover { background: #e8f0ff; border-color: #7aa; }"
        "QPushButton:pressed { background: #d0e0f8; }"
        "QPushButton:disabled { color: #999; background: #f0f0f0; }"
    )
    if slot is not None:
        btn.clicked.connect(slot)
    return btn


# -- Initial Wizard purpose schematics -----------------------------------

@lru_cache(maxsize=16)
def purpose_icon(kind: str, size: int = 64) -> "QIcon":
    """Schematic icons for Initial Wizard Purpose of Analysis radios."""
    if not _HAS_GUI:
        return QIcon()
    drawers = {
        "none": _draw_purpose_none,
        "internal_enclosure": _draw_purpose_enclosure,
        "external_natural": _draw_purpose_natural,
        "external_forced": _draw_purpose_forced,
        "external_buildings": _draw_purpose_buildings,
    }
    fn = drawers.get(kind, _draw_purpose_none)
    pm = _pm(size)
    p = _painter(pm)
    fn(p, size)
    p.end()
    return QIcon(pm)


def _draw_purpose_none(p, size):
    _cube_face(p, x=12, y=14, w=28, h=24,
               face=QColor(200, 200, 205), edge=QColor(120, 120, 125))
    f = QFont()
    f.setPointSize(10)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(100, 100, 100))
    p.drawText(QRectF(8, 8, size - 16, size - 16), Qt.AlignCenter, "?")


def _draw_purpose_forced(p, size):
    _cube_face(p, x=10, y=12, w=30, h=26)
    _arrow(p, 8, 24, 22, 24, QColor(40, 110, 220), 2.5)
    _arrow(p, 36, 28, 24, 28, QColor(40, 140, 230), 2.0)


def _draw_purpose_natural(p, size):
    _cube_face(p, x=10, y=18, w=30, h=22)
    for x in (16, 24, 32):
        path = QPainterPath()
        path.moveTo(x, 36)
        path.cubicTo(x - 3, 28, x + 3, 20, x, 10)
        p.setPen(QPen(QColor(220, 80, 40), 1.5))
        p.drawPath(path)
    p.setPen(QPen(QColor(40, 110, 220), 1.5))
    p.drawLine(12, 40, 38, 40)


def _draw_purpose_enclosure(p, size):
    p.setPen(QPen(QColor(90, 90, 95), 1.5))
    p.setBrush(Qt.NoBrush)
    p.drawRect(10, 10, 34, 34)
    p.setBrush(QBrush(QColor(80, 170, 90)))
    p.drawRect(18, 24, 18, 14)
    p.setPen(QPen(QColor(220, 80, 40), 1.5))
    for x in (20, 28, 36):
        path = QPainterPath()
        path.moveTo(x, 22)
        path.cubicTo(x - 2, 16, x + 2, 12, x, 8)
        p.drawPath(path)


def _draw_purpose_buildings(p, size):
    p.setBrush(QBrush(QColor(170, 170, 175)))
    p.setPen(QPen(QColor(90, 90, 95), 1))
    for x, h in ((8, 22), (18, 30), (28, 18), (38, 26)):
        p.drawRect(x, 42 - h, 8, h)
    _arrow(p, 4, 24, 18, 24, QColor(40, 110, 220), 2.2)
    for i, L in enumerate((4, 8, 12)):
        y = 8 + i * 4
        _arrow(p, 44, y, 44 + L, y, QColor(40, 110, 220), 1.4)


# -- Initial Wizard Analysis Type toggles --------------------------------

@lru_cache(maxsize=32)
def iwiz_atype_icon(kind: str, size: int = 48) -> "QIcon":
    """Beautified schematics for Analysis Type Solve/Ignore pairs."""
    if not _HAS_GUI:
        return QIcon()
    drawers = {
        "flow_solve": _draw_atype_flow_solve,
        "flow_nosolve": _draw_atype_flow_nosolve,
        "laminar": _draw_atype_laminar,
        "turbulent": _draw_atype_turbulent,
        "heat_solve": _draw_atype_heat_solve,
        "heat_nosolve": _draw_atype_heat_nosolve,
        "rad_consider": _draw_atype_rad_consider,
        "rad_ignore": _draw_atype_rad_ignore,
        "solar_consider": _draw_atype_solar_consider,
        "solar_ignore": _draw_atype_solar_ignore,
    }
    fn = drawers.get(kind)
    if fn is None:
        return QIcon()
    pm = _pm(size)
    p = _painter(pm)
    # soft tile background
    p.setBrush(QBrush(QColor(248, 250, 252)))
    p.setPen(QPen(QColor(210, 218, 228), 1))
    p.drawRoundedRect(1, 1, size - 2, size - 2, 6, 6)
    fn(p, size)
    p.end()
    return QIcon(pm)


def _draw_atype_flow_solve(p, size):
    # Stepped solid + streaming arrows
    p.setBrush(QBrush(QColor(150, 155, 165)))
    p.setPen(QPen(QColor(90, 95, 105), 1))
    p.drawRect(8, 30, 32, 8)
    p.drawRect(8, 22, 14, 8)
    for y in (12, 18, 26):
        _arrow(p, 18, y, 40, y, QColor(45, 120, 220), 2.0)


def _draw_atype_flow_nosolve(p, size):
    p.setBrush(QBrush(QColor(150, 155, 165)))
    p.setPen(QPen(QColor(90, 95, 105), 1))
    p.drawRect(8, 30, 32, 8)
    p.drawRect(8, 22, 14, 8)
    p.setBrush(QBrush(QColor(90, 160, 230, 160)))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(20, 10, 18, 20, 3, 3)


def _draw_atype_laminar(p, size):
    # Tap + smooth stream
    p.setBrush(QBrush(QColor(120, 125, 135)))
    p.setPen(QPen(QColor(70, 75, 85), 1))
    p.drawRoundedRect(14, 8, 16, 8, 2, 2)
    p.drawRect(20, 14, 6, 6)
    p.setBrush(QBrush(QColor(70, 150, 230)))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(21, 20, 4, 20, 2, 2)


def _draw_atype_turbulent(p, size):
    p.setBrush(QBrush(QColor(120, 125, 135)))
    p.setPen(QPen(QColor(70, 75, 85), 1))
    p.drawRoundedRect(14, 8, 16, 8, 2, 2)
    p.drawRect(20, 14, 6, 6)
    p.setBrush(QBrush(QColor(70, 150, 230)))
    p.setPen(Qt.NoPen)
    # Deterministic spray droplets
    for x, y, r in (
            (18, 24, 3), (24, 22, 2), (28, 26, 3), (20, 30, 2),
            (26, 32, 3), (22, 36, 2), (30, 34, 2), (17, 34, 2)):
        p.drawEllipse(x, y, r, r)


def _draw_atype_heat_solve(p, size):
    # Thermometer
    p.setPen(QPen(QColor(80, 80, 90), 1.5))
    p.setBrush(QBrush(QColor(240, 240, 245)))
    p.drawRoundedRect(20, 6, 8, 28, 4, 4)
    p.setBrush(QBrush(QColor(220, 60, 50)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(17, 30, 14, 14)
    p.drawRoundedRect(22, 18, 4, 18, 2, 2)


def _draw_atype_heat_nosolve(p, size):
    _draw_atype_heat_solve(p, size)
    pen = QPen(QColor(210, 40, 40), 3.0)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(10, 10, 38, 38)
    p.drawLine(38, 10, 10, 38)


def _draw_atype_rad_consider(p, size):
    p.setBrush(QBrush(QColor(220, 55, 45)))
    p.setPen(QPen(QColor(160, 30, 25), 1))
    p.drawRoundedRect(18, 18, 12, 12, 2, 2)
    import math
    for ang in range(0, 360, 45):
        rad = math.radians(ang)
        _arrow(p, 24 + 9 * math.cos(rad), 24 + 9 * math.sin(rad),
               24 + 18 * math.cos(rad), 24 + 18 * math.sin(rad),
               QColor(230, 120, 40), 1.6)


def _draw_atype_rad_ignore(p, size):
    p.setBrush(QBrush(QColor(220, 55, 45)))
    p.setPen(QPen(QColor(160, 30, 25), 1))
    p.drawRoundedRect(18, 18, 12, 12, 2, 2)


def _draw_atype_solar_consider(p, size):
    # Sun
    p.setBrush(QBrush(QColor(255, 190, 50)))
    p.setPen(QPen(QColor(210, 140, 30), 1))
    p.drawEllipse(8, 6, 14, 14)
    import math
    for ang in range(0, 360, 45):
        rad = math.radians(ang)
        p.drawLine(QPointF(15 + 8 * math.cos(rad), 13 + 8 * math.sin(rad)),
                   QPointF(15 + 11 * math.cos(rad), 13 + 11 * math.sin(rad)))
    # Surface + rays
    p.setBrush(QBrush(QColor(90, 170, 170)))
    p.setPen(QPen(QColor(50, 120, 120), 1))
    p.drawRect(8, 36, 32, 6)
    for x0, x1 in ((14, 16), (22, 24), (32, 30)):
        _arrow(p, x0, 20, x1, 34, QColor(230, 140, 40), 1.5)


def _draw_atype_solar_ignore(p, size):
    p.setBrush(QBrush(QColor(255, 190, 50)))
    p.setPen(QPen(QColor(210, 140, 30), 1))
    p.drawEllipse(8, 6, 14, 14)
    import math
    for ang in range(0, 360, 45):
        rad = math.radians(ang)
        p.drawLine(QPointF(15 + 8 * math.cos(rad), 13 + 8 * math.sin(rad)),
                   QPointF(15 + 11 * math.cos(rad), 13 + 11 * math.sin(rad)))
    p.setBrush(QBrush(QColor(90, 170, 170)))
    p.setPen(QPen(QColor(50, 120, 120), 1))
    p.drawRect(8, 36, 32, 6)


def action_column(parent, *, width: int = 220) -> "QWidget":
    """Fixed-width column so New / Existing buttons share one edge."""
    if not _HAS_GUI:
        return None  # type: ignore[return-value]
    col = QWidget(parent)
    col.setFixedWidth(width)
    col.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
    return col
