"""P4: PyQt5 + VTK viewer/editor for scSTREAM Pre cab project files.

Four-pane layout following the scSTREAM Pre manual (Navigation / Tree /
Property / Draw windows):

- Navigation: open / save-as (rebuild cab) / export .s+.xemt / reload,
  plus a file info card and a grouped navigation tree;
- Tree: project model tree (groups/parts/regions/values/conditions/mesh/
  material library) and a visibility model tree with checkboxes;
- Property: structured, editable metadata for the selected item
  (part name / material / color), applied back to the XML model;
- Draw: 3D view of part boxes (mesh-derived bounds) + domain frame with
  shade/wireframe, fit/reset.
"""

from __future__ import annotations

import os
import sys

import cab_vtk
import xemt_export
from cab_container import CabArchive
from cabxml import (PropertyModel, StpreModel, parse_property, parse_stpre)
from s_export import build_sdat

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
    import vtk
    _HAS_GUI_DEPS = True
except Exception as e:  # pragma: no cover - headless environments
    _HAS_GUI_DEPS = False
    QtWidgets = None


class CabViewer(QtWidgets.QMainWindow if _HAS_GUI_DEPS else object):
    """Main window: load / browse / edit / export / rebuild a cab file."""

    def __init__(self, path: str | None = None, enable_3d: bool = True):
        if not _HAS_GUI_DEPS:
            raise RuntimeError("PyQt5/vtk not installed")
        super().__init__()
        self.setWindowTitle("cabdecoding - scSTREAM Pre cab viewer")
        self.resize(1280, 820)
        self._enable_3d = enable_3d
        self.archive: CabArchive | None = None
        self.model: StpreModel | None = None
        self.props: PropertyModel | None = None
        self.actors: list[tuple[vtk.vtkActor, str]] = []
        self.current_path: str | None = None
        self._wireframe = False

        self._build_ui()
        if path:
            self.load(path)

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        nav = QtWidgets.QDockWidget("Navigation", self)
        nav.setObjectName("nav")
        nav.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable)
        self._nav = QtWidgets.QWidget()
        nav.setWidget(self._nav)
        nav_layout = QtWidgets.QVBoxLayout(self._nav)
        nav_layout.setContentsMargins(6, 6, 6, 6)

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.act_open = QtWidgets.QAction("打开", self)
        self.act_open.triggered.connect(self._open_dialog)
        self.act_save = QtWidgets.QAction("另存为(cab)", self)
        self.act_save.triggered.connect(self._save_dialog)
        self.act_export = QtWidgets.QAction("导出 .s/.xemt", self)
        self.act_export.triggered.connect(self._export_dialog)
        self.act_fit = QtWidgets.QAction("Fit", self)
        self.act_fit.triggered.connect(self._fit_view)
        self.act_wire = QtWidgets.QAction("线框", self)
        self.act_wire.setCheckable(True)
        self.act_wire.toggled.connect(self._set_wireframe)
        for a in (self.act_open, self.act_save, self.act_export,
                  self.act_fit, self.act_wire):
            toolbar.addAction(a)
        nav_layout.addWidget(toolbar)

        self.info_label = QtWidgets.QLabel("未打开文件")
        self.info_label.setWordWrap(True)
        nav_layout.addWidget(self.info_label)

        self.nav_tree = QtWidgets.QTreeWidget()
        self.nav_tree.setHeaderLabels(["项目"])
        self.nav_tree.itemClicked.connect(self._on_tree_click)
        nav_layout.addWidget(self.nav_tree)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, nav)

        tree_dock = QtWidgets.QDockWidget("Model Tree", self)
        tree_dock.setObjectName("tree")
        self.model_tree = QtWidgets.QTreeWidget()
        self.model_tree.setHeaderLabels(["部件 / 显隐"])
        self.model_tree.itemChanged.connect(self._on_visibility_changed)
        tree_dock.setWidget(self.model_tree)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, tree_dock)

        prop_dock = QtWidgets.QDockWidget("Property", self)
        prop_dock.setObjectName("prop")
        self.prop_widget = QtWidgets.QWidget()
        self.prop_layout = QtWidgets.QFormLayout(self.prop_widget)
        self.prop_title = QtWidgets.QLabel("选择树节点查看属性")
        self.prop_layout.addRow(self.prop_title)
        self.prop_fields: dict[str, QtWidgets.QLineEdit] = {}
        self.apply_btn = QtWidgets.QPushButton("应用修改")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply_edits)
        prop_dock.setWidget(self.prop_widget)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, prop_dock)

        if self._enable_3d:
            self.vtk_widget = QVTKRenderWindowInteractor(self)
            self.setCentralWidget(self.vtk_widget)
            self.renderer = vtk.vtkRenderer()
            self.renderer.SetBackground(0.93, 0.94, 0.95)
            self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
            self.vtk_widget.GetRenderWindow().SetSize(900, 700)
        else:
            self.vtk_widget = None
            self.renderer = None
            self.setCentralWidget(QtWidgets.QLabel(
                "3D 视图已禁用（headless 测试模式）", self))

        self.status = self.statusBar()
        self.status.showMessage("就绪")

    # ------------------------------------------------------------ loading

    def load(self, path: str) -> bool:
        try:
            raw = open(path, "rb").read()
            archive = CabArchive.parse(raw)
            archive.fill_member_data()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "打开失败", str(exc))
            return False
        self.archive = archive
        self.current_path = path
        members = {m.name: m.data for m in archive.members}
        self.model = StpreModel(parse_stpre(members["ex4_e.xml"]))
        self.props = PropertyModel(parse_property(
            members["_ex4_e_property.xml"]))
        self._populate_nav()
        self._populate_model_tree()
        self._rebuild_scene()
        info = (f"{os.path.basename(path)}  "
                f"{len(raw):,} B  v{archive.version_minor}."
                f"{archive.version_major}\n"
                f"成员 {len(archive.members)} 个 | 部件 "
                f"{len(self.model.parts())} 个 | 材料 "
                f"{len(self.props.material_names())} 个")
        self.info_label.setText(info)
        self.status.showMessage(f"已加载 {path}")
        return True

    def _populate_nav(self):
        tree = self.nav_tree
        tree.clear()
        root = QtWidgets.QTreeWidgetItem([self.model.project_name])
        tree.addTopLevelItem(root)

        def add(parent, label, data):
            item = QtWidgets.QTreeWidgetItem([label])
            item.setData(0, QtCore.Qt.UserRole, data)
            parent.addChild(item)
            return item

        proj = add(root, "项目", ("project", None))
        add(proj, f"注释: {self.model.project_name}", ("project", None))
        groups = add(root, f"部件组 ({len(self.model.groups())})",
                     ("groups", None))
        for grp in self.model.groups():
            gname = ""
            for ch in grp:
                if ch.tag == "name":
                    gname = (ch.text or "").strip()
            g = add(groups, gname, ("group", gname))
            for p in self.model.parts():
                if p.group == gname:
                    add(g, f"{p.name}  [{p.property}]",
                        ("part", p.name))
        regions = add(root, f"边界区域 ({len(self.model.regions())})",
                      ("regions", None))
        for r in self.model.regions():
            for ch in r:
                if ch.tag == "name":
                    add(regions, (ch.text or "").strip(), ("region", None))
        add(root, f"条件值 ({len(self.model.values())})",
            ("values", None))
        add(root, "求解设置", ("analysis_set", None))
        add(root, f"材料库 ({len(self.props.material_names())})",
            ("materials", None))
        root.setExpanded(True)

    def _populate_model_tree(self):
        tree = self.model_tree
        tree.blockSignals(True)
        tree.clear()
        for p in self.model.parts():
            item = QtWidgets.QTreeWidgetItem([p.name])
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.Checked)
            item.setData(0, QtCore.Qt.UserRole, ("part", p.name))
            tree.addTopLevelItem(item)
        tree.blockSignals(False)

    # ------------------------------------------------------------- events

    def _on_tree_click(self, item, _col):
        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return
        kind, name = data
        self._show_property(kind, name)

    def _show_property(self, kind: str, name: str | None):
        for w in self.prop_fields.values():
            w.deleteLater()
        self.prop_fields.clear()
        while self.prop_layout.rowCount():
            self.prop_layout.removeRow(0)
        self.prop_title = QtWidgets.QLabel()
        self.prop_layout.addRow(self.prop_title)
        self._prop_target = (kind, name)

        def field(label, value, ro=False):
            edit = QtWidgets.QLineEdit(value)
            edit.setReadOnly(ro)
            self.prop_layout.addRow(label, edit)
            self.prop_fields[label] = edit

        if kind == "part" and name:
            part = None
            for p in self.model.parts():
                if p.name == name:
                    part = p
                    break
            if part is None:
                return
            self.prop_title.setText(f"部件: {name}")
            field("名称", part.name)
            field("材料", part.property)
            field("类型", part.kind, ro=True)
            field("属性", part.attribute, ro=True)
            field("颜色 RGBA", part.color)
            field("体积", part.volume, ro=True)
            self.apply_btn.setEnabled(True)
            self.prop_layout.addRow(self.apply_btn)
        elif kind == "project":
            self.prop_title.setText("项目")
            field("名称", self.model.project_name, ro=True)
        elif kind == "materials":
            self.prop_title.setText("材料库")
            for mat in self.props.material_names():
                field(mat, "", ro=True)
        else:
            self.prop_title.setText(kind)
            self.apply_btn.setEnabled(False)

    def _apply_edits(self):
        kind, name = self._prop_target
        if kind != "part" or not name:
            return
        new_name = self.prop_fields["名称"].text().strip()
        material = self.prop_fields["材料"].text().strip()
        color = self.prop_fields["颜色 RGBA"].text().strip()
        changed = False
        if new_name and new_name != name:
            changed = self.model.rename_part(name, new_name) or changed
        if material:
            changed = self.model.set_part_property(
                new_name or name, material) or changed
        if color:
            parts = [int(x) for x in color.split(",")[:4]] \
                if all(x.strip().isdigit() for x in color.split(",")[:4]) \
                else None
            if parts and len(parts) == 4:
                changed = self.model.set_part_color(
                    new_name or name, tuple(parts)) or changed
        if changed:
            self._populate_nav()
            self._populate_model_tree()
            self.status.showMessage("已应用修改（另存为 cab 生效）")

    def _on_visibility_changed(self, item, _col):
        data = item.data(0, QtCore.Qt.UserRole)
        if not data or data[0] != "part":
            return
        visible = item.checkState(0) == QtCore.Qt.Checked
        if self._enable_3d:
            for actor, pname in self.actors:
                if pname == data[1]:
                    actor.SetVisibility(1 if visible else 0)
            self.renderer.GetRenderWindow().Render()

    # ---------------------------------------------------------------- 3D

    def _rebuild_scene(self):
        if not self._enable_3d:
            return
        self.renderer.RemoveAllViewProps()
        self.actors.clear()
        boxes = cab_vtk.part_boxes(self.model)
        frame = cab_vtk.domain_frame(self.model)
        if frame:
            boxes.append(frame)
        for box in boxes:
            pd = cab_vtk._make_box_polydata(box, wireframe=self._wireframe)
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(pd)
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*box.color)
            actor.GetProperty().SetOpacity(box.opacity)
            actor.SetVisibility(1)
            self.renderer.AddActor(actor)
            self.actors.append((actor, box.name))
        self._fit_view()

    def _set_wireframe(self, on: bool):
        self._wireframe = on
        if self.model is None:
            return
        self._rebuild_scene()

    def _fit_view(self):
        if not self._enable_3d:
            return
        self.renderer.ResetCamera()
        self.renderer.GetRenderWindow().Render()

    # ------------------------------------------------------------ actions

    def _open_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "打开 cab", "", "scSTREAM project (*.cab);;All (*)")
        if path:
            self.load(path)

    def _save_dialog(self):
        if self.model is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "另存为 cab", "", "scSTREAM project (*.cab)")
        if not path:
            return
        self._rebuild_to(path)

    def _rebuild_to(self, path: str) -> bool:
        member = next(m for m in self.archive.members
                      if m.name == "ex4_e.xml")
        member.data = self.model.doc.serialize()
        data = self.archive.to_bytes(preserve_source_blocks=False)
        with open(path, "wb") as fh:
            fh.write(data)
        self.status.showMessage(f"已重建 {path} ({len(data):,} B)")
        return True

    def _export_dialog(self):
        if self.model is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出 S/XEMT 基名", self.model.project_name, "")
        if not path:
            return
        base = path.rsplit(".", 1)[0]
        with open(base + ".s", "w", encoding="utf-8-sig",
                  newline="") as fh:
            fh.write(build_sdat(self.model, self.props))
        with open(base + ".xemt", "w", encoding="utf-8-sig",
                  newline="") as fh:
            fh.write(xemt_export.build_emt(self.model, self.props))
        self.status.showMessage(f"已导出 {base}.s / {base}.xemt")


def main(argv: list[str] | None = None) -> int:
    if not _HAS_GUI_DEPS:
        print("PyQt5 / vtk 未安装：python -m pip install -r requirements-gui.txt")
        return 1
    app = QtWidgets.QApplication(argv or sys.argv)
    path = argv[1] if argv and len(argv) > 1 and os.path.isfile(argv[1]) \
        else None
    win = CabViewer(path)
    win.show()
    if win.vtk_widget is not None:
        win.vtk_widget.GetRenderWindow().GetInteractor().Initialize()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
