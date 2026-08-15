"""ECXML (Electronic Components XML) import/export.

ElectronicPartsMaker-domain interchange used by the STpre CAD Interface:
compact thermal circuit models of electronic components (JEDEC two-resistor
and Delphi network families).  The schema kept here is the pragmatic STpre
flavour:

    <ECXML version=\"1.0\">
      <Component name=\"QFP48\" kind=\"two_resistor\"
                 manufacturer=\"\" part_number=\"\">
        <Location x=\"0\" y=\"0\" z=\"0\" unit=\"mm\"/>
        <Size x=\"10\" y=\"10\" z=\"1.5\" unit=\"mm\"/>
        <Thermal>
          <Rjc unit=\"K/W\">1.0</Rjc>
          <Rjb unit=\"K/W\">5.0</Rjb>
          <Power unit=\"W\">1.0</Power>
        </Thermal>
      </Component>
    </ECXML>

Import maps components onto the model parts of kind two_resistor / delphi /
multi_resistor; export serialises those part kinds back.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


_KINDS = {'two_resistor', 'delphi', 'multi_resistor'}


def _attr_float(el, name, default=0.0) -> float:
    v = el.get(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _tag_float(el, tag, default=0.0) -> float:
    c = el.find(tag)
    if c is None or c.text is None:
        return default
    try:
        return float(c.text.strip())
    except ValueError:
        return default


def parse_ecxml(text: str) -> list:
    root = ET.fromstring(text)
    out = []
    for c in root.findall('Component'):
        loc = c.find('Location')
        size = c.find('Size')
        therm = c.find('Thermal')
        comp = {
            'name': c.get('name', 'Component'),
            'kind': c.get('kind', 'two_resistor'),
            'manufacturer': c.get('manufacturer', ''),
            'part_number': c.get('part_number', ''),
            'base': (_attr_float(loc, 'x') if loc is not None else 0.0,
                     _attr_float(loc, 'y') if loc is not None else 0.0,
                     _attr_float(loc, 'z') if loc is not None else 0.0),
            'size': (_attr_float(size, 'x', 10.0) if size is not None else 10.0,
                     _attr_float(size, 'y', 10.0) if size is not None else 10.0,
                     _attr_float(size, 'z', 1.0) if size is not None else 1.0),
            'rjc': (_tag_float(therm, 'Rjc', 1.0)
                    if therm is not None else 1.0),
            'rjb': (_tag_float(therm, 'Rjb', 5.0)
                    if therm is not None else 5.0),
            'package_power': (_tag_float(therm, 'Power', 1.0)
                              if therm is not None else 1.0),
        }
        comp['nodes'] = []
        if therm is not None:
            for nd in therm.findall('Node'):
                nm = nd.get('name', 'Node')
                r = _attr_float(nd, 'r', 1.0)
                comp['nodes'].append((nm, r))
        if comp['kind'] not in _KINDS:
            comp['kind'] = 'two_resistor'
        out.append(comp)
    return out


def import_ecxml_path(path) -> list:
    return parse_ecxml(Path(path).read_text(encoding='utf-8',
                                           errors='replace'))


def register_ecxml_parts(model, comps) -> list:
    from cab_parts import register_primitive
    names = []
    for comp in comps:
        name = comp['name']
        i = 2
        while model.find_part(name) is not None:
            name = comp['name'] + '_' + str(i)
            i += 1
        params = {
            'base': comp['base'],
            'size': comp['size'],
            'rjc': comp['rjc'],
            'rjb': comp['rjb'],
            'package_power': comp['package_power'],
        }
        if comp['manufacturer']:
            params['manufacturer'] = comp['manufacturer']
        if comp['part_number']:
            params['part_number'] = comp['part_number']
        if comp.get('nodes'):
            params['nodes'] = comp['nodes']
        ok = register_primitive(model, name=name, kind=comp['kind'],
                                params=params)
        if ok:
            names.append(name)
    return names


def _tag_text(el, tag, default=''):
    c = el.find(tag)
    if c is None or not (c.text or '').strip():
        return default
    return c.text.strip()


def parts_to_ecxml(model) -> str:
    root = ET.Element('ECXML', {'version': '1.0'})
    for p in model.parts():
        if p.kind not in _KINDS:
            continue
        base = _parse_triple(p.base, (0.0, 0.0, 0.0))
        size = _parse_triple(p.size, (10.0, 10.0, 1.0))
        c = ET.SubElement(root, 'Component', {
            'name': p.name, 'kind': p.kind,
            'manufacturer': _tag_text(p.elem, 'manufacturer'),
            'part_number': _tag_text(p.elem, 'part_number'),
        })
        ET.SubElement(c, 'Location', {
            'x': format(base[0], '.12g'), 'y': format(base[1], '.12g'),
            'z': format(base[2], '.12g'), 'unit': 'mm'})
        ET.SubElement(c, 'Size', {
            'x': format(size[0], '.12g'), 'y': format(size[1], '.12g'),
            'z': format(size[2], '.12g'), 'unit': 'mm'})
        th = ET.SubElement(c, 'Thermal')
        ET.SubElement(th, 'Rjc', {'unit': 'K/W'}).text = \
            format(_tag_float(p.elem, 'rjc', 1.0), '.12g')
        ET.SubElement(th, 'Rjb', {'unit': 'K/W'}).text = \
            format(_tag_float(p.elem, 'rjb', 5.0), '.12g')
        ET.SubElement(th, 'Power', {'unit': 'W'}).text = \
            format(_tag_float(p.elem, 'package_power', 1.0), '.12g')
        if p.kind == 'delphi':
            from cabxml import _first
            for nd in p.elem.findall('thermal_node'):
                nm = _first(nd, 'name')
                res = _first(nd, 'resistance')
                n = ET.SubElement(th, 'Node', {
                    'name': (nm.text or '').strip() if nm is not None
                    else 'Node'})
                try:
                    rv = (float((res.text or '').strip())
                          if res is not None else 1.0)
                except ValueError:
                    rv = 1.0
                n.set('r', format(rv, '.12g'))
    ET.indent(root, space='  ')
    return '<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n' + \
        ET.tostring(root, encoding='unicode')


def _parse_triple(text: str, default: tuple) -> tuple:
    if not (text or '').strip():
        return tuple(default)
    v = [float(x) for x in text.replace(',', ' ').split()]
    return tuple((v + list(default))[:3])
