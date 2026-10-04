import numpy as np, trimesh, zipfile, io, struct
from pathlib import Path
out = Path(__file__).parent
rng = np.random.default_rng(42)
# (a) gear/bracket with holes ~50k tris
def gear(teeth=24, r_out=30, r_in=26, th=8, hole=6, nholes=6, ring=15):
    pts=[]
    for i in range(teeth*4):
        a=2*np.pi*i/(teeth*4); r=r_out if i%4 in (1,2) else r_in
        pts.append((r*np.cos(a), r*np.sin(a)))
    from shapely.geometry import Polygon, Point
    p=Polygon(pts)
    p=p.difference(Point(0,0).buffer(8,128))
    for k in range(nholes):
        a=2*np.pi*k/nholes; p=p.difference(Point(ring*np.cos(a),ring*np.sin(a)).buffer(hole/2*1.0,128))
    return trimesh.creation.extrude_polygon(p, th)
g=gear()
# subdivide to ~50k
while len(g.faces)<25000: g=g.subdivide()
print('gear',len(g.faces))
g.export(out/'a_gear_bracket_binary.stl')
# ascii copy of smaller gear
gs=gear(); open(out/'a2_gear_ascii.stl','w').write(trimesh.exchange.stl.export_stl_ascii(gs))
# (b) OBJ with groups, normals, UVs
def obj_groups():
    parts=[('base',trimesh.creation.box([60,40,5])),('post',trimesh.creation.cylinder(8,40,sections=48)),('ball',trimesh.creation.icosphere(3,10))]
    parts[1][1].apply_translation([0,0,22.5]); parts[2][1].apply_translation([0,0,50])
    lines=['# multi-group test','mtllib none.mtl']; vo=0; vto=0; vno=0
    for name,m in parts:
        lines.append(f'o {name}'); lines.append(f'g {name}_grp'); lines.append('usemtl mat_'+name)
        v=m.vertices; n=m.vertex_normals
        uv=np.c_[(v[:,0]-v[:,0].min())/max(np.ptp(v[:,0]),1e-9),(v[:,1]-v[:,1].min())/max(np.ptp(v[:,1]),1e-9)]
        lines += [f'v {a:.5f} {b:.5f} {c:.5f}' for a,b,c in v]
        lines += [f'vt {a:.5f} {b:.5f}' for a,b in uv]
        lines += [f'vn {a:.5f} {b:.5f} {c:.5f}' for a,b,c in n]
        for f in m.faces+1:
            lines.append('f '+' '.join(f'{i+vo}/{i+vo}/{i+vo}' for i in f))
        vo+=len(v)
    (out/'b_multigroup_uv_normals.obj').write_text('\n'.join(lines))
obj_groups()
# also an OBJ with quads + negative indices
q=['o quadbox']
bv=[(0,0,0),(10,0,0),(10,10,0),(0,10,0),(0,0,10),(10,0,10),(10,10,10),(0,10,10)]
q+=[f'v {a} {b} {c}' for a,b,c in bv]
quads=[(1,4,3,2),(5,6,7,8),(1,2,6,5),(2,3,7,6),(3,4,8,7),(4,1,5,8)]
q+=['f '+' '.join(map(str,x)) for x in quads]
(out/'b2_quads_box.obj').write_text('\n'.join(q))
# (c) 3MF with multiple objects, components, colors, transforms
def write3mf():
    def mesh_xml(m,oid,pid=None,col=None):
        v=''.join(f'<vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>' for a,b,c in m.vertices)
        t=''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a,b,c in m.faces)
        pa=f' pid="{pid}" pindex="{col}"' if pid else ''
        return f'<object id="{oid}" type="model"{pa}><mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh></object>'
    box=trimesh.creation.box([20,20,10]); cyl=trimesh.creation.cylinder(6,15,sections=40); sph=trimesh.creation.icosphere(3,8)
    objs=mesh_xml(box,1,10,0)+mesh_xml(cyl,2,10,1)+mesh_xml(sph,3,10,2)
    objs+='<object id="4" type="model"><components><component objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/><component objectid="2" transform="1 0 0 0 1 0 0 0 1 0 0 12"/></components></object>'
    xml=('<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>'
     '<basematerials id="10"><base name="Red" displaycolor="#FF0000FF"/><base name="Green" displaycolor="#00FF00FF"/><base name="Blue" displaycolor="#0000FFFF"/></basematerials>'
     +objs+'</resources><build>'
     '<item objectid="4" transform="1 0 0 0 1 0 0 0 1 50 50 0"/>'
     '<item objectid="3" transform="0 -1 0 1 0 0 0 0 1 100 20 5"/>'
     '<item objectid="1" transform="2 0 0 0 2 0 0 0 1 -30 -30 0"/></build></model>')
    ct='<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    rels='<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with zipfile.ZipFile(out/'c_multiobj_components_colors.3mf','w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',ct); z.writestr('_rels/.rels',rels); z.writestr('3D/3dmodel.model',xml)
write3mf()
# (d) bad download: flipped normals on half, open holes, duplicate faces, floating bits
m=trimesh.creation.icosphere(4,25)  # ~ 5k tris wait
m=trimesh.Trimesh(m.vertices.copy(), m.faces.copy(), process=False)
f=m.faces.copy()
# remove faces near top (hole) & a side patch
c=m.triangles_center
keep=~((c[:,2]>20)|((c[:,0]>22)&(np.abs(c[:,1])<6)))
f=f[keep]
# flip 30% of the remaining
flip=rng.random(len(f))<0.3; f[flip]=f[flip][:,::-1]
# duplicate 100 faces
f=np.vstack([f,f[:100]])
# floating tiny tetra
tet=trimesh.creation.box([1,1,1]); tet.apply_translation([60,0,0])
v=np.vstack([m.vertices,tet.vertices]); f=np.vstack([f,tet.faces+len(m.vertices)])
bad=trimesh.Trimesh(v,f,process=False); bad.export(out/'d_bad_open_flipped.stl'); print('bad',len(bad.faces))
# (e1) organic high poly, in metres, far from origin
s=trimesh.creation.icosphere(8)  # 1.3M? check
print('ico8',len(s.faces))
s=trimesh.creation.icosphere(7)   # 327,680 tris
v=s.vertices.copy()
n=v/np.linalg.norm(v,axis=1,keepdims=True)
noise=sum(np.sin(n[:,0]*k+p)*np.cos(n[:,1]*k*1.3+p)*np.sin(n[:,2]*k*0.7+p)*(0.12/k**0.5) for k,p in [(3,0.1),(7,1.3),(15,2.2),(31,0.7)])
v=n*(1+noise[:,None])*1.0
v[:,2]*=1.4
v=v*1.5            # ~3 inch across (units: inches)
v+=np.array([40.0,25.0,5.0])   # far from origin (inches => ~1000 mm)
org=trimesh.Trimesh(v,s.faces,process=False); org.export(out/'e_organic_330k_inches_offset.stl'); print('organic',len(org.faces),org.bounds)
# unicode filename copy of small part
import shutil; shutil.copy(out/'a2_gear_ascii.stl', out/'ギア_部品_é.stl')
