"""ComObject + typed STpre class-hierarchy wrappers (late-bound coverage)."""
from __future__ import annotations

import pytest

import cab_stpre_api


class _Flag:
    """Minimal win32com-like dispatch object with _FlagAsMethod."""
    def _FlagAsMethod(self, name):
        return self


class _FakeDoc(_Flag):
    def __init__(self):
        self.mesher = _Flag()
        self.created = []
        self.saved = []

    def OpenCabFile(self, path):
        return 1

    def SaveCabFile(self, path):
        self.saved.append(path)
        return 1

    def GetMesher(self):
        return self.mesher

    def GetModel(self, name):
        return _Flag()

    def CreateCubeModel(self, name, base, size):
        self.created.append(name)
        return _Flag()


class _FakeApp(_Flag):
    def __init__(self):
        self.doc = _FakeDoc()

    def GetDocument(self):
        return self.doc

    def Quit(self):
        pass


def test_com_object_call_flags_method():
    obj = ComObject_wrap(_FakeDoc())
    assert obj.call("OpenCabFile", "x.cab") == 1


def ComObject_wrap(o):
    return cab_stpre_api.ComObject(o)


def test_typed_doc_create_and_save():
    app = cab_stpre_api.STpreApplication(_FakeApp())
    doc = app.GetDocument()
    assert isinstance(doc, cab_stpre_api.STpreDoc)
    m = doc.CreateCubeModel("box", "0,0,0", "10,10,10")
    assert isinstance(m, cab_stpre_api.STpreModel)
    assert app.raw.doc.created == ["box"]
    assert doc.SaveCabFile("out.cab") == 1
    assert app.raw.doc.saved == ["out.cab"]


def test_catalog_populated():
    assert "Doc_high_value" in cab_stpre_api.API_CATALOG
    assert "CreateCubeModel" in cab_stpre_api.API_CATALOG["Doc_high_value"]
    assert "SaveCabFile" in cab_stpre_api.API_CATALOG["Doc_high_value"]
    assert cab_stpre_api.API_MEMBER_COUNTS["Doc"] == 459


def test_session_exposes_typed_accessors():
    sess = cab_stpre_api.STpreSession()
    sess._app = _FakeApp()
    sess._doc = sess._app.doc
    sess._mesher = sess._app.doc.mesher
    assert isinstance(sess.application, cab_stpre_api.STpreApplication)
    assert isinstance(sess.doc, cab_stpre_api.STpreDoc)
    assert isinstance(sess.mesher, cab_stpre_api.STpreMesher)
    assert isinstance(sess.model("box"), cab_stpre_api.STpreModel)
