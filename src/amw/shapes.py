"""Metre-based solid geometry. Sizes are project inputs, never code compliance."""
import math
import numpy as np
import trimesh
from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient


def payload(mesh):
    mesh.remove_unreferenced_vertices()
    if not mesh.is_watertight or not mesh.is_volume:
        raise ValueError('Generated geometry is not a closed, consistently oriented solid')
    return dict(vertices=mesh.vertices.tolist(), triangles=mesh.faces.tolist(), expect_solid=True)


def mesh(data):
    return trimesh.Trimesh(vertices=data['vertices'], faces=data['triangles'], process=True)


def solid_problems(m):
    """Validate each closed shell; a positive aggregate volume can hide a flipped body.

    Negative inner cavity shells are retained when actual solid intersection
    proves their nesting parity. No bounding-box-only orientation inference.
    """
    if not len(m.faces) or not np.isfinite(m.vertices).all() or not m.is_watertight or not m.is_winding_consistent:
        return ['open, degenerate or inconsistently oriented solid']
    neighbors=[[] for _ in m.faces]
    for a,b in m.face_adjacency:
        neighbors[a].append(b);neighbors[b].append(a)
    remaining=set(range(len(m.faces)));components=[]
    while remaining:
        stack=[remaining.pop()];faces=[]
        while stack:
            i=stack.pop();faces.append(i)
            for j in neighbors[i]:
                if j in remaining:remaining.remove(j);stack.append(j)
        components.append(faces)
    if len(components)==1:return [] if m.volume>0 else ['inverted outer shell']
    shells=[]
    for faces in components:
        shell=trimesh.Trimesh(vertices=m.vertices,faces=m.faces[faces],process=False)
        shell.remove_unreferenced_vertices();shells.append(shell)
    if all(s.volume>0 for s in shells):return []
    solids=[]
    for shell in shells:
        s=shell.copy()
        if s.volume<0:s.invert()
        if not s.is_volume:return ['zero-volume or invalid shell']
        solids.append(s)
    problems=[]
    for i,(original,child) in enumerate(zip(shells,solids)):
        depth=0
        for j,parent in enumerate(solids):
            if i==j or np.any(child.bounds[0]<parent.bounds[0]) or np.any(child.bounds[1]>parent.bounds[1]):continue
            intersection=trimesh.boolean.intersection([child,parent],engine='manifold')
            tolerance=max(1e-12,abs(child.volume)*1e-7)
            if abs(intersection.volume-child.volume)<=tolerance:depth+=1
        if (original.volume>0)!=(depth%2==0):problems.append(f'shell {i} has wrong orientation for actual nesting depth {depth}')
    return problems


def box(origin, size):
    if len(origin) != 3 or len(size) != 3 or min(size) <= 0:
        raise ValueError('Box needs a 3D origin and three positive dimensions in metres')
    m = trimesh.creation.box(extents=size)
    m.apply_translation(np.array(origin) + np.array(size) / 2)
    return payload(m)


def prism(outline, holes, z, height):
    p = orient(Polygon(outline, holes), sign=1)
    if not p.is_valid or p.area <= 0 or height <= 0:
        raise ValueError('Prism requires a valid polygon and positive height')
    vertices = []; indices = {}; faces = []
    def idx(x, y, zz):
        key = (float(x), float(y), float(zz))
        if key not in indices:
            indices[key] = len(vertices); vertices.append(key)
        return indices[key]
    for t in constrained_delaunay_triangles(p).geoms:
        t = orient(t, sign=1)
        if not p.covers(t.representative_point()):
            continue
        xy = list(t.exterior.coords)[:3]
        faces.append([idx(x, y, z + height) for x, y in xy])
        faces.append([idx(x, y, z) for x, y in reversed(xy)])
    for ring in [p.exterior, *p.interiors]:
        points = list(ring.coords)
        for a, b in zip(points[:-1], points[1:]):
            ai, bi = idx(*a, z), idx(*b, z)
            at, bt = idx(*a, z + height), idx(*b, z + height)
            faces.extend([[ai, bi, bt], [ai, bt, at]])
    return payload(trimesh.Trimesh(vertices=vertices, faces=faces, process=True))


def boolean(a, b, operation):
    ma, mb = mesh(a), mesh(b)
    if solid_problems(ma) or solid_problems(mb):
        raise ValueError('Boolean input must contain closed solids; repair the actual topology first')
    fn = {'difference': trimesh.boolean.difference, 'union': trimesh.boolean.union,
          'intersection': trimesh.boolean.intersection}[operation]
    result = fn([ma, mb], engine='manifold')
    if result.is_empty:
        return dict(vertices=[], triangles=[], expect_solid=True)
    return payload(result)


def stairs(origin, width, rise, tread, risers, rotation_degrees=0):
    if width <= 0 or rise <= 0 or tread <= 0 or not 2 <= risers <= 100:
        raise ValueError('Provide positive width/rise/tread and 2–100 integer risers')
    # n risers, n-1 treads; the arrival slab supplies the final level.
    outline = [[0, 0], [(risers - 1) * tread, 0], [(risers - 1) * tread, (risers - 1) * rise]]
    for n in range(risers - 1, 0, -1):
        outline.extend([[((n - 1) * tread), n * rise], [((n - 1) * tread), (n - 1) * rise]])
    m = mesh(prism(outline, [], 0, width))
    v = m.vertices.copy()
    # Polygon XY encodes run and height; extrusion becomes width.
    m.vertices = np.column_stack((v[:, 2], v[:, 0], v[:, 1]))
    t = trimesh.transformations.rotation_matrix(math.radians(rotation_degrees), [0, 0, 1])
    m.apply_transform(t); m.apply_translation(origin)
    return payload(m)
