"""Minimal planar reader to prove the handoff interface, not a drawing engine."""
import numpy as np
import trimesh
from . import checks, shapes
from .io import atomic,within,sha


def slice_geometry(g, origin, normal, x_axis, ids=None):
    origin=np.asarray(origin,dtype=float);normal=np.asarray(normal,dtype=float);x=np.asarray(x_axis,dtype=float)
    normal/=np.linalg.norm(normal);x/=np.linalg.norm(x)
    if not np.isfinite([origin,normal,x]).all() or abs(normal@x)>1e-8:raise ValueError('Finite perpendicular plane normal and X axis required')
    y=np.cross(normal,x);rows=[]
    for o in checks.select(g,ids):
        if not o.get('triangles'):continue
        segments=trimesh.intersections.mesh_plane(shapes.mesh(o),normal,origin)
        if len(segments):
            local=segments-origin;xy=np.stack((local@x,local@y),axis=-1)
            rows.append(dict(id=o['id'],name=o.get('name'),segments_m=xy.tolist()))
    return dict(schema_version=1,units='m',origin_m=origin.tolist(),normal=normal.tolist(),x_axis=x.tolist(),
        objects=rows,native_face_rings=sum(len(o.get('faces',[])) for o in checks.select(g,ids)),
        limits='Section segments only. No hidden-line removal, annotation, line-weight or final graphic certification.')


def write_slice(workspace,geometry_path,output_path,origin,normal,x_axis,ids=None):
    root=within(workspace,'.');source=within(root,geometry_path);g=checks.geometry(source)
    result=slice_geometry(g,origin,normal,x_axis,ids)
    result['source']=dict(path=geometry_path,sha256=sha(source))
    atomic(within(root,output_path),result)
    return result
