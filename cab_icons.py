"""QPainter vector icons for cab_gui (ported/adapted from pph_gui.AppIcons)."""

from __future__ import annotations

import math

from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap,
    QPolygon,
)


class AppIcons:
    """Lightweight vector icons for toolbars / trees."""

    _cache: dict[tuple, QIcon] = {}

    @classmethod
    def get(cls, name: str, size: int = 20) -> QIcon:
        key = (name, size)
        if key not in cls._cache:
            cls._cache[key] = QIcon(cls._paint(name, size))
        return cls._cache[key]

    @classmethod
    def _paint(cls, name: str, size: int) -> QPixmap:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        m = max(1, size // 10)
        r = QRectF(m, m, size - 2 * m, size - 2 * m)
        drawer = getattr(cls, f"_draw_{name}", None)
        if drawer:
            drawer(p, r, size)
        else:
            cls._draw_generic(p, r)
        p.end()
        return pm

    @staticmethod
    def _pen(color, w=1.6):
        pen = QPen(QColor(color))
        pen.setWidthF(w)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        return pen

    @classmethod
    def _draw_generic(cls, p, r, _s=0):
        p.setPen(cls._pen("#555"))
        p.setBrush(QBrush(QColor("#dde3ea")))
        p.drawRoundedRect(r, 3, 3)

    @classmethod
    def _draw_open(cls, p, r, _s):
        p.setPen(cls._pen("#2e75b6", 1.4))
        p.setBrush(QBrush(QColor("#f4c542")))
        tab = QRectF(r.left(), r.top(), r.width() * 0.45, r.height() * 0.28)
        p.drawRoundedRect(tab, 2, 2)
        body = QRectF(r.left(), r.top() + r.height() * 0.22,
                      r.width(), r.height() * 0.72)
        p.setBrush(QBrush(QColor("#ffd966")))
        p.drawRoundedRect(body, 2, 2)

    @classmethod
    def _draw_save(cls, p, r, _s):
        p.setPen(cls._pen("#1f4e79", 1.3))
        p.setBrush(QBrush(QColor("#5b9bd5")))
        p.drawRoundedRect(r, 2, 2)
        p.setBrush(QBrush(QColor("#fff")))
        slot = QRectF(r.left() + r.width() * 0.22, r.top(),
                      r.width() * 0.56, r.height() * 0.38)
        p.drawRect(slot)
        p.setBrush(QBrush(QColor("#eaf2fb")))
        label = QRectF(r.left() + r.width() * 0.18,
                       r.top() + r.height() * 0.48,
                       r.width() * 0.64, r.height() * 0.42)
        p.drawRoundedRect(label, 1, 1)

    @classmethod
    def _draw_reload(cls, p, r, _s):
        p.setPen(cls._pen("#2e7d32", 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawArc(r.toRect(), 40 * 16, 280 * 16)
        cx, cy = r.center().x(), r.center().y()
        tip = QPolygon([
            QPoint(int(cx + r.width() * 0.42), int(cy - r.height() * 0.05)),
            QPoint(int(cx + r.width() * 0.18), int(cy - r.height() * 0.38)),
            QPoint(int(cx + r.width() * 0.48), int(cy - r.height() * 0.32)),
        ])
        p.setBrush(QBrush(QColor("#2e7d32")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tip)

    @classmethod
    def _draw_export(cls, p, r, _s):
        p.setPen(cls._pen("#37474f", 1.3))
        p.setBrush(QBrush(QColor("#cfd8dc")))
        p.drawRoundedRect(r.adjusted(0, 0, -r.width() * 0.25, 0), 2, 2)
        p.setPen(cls._pen("#1565c0", 2.0))
        cx = r.right() - r.width() * 0.18
        p.drawLine(QPointF(cx, r.top() + 2), QPointF(cx, r.bottom() - 2))
        tip = QPolygon([
            QPoint(int(cx), int(r.bottom() - 1)),
            QPoint(int(cx - r.width() * 0.18), int(r.bottom() - r.height() * 0.35)),
            QPoint(int(cx + r.width() * 0.18), int(r.bottom() - r.height() * 0.35)),
        ])
        p.setBrush(QBrush(QColor("#1565c0")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tip)

    @classmethod
    def _draw_part(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 1.4))
        p.setBrush(QBrush(QColor("#90caf9")))
        pts = QPolygon([
            QPoint(int(r.left() + r.width() * 0.2), int(r.bottom())),
            QPoint(int(r.left() + r.width() * 0.5), int(r.top())),
            QPoint(int(r.right()), int(r.bottom() - r.height() * 0.15)),
            QPoint(int(r.left() + r.width() * 0.55),
                   int(r.bottom() - r.height() * 0.05)),
        ])
        p.drawPolygon(pts)

    @classmethod
    def _draw_mesh(cls, p, r, _s):
        p.setPen(cls._pen("#00838f", 1.2))
        p.setBrush(QBrush(QColor("#80deea")))
        p.drawEllipse(r)
        p.setPen(cls._pen("#006064", 1.0))
        cx, cy = r.center().x(), r.center().y()
        for ang in (0, 60, 120):
            a = math.radians(ang)
            x = cx + math.cos(a) * r.width() * 0.42
            y = cy + math.sin(a) * r.height() * 0.42
            p.drawLine(QPointF(cx, cy), QPointF(x, y))

    @classmethod
    def _draw_fit(cls, p, r, _s):
        p.setPen(cls._pen("#37474f", 1.6))
        p.setBrush(Qt.NoBrush)
        s = r.width() * 0.28
        corners = [
            (r.left(), r.top(), 1, 1),
            (r.right(), r.top(), -1, 1),
            (r.left(), r.bottom(), 1, -1),
            (r.right(), r.bottom(), -1, -1),
        ]
        for x, y, sx, sy in corners:
            p.drawLine(QPoint(int(x), int(y)), QPoint(int(x + sx * s), int(y)))
            p.drawLine(QPoint(int(x), int(y)), QPoint(int(x), int(y + sy * s)))
        p.setBrush(QBrush(QColor("#90a4ae")))
        p.drawEllipse(r.adjusted(r.width() * 0.28, r.height() * 0.28,
                                 -r.width() * 0.28, -r.height() * 0.28))

    @classmethod
    def _draw_show_all(cls, p, r, _s):
        p.setPen(cls._pen("#ef6c00", 1.3))
        p.setBrush(QBrush(QColor("#ffe0b2")))
        p.drawEllipse(r.adjusted(r.width() * 0.15, r.height() * 0.2,
                                 -r.width() * 0.15, -r.height() * 0.15))
        p.setBrush(QBrush(QColor("#fff")))
        eye = QRectF(r.center().x() - r.width() * 0.12,
                     r.center().y() - r.height() * 0.08,
                     r.width() * 0.24, r.height() * 0.24)
        p.drawEllipse(eye)
        p.setBrush(QBrush(QColor("#333")))
        p.drawEllipse(eye.adjusted(eye.width() * 0.3, eye.height() * 0.3,
                                   -eye.width() * 0.3, -eye.height() * 0.3))

    @classmethod
    def _draw_display(cls, p, r, _s):
        p.setPen(cls._pen("#5d4037", 1.2))
        p.setBrush(QBrush(QColor(100, 149, 237, 120)))
        p.drawEllipse(r)
        p.setBrush(QBrush(QColor("#5c6bc0")))
        p.drawEllipse(r.adjusted(r.width() * 0.35, r.height() * 0.35,
                                 -r.width() * 0.05, -r.height() * 0.05))

    @classmethod
    def _draw_folder(cls, p, r, _s):
        cls._draw_open(p, r, _s)

    @classmethod
    def _draw_group(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 1.2))
        p.setBrush(QBrush(QColor("#bbdefb")))
        p.drawRoundedRect(r, 3, 3)
        p.setPen(cls._pen("#0d47a1", 1.4))
        p.drawText(r.toRect(), Qt.AlignCenter, "G")

    @classmethod
    def _draw_region(cls, p, r, _s):
        p.setPen(cls._pen("#2e7d32", 1.3))
        p.setBrush(QBrush(QColor("#81c784")))
        cx, cy = r.center().x(), r.center().y()
        w, h = r.width() * 0.42, r.height() * 0.42
        poly = QPolygon([
            QPoint(int(cx), int(cy - h)),
            QPoint(int(cx + w), int(cy)),
            QPoint(int(cx), int(cy + h)),
            QPoint(int(cx - w), int(cy)),
        ])
        p.drawPolygon(poly)

    @classmethod
    def _draw_surface(cls, p, r, _s):
        """STpre DomainBoundary / Region face — light-blue parallelogram."""
        p.setPen(cls._pen("#0277bd", 1.2))
        p.setBrush(QBrush(QColor("#81d4fa")))
        poly = QPolygon([
            QPoint(int(r.left() + r.width() * 0.08), int(r.bottom() - 1)),
            QPoint(int(r.left() + r.width() * 0.35), int(r.top() + 1)),
            QPoint(int(r.right() - 1), int(r.top() + 1)),
            QPoint(int(r.right() - r.width() * 0.27), int(r.bottom() - 1)),
        ])
        p.drawPolygon(poly)

    @classmethod
    def _draw_project(cls, p, r, _s):
        p.setPen(cls._pen("#455a64", 1.2))
        p.setBrush(QBrush(QColor("#cfd8dc")))
        p.drawRoundedRect(r, 2, 2)
        p.setPen(cls._pen("#263238", 1.0))
        for i in range(3):
            y = r.top() + r.height() * (0.28 + i * 0.22)
            p.drawLine(QPoint(int(r.left() + 3), int(y)),
                       QPoint(int(r.right() - 3), int(y)))

    @classmethod
    def _draw_xml(cls, p, r, _s):
        p.setPen(cls._pen("#bf360c", 1.2))
        p.setBrush(QBrush(QColor("#ffccbc")))
        p.drawRoundedRect(r, 2, 2)
        p.setPen(cls._pen("#bf360c", 1.3))
        p.setFont(QFont("Consolas", max(6, int(r.height() * 0.4))))
        p.drawText(r.toRect(), Qt.AlignCenter, "<>")

    @classmethod
    def _draw_domain(cls, p, r, _s):
        p.setPen(cls._pen("#00838f", 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(1, 1, -1, -1))
        p.setPen(cls._pen("#00acc1", 1.0))
        p.drawLine(QPoint(int(r.left()), int(r.center().y())),
                   QPoint(int(r.right()), int(r.center().y())))
        p.drawLine(QPoint(int(r.center().x()), int(r.top())),
                   QPoint(int(r.center().x()), int(r.bottom())))

    @classmethod
    def _draw_condition(cls, p, r, _s):
        p.setPen(cls._pen("#6a1b9a", 1.2))
        p.setBrush(QBrush(QColor("#e1bee7")))
        p.drawRoundedRect(r, 2, 2)
        p.setPen(cls._pen("#4a148c", 1.5))
        p.setFont(QFont("Consolas", max(6, int(r.height() * 0.4))))
        p.drawText(r.toRect(), Qt.AlignCenter, "C")

    @classmethod
    def _draw_library(cls, p, r, _s):
        p.setPen(cls._pen("#5d4037", 1.2))
        p.setBrush(QBrush(QColor("#d7ccc8")))
        p.drawRoundedRect(r, 2, 2)
        p.setBrush(QBrush(QColor("#8d6e63")))
        for i in range(3):
            y = r.top() + r.height() * (0.2 + i * 0.25)
            p.drawRect(QRectF(r.left() + 3, y, r.width() - 6, r.height() * 0.12))

    @classmethod
    def _draw_cube(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 1.2))
        p.setBrush(QBrush(QColor("#90caf9")))
        p.drawRect(r.adjusted(r.width() * 0.15, r.height() * 0.25,
                              -r.width() * 0.05, -r.height() * 0.05))
        p.setBrush(QBrush(QColor("#64b5f6")))
        top = QPolygon([
            QPoint(int(r.left() + r.width() * 0.15), int(r.top() + r.height() * 0.25)),
            QPoint(int(r.left() + r.width() * 0.35), int(r.top() + r.height() * 0.05)),
            QPoint(int(r.right() - r.width() * 0.05), int(r.top() + r.height() * 0.05)),
            QPoint(int(r.right() - r.width() * 0.05), int(r.top() + r.height() * 0.25)),
        ])
        p.drawPolygon(top)

    @classmethod
    def _draw_cylinder(cls, p, r, _s):
        p.setPen(cls._pen("#00695c", 1.2))
        p.setBrush(QBrush(QColor("#80cbc4")))
        p.drawEllipse(QRectF(r.left() + 2, r.top(), r.width() - 4, r.height() * 0.28))
        p.drawRect(QRectF(r.left() + 2, r.top() + r.height() * 0.14,
                          r.width() - 4, r.height() * 0.6))
        p.drawEllipse(QRectF(r.left() + 2, r.bottom() - r.height() * 0.28,
                             r.width() - 4, r.height() * 0.28))

    @classmethod
    def _draw_sphere(cls, p, r, _s):
        p.setPen(cls._pen("#ad1457", 1.2))
        p.setBrush(QBrush(QColor("#f48fb1")))
        p.drawEllipse(r)

    @classmethod
    def _draw_panel(cls, p, r, _s):
        p.setPen(cls._pen("#ef6c00", 1.2))
        p.setBrush(QBrush(QColor("#ffcc80")))
        p.drawRoundedRect(r.adjusted(1, r.height() * 0.3, -1, -r.height() * 0.3), 2, 2)

    @classmethod
    def _draw_select(cls, p, r, _s):
        p.setPen(cls._pen("#37474f", 1.4))
        path = QPainterPath()
        path.moveTo(r.left() + 2, r.top() + 2)
        path.lineTo(r.left() + 2, r.bottom() - 2)
        path.lineTo(r.left() + r.width() * 0.35, r.top() + r.height() * 0.55)
        path.lineTo(r.left() + r.width() * 0.55, r.bottom() - 2)
        path.lineTo(r.right() - 2, r.top() + r.height() * 0.35)
        path.closeSubpath()
        p.setBrush(QBrush(QColor("#eceff1")))
        p.drawPath(path)

    @classmethod
    def _draw_rotate(cls, p, r, _s):
        p.setPen(cls._pen("#1565c0", 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawArc(r.toRect(), 30 * 16, 300 * 16)

    @classmethod
    def _draw_pan(cls, p, r, _s):
        p.setPen(cls._pen("#455a64", 1.6))
        cx, cy = r.center().x(), r.center().y()
        p.drawLine(QPoint(int(r.left() + 2), int(cy)), QPoint(int(r.right() - 2), int(cy)))
        p.drawLine(QPoint(int(cx), int(r.top() + 2)), QPoint(int(cx), int(r.bottom() - 2)))

    @classmethod
    def _draw_zoom(cls, p, r, _s):
        p.setPen(cls._pen("#37474f", 1.4))
        p.setBrush(Qt.NoBrush)
        circ = r.adjusted(0, 0, -r.width() * 0.25, -r.height() * 0.25)
        p.drawEllipse(circ)
        p.drawLine(QPoint(int(circ.right() - 1), int(circ.bottom() - 1)),
                   QPoint(int(r.right() - 1), int(r.bottom() - 1)))

    @classmethod
    def _draw_plane_xy(cls, p, r, _s):
        cls._draw_plane(p, r, "XY")

    @classmethod
    def _draw_plane_xz(cls, p, r, _s):
        cls._draw_plane(p, r, "XZ")

    @classmethod
    def _draw_plane_yz(cls, p, r, _s):
        cls._draw_plane(p, r, "YZ")

    @classmethod
    def _draw_plane(cls, p, r, label):
        p.setPen(cls._pen("#546e7a", 1.2))
        p.setBrush(QBrush(QColor("#eceff1")))
        p.drawRect(r.adjusted(2, 2, -2, -2))
        p.setPen(cls._pen("#263238", 1.0))
        p.setFont(QFont("Arial", max(6, int(r.height() * 0.35))))
        p.drawText(r.toRect(), Qt.AlignCenter, label)
