"""Minimal UI language support (P7 i18n MVP).

Currently translates the application title and a few status strings;
full menu/dialog translation remains incremental.
"""

from __future__ import annotations

_STRINGS = {
    "en": {
        "app_title": "cabdecoding - STpre layout",
        "ready": "Ready.",
    },
    "zh": {
        "app_title": "cabdecoding - STpre 布局",
        "ready": "就绪。",
    },
}


def ui_language() -> str:
    from cab_options import get_setting
    return str(get_setting("ui_language", "en"))


def tr(key: str, lang: str | None = None) -> str:
    if lang is None:
        lang = ui_language()
    return _STRINGS.get(lang, _STRINGS["en"]).get(key, key)
