"""Native BRep engineering candidate views, no synthetic geometry."""
from pathlib import Path
import json,hashlib
import cadquery as cq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'docs/evidence/B13/r3/candidates';out.mkdir(parents=True,exist_ok=True)
path=ROOT/'fixtures/real-derived/b13/motor.brep';source=cq.Shape.importBrep(str(path));faces=source.Faces()
groups={'A':[16,17,18,19],'B':[20,21,22,23]}
colors={'A':'#e8a229','B':'#e56150'}
fig=plt.figure(figsize=(13,7),layout='constrained')
for index,title in enumerate(['Complete original motor | 44 native faces','Actual radial interfaces | geometry candidates'],1):
    ax=fig.add_subplot(1,2,index,projection='3d')
    for i,face in enumerate(faces):
        group=next((g for g,ids in groups.items() if i in ids),None)
        if index==2 and group is None and i!=43:continue
        vertices,triangles=face.tessellate(.12,.15)
        polygons=[[vertices[k].toTuple() for k in triangle] for triangle in triangles]
        ax.add_collection3d(Poly3DCollection(polygons,facecolor=colors.get(group,'#b7ccd7'),edgecolor='none',alpha=1 if group else .3))
    if index==1:
        b=source.BoundingBox();ax.set(xlim=(b.xmin-15,b.xmax+15),ylim=(b.ymin-15,b.ymax+15),zlim=(b.zmin-15,b.zmax+15));ax.set_box_aspect((b.xlen,b.ylen,b.zlen))
    else:
        ax.set(xlim=(45,108),ylim=(255,350),zlim=(145,220));ax.set_box_aspect((63,95,75))
        for group,ids in groups.items():
            c=max((faces[i].Center() for i in ids),key=lambda c:c.z);ax.text(c.x,c.y,c.z+4,group,color=colors[group],fontsize=16,fontweight='bold')
    ax.view_init(elev=25,azim=-55);ax.set_title(title,pad=18);ax.set_xlabel('X / mm');ax.set_ylabel('Y / mm');ax.set_zlabel('Z / mm')
fig.suptitle('B13 R3 | native motor: A vertical, B inclined 30 degrees\nEight actual cap / shoulder / sidewall faces; process approval pending',fontsize=14)
fig.savefig(out/'motor-interface-candidates.png',dpi=170);plt.close(fig)
value=dict(source=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_face_count=len(faces),index_convention='zero-based indices in original motor.brep; runtime EntityRef IDs differ after STEP import',target_face_index=43,candidates=[dict(id=g,source_face_indices=ids,faces=[dict(index=i,type=faces[i].geomType(),area_mm2=faces[i].Area(),centroid_mm=faces[i].Center().toTuple()) for i in ids],classification_approved=False) for g,ids in groups.items()],available_geometry_choices=['Explicit boss rule: protect the entire actual component, default additional band 0 mm','Explicit additional band 3 mm: measured geometry variant only, no process approval','Explicit exclude: omit this boundary rule','Explicit rib classification: retain paint where that engineering classification applies'],manufacturing_approval=False)
(out/'motor-interface-candidates.json').write_text(json.dumps(value,indent=2)+'\n')
