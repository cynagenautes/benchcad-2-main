"""Parametric part families for the synthetic training set.

Every family turns a seeded RNG into (params, CadQuery source). The source is
the training target: a complete program that leaves the solid in `result`,
written with the plain CadQuery API (2.3 in the BenchCAD sandbox, 2.8 on the
host), so it would run unchanged as a T3 ```submit.

None of this is derived from BenchCAD cases: the families, their parameter
ranges and their code are written here from scratch. BenchCAD's Public set
terms forbid training on it, and paper/train/contamination.py checks the
output against every BenchCAD file this machine holds before any upload.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable


def _r(rng: random.Random, lo: float, hi: float, step: float = 0.5) -> float:
    """A dimension in [lo, hi] on a `step` grid, the way a drawing would round it."""
    n = int(round((hi - lo) / step))
    return round(lo + step * rng.randint(0, n), 3)


@dataclass
class Family:
    name: str
    make: Callable[[random.Random], tuple[dict, str]]


def plate_holes(rng):
    L, W, T = _r(rng, 40, 160, 5), _r(rng, 30, 100, 5), _r(rng, 3, 15, 1)
    nx, ny = rng.randint(1, 4), rng.randint(1, 3)
    d = _r(rng, 3, min(12, W / (ny + 2)), 0.5)
    px, py = round((L - 2 * d - 10) / max(nx - 1, 1), 2), round((W - 2 * d - 10) / max(ny - 1, 1), 2)
    fil = _r(rng, 0, min(L, W) / 6, 1)
    p = dict(L=L, W=W, T=T, nx=nx, ny=ny, d=d, px=px, py=py, fillet=fil)
    src = f"""import cadquery as cq

L, W, T = {L}, {W}, {T}
result = cq.Workplane("XY").box(L, W, T)
"""
    if fil > 0:
        src += f'result = result.edges("|Z").fillet({fil})\n'
    src += f"""result = (result.faces(">Z").workplane()
          .rarray({px}, {py}, {nx}, {ny}).hole({d}))
"""
    return p, src


def flange(rng):
    D = _r(rng, 40, 140, 5)
    T = _r(rng, 5, 20, 1)
    bore = _r(rng, D * 0.2, D * 0.45, 1)
    hub_d = _r(rng, bore + 6, D * 0.7, 1)
    hub_h = _r(rng, 0, 30, 2)
    n = rng.choice([3, 4, 5, 6, 8])
    bc = round((D + hub_d) / 2 * 0.95, 2)
    hd = _r(rng, 3, max(3.5, (D - hub_d) / 3), 0.5)
    p = dict(D=D, T=T, bore=bore, hub_d=hub_d, hub_h=hub_h, n=n, bolt_circle=bc, hole_d=hd)
    src = f"""import cadquery as cq

result = cq.Workplane("XY").circle({D / 2}).extrude({T})
"""
    if hub_h > 0:
        src += f'result = result.faces(">Z").workplane().circle({hub_d / 2}).extrude({hub_h})\n'
    src += f"""result = result.faces(">Z").workplane().hole({bore})
result = (result.faces("<Z").workplane()
          .polarArray({bc / 2}, 0, 360, {n}).hole({hd}, {T}))
"""
    return p, src


def l_bracket(rng):
    W = _r(rng, 20, 80, 5)
    A, B = _r(rng, 30, 100, 5), _r(rng, 30, 100, 5)
    T = _r(rng, 3, 12, 1)
    hd = _r(rng, 3, min(10, W / 3), 0.5)
    fil = _r(rng, 0, T * 1.5, 0.5)
    p = dict(W=W, A=A, B=B, T=T, hole_d=hd, inner_fillet=fil)
    src = f"""import cadquery as cq

W, A, B, T = {W}, {A}, {B}, {T}
base = cq.Workplane("XY").box(A, W, T, centered=(False, True, False))
wall = cq.Workplane("XY").box(T, W, B, centered=(False, True, False))
result = base.union(wall)
"""
    if fil > 0:
        src += f'result = result.edges("|Y").edges(cq.selectors.NearestToPointSelector(({T}, 0, {T}))).fillet({fil})\n'
    src += f"""result = (result.faces(">Z[-2]").workplane(centerOption="CenterOfBoundBox")
          .center({(A + T) / 4}, 0).hole({hd}))
result = (result.faces("<X").workplane(centerOption="CenterOfBoundBox")
          .center(0, {B / 6}).hole({hd}))
"""
    return p, src


def stepped_shaft(rng):
    k = rng.randint(2, 5)
    ds = sorted((_r(rng, 8, 60, 1) for _ in range(k)), reverse=rng.random() < 0.5)
    ls = [_r(rng, 5, 50, 1) for _ in range(k)]
    ch = _r(rng, 0, min(ds) / 8, 0.5)
    p = dict(diameters=ds, lengths=ls, chamfer=ch)
    lines = ["import cadquery as cq", "", "result = None", "z = 0.0"]
    for d, l in zip(ds, ls):
        lines += [f"seg = cq.Workplane(\"XY\").workplane(offset=z).circle({d / 2}).extrude({l})",
                  "result = seg if result is None else result.union(seg)", f"z += {l}"]
    if ch > 0:
        lines.append(f'result = result.faces(">Z or <Z").edges().chamfer({ch})')
    return p, "\n".join(lines) + "\n"


def pocket_block(rng):
    L, W, H = _r(rng, 40, 120, 5), _r(rng, 30, 90, 5), _r(rng, 15, 60, 5)
    pl, pw = _r(rng, L * 0.3, L * 0.7, 1), _r(rng, W * 0.3, W * 0.7, 1)
    pd = _r(rng, 3, H * 0.6, 1)
    slot = rng.random() < 0.6
    sw = _r(rng, 4, max(4.5, W * 0.25), 0.5)
    p = dict(L=L, W=W, H=H, pocket_l=pl, pocket_w=pw, pocket_depth=pd, slot=slot, slot_w=sw)
    src = f"""import cadquery as cq

result = cq.Workplane("XY").box({L}, {W}, {H})
result = result.faces(">Z").workplane().rect({pl}, {pw}).cutBlind(-{pd})
"""
    if slot:
        src += (f'result = (result.faces("<Y").workplane(centerOption="CenterOfBoundBox")'
                f'.slot2D({L * 0.6}, {sw}).cutBlind(-{W * 0.3}))\n')
    return p, src


def hex_standoff(rng):
    af = _r(rng, 6, 30, 1)
    H = _r(rng, 8, 60, 1)
    bore = _r(rng, 2, af * 0.6, 0.5)
    ch = _r(rng, 0, af / 10, 0.25)
    p = dict(across_flats=af, H=H, bore=bore, chamfer=ch)
    src = f"""import cadquery as cq
import math

af, H = {af}, {H}
result = cq.Workplane("XY").polygon(6, af / math.cos(math.pi / 6)).extrude(H)
result = result.faces(">Z").workplane().hole({bore})
"""
    if ch > 0:
        src += f'result = result.faces(">Z or <Z").edges("not %CIRCLE").chamfer({ch})\n'
    return p, src


def u_channel(rng):
    L, W, H, T = _r(rng, 40, 160, 5), _r(rng, 20, 80, 5), _r(rng, 15, 60, 5), _r(rng, 2, 8, 1)
    nh = rng.randint(0, 4)
    hd = _r(rng, 3, min(10, W / 3), 0.5)
    p = dict(L=L, W=W, H=H, T=T, n_holes=nh, hole_d=hd)
    src = f"""import cadquery as cq

L, W, H, T = {L}, {W}, {H}, {T}
outer = cq.Workplane("XY").box(L, W, H, centered=(True, True, False))
inner = cq.Workplane("XY").workplane(offset=T).box(L, W - 2 * T, H, centered=(True, True, False))
result = outer.cut(inner)
"""
    if nh:
        src += (f'result = result.faces("<Z").workplane().rarray({round((L - 20) / max(nh - 1, 1), 2)}, 1, {nh}, 1)'
                f'.hole({hd})\n')
    return p, src


def ribbed_plate(rng):
    L, W, T = _r(rng, 60, 160, 5), _r(rng, 40, 100, 5), _r(rng, 3, 10, 1)
    n = rng.randint(1, 4)
    rh, rt = _r(rng, 8, 40, 1), _r(rng, 2, 8, 0.5)
    p = dict(L=L, W=W, T=T, n_ribs=n, rib_h=rh, rib_t=rt)
    src = f"""import cadquery as cq

L, W, T = {L}, {W}, {T}
result = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))
ribs = (cq.Workplane("XY").workplane(offset=T)
        .rarray({round(L / (n + 1), 2)}, 1, {n}, 1).rect({rt}, W).extrude({rh}))
result = result.union(ribs)
"""
    return p, src


FAMILIES = [Family(f.__name__, f) for f in
            (plate_holes, flange, l_bracket, stepped_shaft, pocket_block, hex_standoff, u_channel, ribbed_plate)]
