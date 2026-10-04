"""STL / OBJ / 3MF writers (hand-written, numpy based)."""
from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

import numpy as np

from .geometry import Model


def _tri_normals(v, f):
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    return n / np.where(ln == 0, 1, ln)


def to_stl(model: Model) -> bytes:
    v, f = model.solid()
    tri = v[f].astype("<f4")
    rec = np.zeros(len(f), dtype=[("n", "<f4", 3), ("t", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"] = _tri_normals(v, f)
    rec["t"] = tri
    header = b"photo3d binary STL (mm)".ljust(80, b" ")
    return header + np.uint32(len(f)).tobytes() + rec.tobytes()


def to_obj(model: Model) -> bytes:
    out = io.StringIO()
    out.write("# photo3d OBJ (units: mm)\n")
    off = 1
    for b in model.bodies:
        out.write(f"o {b.name}\n")
        np.savetxt(out, b.vertices, fmt="v %.5f %.5f %.5f")
        np.savetxt(out, b.faces + off, fmt="f %d %d %d")
        off += len(b.vertices)
    return out.getvalue().encode()


CT = ('<?xml version="1.0" encoding="UTF-8"?>\n'
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
      '</Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')


def to_3mf(model: Model, title: str = "photo3d") -> bytes:
    colors = []
    for b in model.bodies:
        if b.color and b.color.upper() not in colors:
            colors.append(b.color.upper())
    x = io.StringIO()
    x.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    x.write('<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">')
    x.write(f'<metadata name="Title">{escape(title)}</metadata>'
            '<metadata name="Application">photo3d</metadata><resources>')
    mat_id = None
    if colors:
        mat_id = 1
        x.write('<basematerials id="1">')
        for i, c in enumerate(colors):
            x.write(f'<base name="color{i}" displaycolor="{c}FF"/>')
        x.write('</basematerials>')
    first = 2
    for i, b in enumerate(model.bodies):
        oid = first + i
        attrs = ""
        if mat_id and b.color:
            attrs = f' pid="{mat_id}" pindex="{colors.index(b.color.upper())}"'
        x.write(f'<object id="{oid}" type="model" name="{escape(b.name)}"{attrs}><mesh><vertices>')
        np.savetxt(x, b.vertices, fmt='<vertex x="%.5f" y="%.5f" z="%.5f"/>', newline="")
        x.write('</vertices><triangles>')
        np.savetxt(x, b.faces, fmt='<triangle v1="%d" v2="%d" v3="%d"/>', newline="")
        x.write('</triangles></mesh></object>')
    x.write('</resources><build>')
    for i in range(len(model.bodies)):
        x.write(f'<item objectid="{first + i}"/>')
    x.write('</build></model>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", x.getvalue())
    return buf.getvalue()


WRITERS = {"stl": to_stl, "obj": to_obj, "3mf": to_3mf}
