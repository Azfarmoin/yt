"""Runs INSIDE Blender (bpy as a Python module):  python -m ivs.bl_scene spec.json
Procedural, license-free 3D: heightfield terrain (dunes/mountains), ocean, sky/moon/stars, drifting clouds, faceless low-poly
figures with real walk cycles (robed walker, spearman, staff traveller), elephants with leg cycles, flapping birds, and
keyframe-free per-frame camera direction (dolly, truck, crane, orbit, follow, low push).
SAFETY: only the generic actors below exist. No prophet / Companion / sacred-figure actor, and no actor has facial features."""
from __future__ import annotations
import json, math, sys
import numpy as np
import bpy
from mathutils import Vector, Euler

# ---------------------------------------------------------------------------------------------------------- helpers
def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)

def height(x, y, env):
    """Terrain height (metres). Dunes everywhere, tall ridges far in +Y (mountains)."""
    s = env["seed"] * 1.7
    d = (1.3 * np.sin(0.05 * x + 1.3 + s) * np.cos(0.032 * y + s) + 0.8 * np.sin(0.12 * x + 0.07 * y + 2 + s)
         + 0.35 * np.sin(0.31 * x - 0.2 * y + s)) * env["dune"]
    far = smooth(env["mtn_start"], env["mtn_start"] + 110, y)
    ridge = (np.abs(np.sin(0.021 * x + 1 + s)) * 0.7 + np.abs(np.sin(0.047 * x + 0.5 * s)) * 0.3) * env["mtn_h"]
    return d + far * (ridge + 0.4 * np.sin(0.11 * x + s))

def rgb(h):
    h = h.lstrip("#"); return tuple(((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92 for c in (int(h[i:i + 2], 16) for i in (0, 2, 4)))

def mat(name, color, rough=0.85, emit=0.0, metallic=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    if emit:
        for k in ("Emission Color", "Emission"):
            if k in b.inputs: b.inputs[k].default_value = (*color, 1); break
        if "Emission Strength" in b.inputs: b.inputs["Emission Strength"].default_value = emit
    return m

def solid(obj, m):
    obj.data.materials.clear(); obj.data.materials.append(m); return obj

def prim(kind, loc=(0, 0, 0), scale=(1, 1, 1), parent=None, material=None, rot=(0, 0, 0), **kw):
    ops = {"sphere": lambda: bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=0.5, **kw),
           "cyl": lambda: bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=0.5, depth=1, **kw),
           "cone": lambda: bpy.ops.mesh.primitive_cone_add(vertices=18, radius1=0.5, radius2=kw.pop("r2", 0.0), depth=1),
           "cube": lambda: bpy.ops.mesh.primitive_cube_add(size=1, **kw)}
    ops[kind](); o = bpy.context.object
    o.location, o.scale, o.rotation_euler = loc, scale, rot
    if parent: o.parent = parent
    if material: solid(o, material)
    for p in o.data.polygons: p.use_smooth = True
    return o

def empty(name, loc=(0, 0, 0), parent=None):
    e = bpy.data.objects.new(name, None); bpy.context.collection.objects.link(e); e.location = loc
    if parent: e.parent = parent
    return e

def pivot_cyl(parent, top, length, width, material, name=""):
    """Cylinder hanging from a pivot empty at its top (so rotating the pivot swings it like a limb)."""
    pv = empty(name, top, parent)
    prim("cyl", (0, 0, -length / 2), (width, width, length), pv, material)
    return pv

# ------------------------------------------------------------------------------------------------------------ geometry
def lathe(name, profile, segs=28, fold=(0.0, 6), squash=(1.0, 1.0), parent=None, material=None, loc=(0, 0, 0), rot=(0, 0, 0), cap=True):
    """Surface of revolution from [(radius, z)...] with optional cloth-like folds (amp, count). Smooth shaded."""
    rings = len(profile); verts = []
    for r, z in profile:
        for k in range(segs):
            th = 2 * math.pi * k / segs; rr = r * (1 + fold[0] * math.sin(fold[1] * th + z * 2.3))
            verts.append((rr * math.cos(th) * squash[0], rr * math.sin(th) * squash[1], z))
    faces = [(i * segs + k, i * segs + (k + 1) % segs, (i + 1) * segs + (k + 1) % segs, (i + 1) * segs + k) for i in range(rings - 1) for k in range(segs)]
    if cap:
        faces += [tuple(range(segs - 1, -1, -1)), tuple(range((rings - 1) * segs, rings * segs))]
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    o = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(o)
    for p in me.polygons: p.use_smooth = len(p.vertices) == 4
    o.location, o.rotation_euler = loc, rot
    if parent: o.parent = parent
    if material: solid(o, material)
    return o

def limb(parent, top, l1, l2, w, material, name="limb"):
    """Two-segment limb (upper + lower) with a pivot at the top and another at the joint; returns (root pivot, joint pivot)."""
    p1 = empty(name, top, parent); prim("cyl", (0, 0, -l1 / 2), (w, w, l1), p1, material); prim("sphere", (0, 0, 0), (w * 1.15,) * 3, p1, material)
    p2 = empty(name + "_j", (0, 0, -l1), p1); prim("cyl", (0, 0, -l2 / 2), (w * 0.88, w * 0.88, l2), p2, material); prim("sphere", (0, 0, -l2), (w * 1.0,) * 3, p2, material)
    return p1, p2

def torus(loc, major, minor, parent, material, rot=(0, 0, 0), scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=24, minor_segments=8); o = bpy.context.object
    o.location, o.rotation_euler, o.scale = loc, rot, scale; o.parent = parent; solid(o, material)
    for p in o.data.polygons: p.use_smooth = True
    return o

# ------------------------------------------------------------------------------------------------------------ actors
class Actor:
    def __init__(self, spec, env, pal):
        self.s, self.env = spec, env
        self.t0 = spec.get("phase", 0.0)
        self.root = empty("actor"); self.kind = spec["type"]
        getattr(self, "build_" + self.kind)(pal)

    # Humans: covered head (smooth featureless oval wrapped in a turban), long folded robe, sleeves, hands, belt, sandals.
    def build_person(self, pal, spear=False, staff=False, bundle=False):
        r = self.root; sc = self.s.get("scale", 1.0); k = self.s.get("variant", 0)
        pc = [pal["robe"], pal["accent"], pal["hood"]]
        robe = mat("robe", rgb(pc[0]), 0.92); cloth = mat("cloth", rgb(pc[1]), 0.9); wrap = mat("wrap", rgb(pc[2] if k % 2 else pc[1]), 0.95)
        under = mat("under", rgb(pc[0]), 0.9); leather = mat("leather", (0.12, 0.07, 0.04), 0.7); covered = mat("covered", rgb(pc[2]), 0.95)
        self.body = empty("body", (0, 0, 0), r)
        prof = [(0.34, 0.04), (0.33, 0.25), (0.28, 0.6), (0.23, 0.95), (0.2, 1.2), (0.2, 1.42), (0.15, 1.5), (0.09, 1.54)]   # robe silhouette
        lathe("robe", [(a * sc, z * sc) for a, z in prof], 30, (0.045, 7), (1.0, 0.85), self.body, robe)
        lathe("shoulders", [(0.2 * sc, 1.36 * sc), (0.27 * sc, 1.42 * sc), (0.22 * sc, 1.5 * sc), (0.1 * sc, 1.56 * sc)], 20, (0.0, 1), (1.05, 0.7), self.body, robe)
        prim("sphere", (0, 0.015 * sc, 1.69 * sc), (0.23 * sc, 0.26 * sc, 0.31 * sc), self.body, covered)             # head: blank oval, no features
        torus((0, 0.01 * sc, 1.76 * sc), 0.14 * sc, 0.045 * sc, self.body, wrap, scale=(1, 1.05, 1)); torus((0, 0.01 * sc, 1.69 * sc), 0.145 * sc, 0.04 * sc, self.body, wrap, (math.radians(8), 0, 0))
        prim("cone", (0, 0.17 * sc, 1.62 * sc), (0.2 * sc, 0.2 * sc, 0.55 * sc), self.body, wrap, rot=(math.radians(-110), 0, 0), r2=0.02)   # turban tail, flutters
        lathe("belt", [(0.215 * sc, 1.08 * sc), (0.225 * sc, 1.13 * sc), (0.225 * sc, 1.18 * sc), (0.215 * sc, 1.2 * sc)], 24, (0, 1), (1.0, 0.85), self.body, cloth)
        self.cape = lathe("cape", [(0.0, 1.46 * sc), (0.26 * sc, 1.4 * sc), (0.3 * sc, 0.9 * sc), (0.33 * sc, 0.55 * sc)], 18, (0.05, 4), (1.0, 0.2), self.body, cloth, loc=(0, 0.2 * sc, 0))
        self.armL, self.elbL = limb(self.body, (-0.25 * sc, 0, 1.4 * sc), 0.3 * sc, 0.3 * sc, 0.055 * sc, robe, "armL")
        self.armR, self.elbR = limb(self.body, (0.25 * sc, 0, 1.4 * sc), 0.3 * sc, 0.3 * sc, 0.055 * sc, robe, "armR")
        self.footL = prim("sphere", (-0.11 * sc, 0, 0.05 * sc), (0.13 * sc, 0.27 * sc, 0.09 * sc), r, leather)
        self.footR = prim("sphere", (0.11 * sc, 0, 0.05 * sc), (0.13 * sc, 0.27 * sc, 0.09 * sc), r, leather)
        if bundle:
            prim("sphere", (0, 0.27 * sc, 1.0 * sc), (0.3 * sc, 0.22 * sc, 0.4 * sc), self.body, mat("bundle", rgb(pc[1]), 0.95))
            torus((0, 0.27 * sc, 1.0 * sc), 0.19 * sc, 0.012 * sc, self.body, leather, (math.radians(90), 0, 0))
        if spear:
            sp = empty("spear", (0.3 * sc, 0.05 * sc, 0), r); self.spear = sp
            prim("cyl", (0, 0, 1.0 * sc), (0.03 * sc, 0.03 * sc, 2.3 * sc), sp, mat("wood", (0.25, 0.16, 0.08)))
            prim("cone", (0, 0, 2.28 * sc), (0.075 * sc, 0.075 * sc, 0.3 * sc), sp, mat("iron", (0.2, 0.2, 0.23), 0.35, metallic=0.9))
            prim("cyl", (0, 0, 0.35 * sc), (0.05 * sc, 0.05 * sc, 0.05 * sc), sp, leather)
        if staff:
            sp = empty("staff", (0.3 * sc, 0.1 * sc, 0), r); self.spear = sp
            prim("cyl", (0, 0, 0.85 * sc), (0.035 * sc, 0.035 * sc, 1.75 * sc), sp, mat("wood2", (0.3, 0.2, 0.1)))
            prim("sphere", (0, 0, 1.75 * sc), (0.07 * sc,) * 3, sp, mat("wood2", (0.3, 0.2, 0.1)))
    def build_walker(self, pal): self.build_person(pal)
    def build_spearman(self, pal): self.build_person(pal, spear=True)
    def build_traveller(self, pal): self.build_person(pal, staff=True, bundle=True)

    def build_elephant(self, pal):
        r = self.root; sc = self.s.get("scale", 1.0)
        grey = mat("elephant", rgb(pal.get("elephant", "#6b6560")), 0.97); ivory = mat("ivory", (0.85, 0.8, 0.68), 0.4); cloth = mat("howdah", rgb(pal["accent"]), 0.9)
        dark = mat("edark", rgb("#4a4642"), 0.98)
        self.body = empty("ebody", (0, 0, 0), r)
        lathe("torso", [(0.2 * sc, -1.5 * sc), (0.95 * sc, -1.2 * sc), (1.15 * sc, -0.3 * sc), (1.1 * sc, 0.8 * sc), (0.85 * sc, 1.5 * sc), (0.4 * sc, 1.85 * sc)], 28, (0.03, 9), (1.0, 1.0), self.body, grey, loc=(0, 0, 2.2 * sc), rot=(math.radians(90), 0, 0))
        prim("sphere", (0, 1.8 * sc, 2.65 * sc), (1.15 * sc, 1.2 * sc, 1.35 * sc), self.body, grey)
        prim("sphere", (0, 1.95 * sc, 3.2 * sc), (0.8 * sc, 0.7 * sc, 0.6 * sc), self.body, grey)                      # forehead dome
        for sx in (-1, 1):
            prim("sphere", (sx * 0.95 * sc, 1.45 * sc, 2.7 * sc), (0.1 * sc, 1.05 * sc, 1.3 * sc), self.body, dark, rot=(0, 0, sx * math.radians(18)))   # ears
            prim("cone", (sx * 0.42 * sc, 2.55 * sc, 2.0 * sc), (0.16 * sc, 0.16 * sc, 1.05 * sc), self.body, ivory, rot=(math.radians(70), 0, sx * math.radians(-10)), r2=0.01)   # tusks
        self.trunk = []; par = self.body; pos = (0, 2.4 * sc, 2.9 * sc); w = 0.46 * sc
        for i in range(4):
            e = empty(f"trunk{i}", pos, par); prim("cyl", (0, 0, -0.32 * sc), (w, w, 0.7 * sc), e, grey); self.trunk.append(e); par = e; pos = (0, 0, -0.62 * sc); w *= 0.82
        prim("cube", (0, -0.1 * sc, 3.38 * sc), (1.5 * sc, 1.9 * sc, 0.16 * sc), self.body, cloth)                          # decorated blanket
        for sx in (-1, 1):
            for i in range(5): prim("cone", (sx * 0.75 * sc, (-0.9 + i * 0.45) * sc, 3.2 * sc), (0.08 * sc, 0.08 * sc, 0.3 * sc), self.body, ivory, rot=(math.pi, 0, 0), r2=0.04)   # tassels
        for sx in (-1, 1):
            for sy in (-0.7, 0.7): prim("cyl", (sx * 0.5 * sc, sy * sc, 3.65 * sc), (0.06 * sc, 0.06 * sc, 0.75 * sc), self.body, mat("wood", (0.25, 0.16, 0.08)))   # canopy posts
        prim("cube", (0, 0, 4.05 * sc), (1.35 * sc, 1.8 * sc, 0.07 * sc), self.body, cloth)                                 # empty canopy
        self.legs = []
        for i, (lx, ly) in enumerate(((-0.65, 1.0), (0.65, 1.0), (-0.65, -1.0), (0.65, -1.0))):
            pv = empty(f"leg{i}", (lx * sc, ly * sc, 1.6 * sc), self.body); prim("cyl", (0, 0, -0.8 * sc), (0.58 * sc, 0.58 * sc, 1.6 * sc), pv, grey)
            for n in range(3): prim("sphere", ((n - 1) * 0.16 * sc, 0.2 * sc, -1.58 * sc), (0.14 * sc, 0.14 * sc, 0.1 * sc), pv, ivory)
            self.legs.append(pv)
        self.tail = empty("tail", (0, -1.85 * sc, 2.7 * sc), self.body); prim("cyl", (0, 0, -0.5 * sc), (0.07 * sc, 0.07 * sc, 1.0 * sc), self.tail, grey); prim("sphere", (0, 0, -1.05 * sc), (0.16 * sc,) * 3, self.tail, dark)

    def build_camel(self, pal):
        r = self.root; sc = self.s.get("scale", 1.0); fur = mat("camel", rgb(pal.get("camel", "#b08650")), 0.97); cloth = mat("camelcloth", rgb(pal["accent"]), 0.9); sack = mat("sack", rgb(pal["robe"]), 0.95)
        self.body = empty("cbody", (0, 0, 0), r)
        lathe("cbelly", [(0.1 * sc, -1.2 * sc), (0.5 * sc, -0.9 * sc), (0.62 * sc, 0), (0.5 * sc, 0.9 * sc), (0.1 * sc, 1.2 * sc)], 20, (0.0, 1), (1.0, 1.0), self.body, fur, loc=(0, 0, 1.55 * sc), rot=(math.radians(90), 0, 0))
        prim("sphere", (0, -0.1 * sc, 2.25 * sc), (0.55 * sc, 0.7 * sc, 0.55 * sc), self.body, fur)                          # hump
        neck = empty("neck", (0, 1.05 * sc, 1.9 * sc), self.body); self.neck = neck
        prim("cyl", (0, 0.25 * sc, 0.45 * sc), (0.26 * sc, 0.26 * sc, 1.05 * sc), neck, fur, rot=(math.radians(-28), 0, 0))
        prim("sphere", (0, 0.62 * sc, 0.98 * sc), (0.24 * sc, 0.5 * sc, 0.26 * sc), neck, fur)                              # head, featureless
        prim("cube", (0, -0.1 * sc, 2.0 * sc), (1.1 * sc, 1.25 * sc, 0.1 * sc), self.body, cloth)
        for sx in (-1, 1): prim("sphere", (sx * 0.5 * sc, -0.15 * sc, 2.0 * sc), (0.35 * sc, 0.45 * sc, 0.45 * sc), self.body, sack)
        self.legs = []
        for i, (lx, ly) in enumerate(((-0.3, 0.8), (0.3, 0.8), (-0.3, -0.8), (0.3, -0.8))):
            u, l = limb(self.body, (lx * sc, ly * sc, 1.3 * sc), 0.62 * sc, 0.68 * sc, 0.11 * sc, fur, f"cleg{i}"); self.legs.append((u, l))
        self.tail = empty("ctail", (0, -1.25 * sc, 1.7 * sc), self.body); prim("cyl", (0, 0, -0.3 * sc), (0.05 * sc, 0.05 * sc, 0.6 * sc), self.tail, fur)

    def build_ship(self, pal):
        r = self.root; sc = self.s.get("scale", 1.0); wood = mat("hull", (0.22, 0.13, 0.07), 0.8); sail = mat("sail", (0.75, 0.7, 0.58), 0.95); dark = mat("mast", (0.15, 0.09, 0.05), 0.8)
        self.body = empty("shipbody", (0, 0, 0), r)
        lathe("hull", [(0.2 * sc, -3.2 * sc), (1.3 * sc, -2.6 * sc), (1.9 * sc, -0.8 * sc), (1.9 * sc, 1.2 * sc), (1.4 * sc, 2.6 * sc), (0.3 * sc, 3.5 * sc)], 18, (0.0, 1), (1.0, 1.0), self.body, wood, loc=(0, 0, 0.55 * sc), rot=(math.radians(90), 0, 0))
        prim("cube", (0, 0, 1.2 * sc), (3.4 * sc, 6.4 * sc, 0.12 * sc), self.body, dark)                                  # deck (empty)
        prim("cyl", (0, 0.3 * sc, 4.3 * sc), (0.14 * sc, 0.14 * sc, 6.2 * sc), self.body, dark)
        self.sail = prim("cube", (0, 0.35 * sc, 4.7 * sc), (3.6 * sc, 0.08 * sc, 4.4 * sc), self.body, sail)
        prim("cube", (0, 0.3 * sc, 6.9 * sc), (3.9 * sc, 0.12 * sc, 0.12 * sc), self.body, dark)

    def build_bird(self, pal):
        r = self.root; sc = self.s.get("scale", 1.0); dark = mat("bird", (0.03, 0.03, 0.04), 0.9)
        prim("sphere", (0, 0, 0), (0.16 * sc, 0.5 * sc, 0.14 * sc), r, dark); prim("cone", (0, 0.32 * sc, 0), (0.05 * sc, 0.05 * sc, 0.12 * sc), r, dark, rot=(math.radians(-90), 0, 0), r2=0.0)
        prim("cone", (0, -0.35 * sc, 0), (0.12 * sc, 0.02 * sc, 0.3 * sc), r, dark, rot=(math.radians(90), 0, 0), r2=0.1)
        self.wings = []
        for sx in (-1, 1):
            pv = empty("wing", (sx * 0.08 * sc, 0, 0.04 * sc), r); w1 = empty("w1", (0, 0, 0), pv)
            prim("cube", (sx * 0.28 * sc, 0, 0), (0.56 * sc, 0.34 * sc, 0.02 * sc), w1, dark)
            w2 = empty("w2", (sx * 0.56 * sc, 0, 0), w1); prim("cube", (sx * 0.22 * sc, -0.03 * sc, 0), (0.44 * sc, 0.26 * sc, 0.015 * sc), w2, dark)
            self.wings.append((pv, w2, sx))

    # -- per-frame pose
    def pose(self, t, env):
        s = self.s; sc = s.get("scale", 1.0)
        v = s.get("speed", 1.2); hd = math.radians(s.get("heading", 0.0))
        x = s["x"] + math.sin(hd) * v * t; y = s["y"] + math.cos(hd) * v * t
        if self.kind == "bird":
            z = s.get("z", 14) + 0.6 * math.sin(0.9 * t + self.t0 * 6)
            self.root.location = (x, y, z); self.root.rotation_euler = (0.08 * math.sin(1.3 * t), 0.15 * math.sin(0.9 * t), -hd)
            fl = math.sin(2 * math.pi * 3.2 * (t + self.t0))
            for pv, w2, sx in self.wings: pv.rotation_euler = (0, sx * 0.75 * fl, 0); w2.rotation_euler = (0, sx * 0.5 * math.sin(2 * math.pi * 3.2 * (t + self.t0) - 0.9), 0)
            return
        if self.kind == "ship":
            z = 0.0; self.root.location = (x, y, z + 0.25 * math.sin(0.8 * t + self.t0 * 5)); self.root.rotation_euler = (0.045 * math.sin(0.7 * t + 1), 0.06 * math.sin(0.55 * t), -hd)
            self.sail.rotation_euler.x = 0.05 * math.sin(1.2 * t); return
        z = float(height(np.array(x), np.array(y), env)); self.root.rotation_euler = (0, 0, -hd); self.root.location = (x, y, z)
        if self.kind in ("elephant", "camel"):
            hz = 0.62 if self.kind == "elephant" else 0.8; ph = 2 * math.pi * hz * (t + self.t0)
            self.body.location.z = 0.05 * sc * abs(math.sin(ph)); self.body.rotation_euler = (0.015 * math.sin(ph * 2), 0.03 * math.sin(ph), 0)
            if self.kind == "elephant":
                for i, lg in enumerate(self.legs): lg.rotation_euler.x = 0.5 * math.sin(ph + (math.pi if i in (1, 2) else 0))
                for i, tk in enumerate(self.trunk): tk.rotation_euler.x = 0.14 * math.sin(ph * 0.5 + i * 0.7)
                self.tail.rotation_euler.y = 0.4 * math.sin(ph * 0.8)
            else:
                for i, (u, l) in enumerate(self.legs):
                    q = ph + (math.pi if i in (1, 2) else 0); u.rotation_euler.x = 0.45 * math.sin(q); l.rotation_euler.x = -0.4 * max(0, math.sin(q + 1.0))
                self.neck.rotation_euler.x = 0.08 * math.sin(ph); self.tail.rotation_euler.x = 0.3 * math.sin(ph * 1.3)
            return
        hz = 1.0 * (v / 1.2); ph = 2 * math.pi * hz * (t + self.t0)
        self.body.location.z = 0.05 * sc * abs(math.sin(ph)) * 2; self.body.rotation_euler = (0.03 * math.sin(ph * 0.5), 0.05 * math.sin(ph), 0.03 * math.sin(ph))
        stride = 0.34 * sc
        self.footL.location.y = stride * math.sin(ph); self.footR.location.y = -stride * math.sin(ph)
        self.footL.location.z = 0.05 * sc + 0.1 * sc * max(0, math.cos(ph)); self.footR.location.z = 0.05 * sc + 0.1 * sc * max(0, -math.cos(ph))
        holding = hasattr(self, "spear")
        self.armL.rotation_euler.x = (0.2 if holding else 0.5 * math.sin(ph)); self.elbL.rotation_euler.x = -0.35 if holding else -0.25 - 0.2 * max(0, math.sin(ph))
        self.armR.rotation_euler.x = -0.5 * math.sin(ph); self.elbR.rotation_euler.x = -0.25 - 0.2 * max(0, -math.sin(ph))
        self.cape.rotation_euler.x = 0.1 + 0.08 * math.sin(ph * 0.7 + 1.2) + self.env.get("wind", 0.4) * 0.3
        if holding: self.spear.rotation_euler.x = 0.04 * math.sin(ph)

def build_props(env, spec_props, actors_hint):
    """Scatter scenery (seeded): palms, rocks, tents. Kept away from the central walking corridor."""
    rng = np.random.default_rng(env["seed"] * 7 + 3); sway = []
    for p in spec_props:
        kind = p["type"]; n = p.get("count", 4)
        for i in range(n):
            x = float(rng.uniform(-55, 55)); y = float(rng.uniform(8, 95))
            if abs(x) < 7 and kind != "rock_small": x += 11 * (1 if x >= 0 else -1)
            z = float(height(np.array(x), np.array(y), env))
            if kind == "palm":
                tr = lathe("trunk", [(0.28, 0), (0.2, 2.5), (0.16, 5), (0.14, 7.5)], 12, (0.05, 8), (1, 1), None, mat("trunk", (0.25, 0.17, 0.09), 0.9), loc=(x, y, z))
                top = empty("palmtop", (x, y, z + 7.4)); fr = mat("frond", (0.06, 0.2, 0.05), 0.8)
                for k in range(9):
                    pv = empty("fr", (0, 0, 0), top); pv.rotation_euler = (0, 0, 2 * math.pi * k / 9)
                    f = prim("cone", (0, 1.9, -0.2), (0.35, 0.05, 4.0), pv, fr, rot=(math.radians(110 + 12 * (k % 3)), 0, 0), r2=0.0); f.scale = (0.45, 0.03, 4.0)
                    sway.append((top, float(rng.uniform(0, 6))))
            elif kind in ("rock", "rock_small"):
                sc = float(rng.uniform(0.8, 2.6)) * (0.4 if kind == "rock_small" else 1.0)
                bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1, location=(x, y, z + sc * 0.3)); o = bpy.context.object
                o.scale = (sc * rng.uniform(0.8, 1.6), sc * rng.uniform(0.8, 1.4), sc * rng.uniform(0.5, 0.9)); o.rotation_euler.z = float(rng.uniform(0, 6))
                import bmesh
                for v in o.data.vertices: v.co += Vector(tuple(float(q) for q in rng.normal(0, 0.12, 3)))
                solid(o, mat("rock", rgb(env.get("rock", "#6e5f52")), 0.95))
                for q in o.data.polygons: q.use_smooth = False
            elif kind == "tent":
                cl = mat("tent", rgb(p.get("color", "#6b4f3a")), 0.95)
                lathe("tent", [(2.4, 0), (2.2, 1.2), (1.2, 2.2), (0.15, 3.0)], 6, (0.0, 1), (1.0, 0.8), None, cl, loc=(x, y, z)); prim("cyl", (x, y, z + 3.2), (0.05, 0.05, 1.2), None, mat("pole", (0.2, 0.12, 0.06)))
    return sway

# ---------------------------------------------------------------------------------------------------------- scene
ENVS = {  # name -> parameters (sun elevation deg, colors, terrain, ocean...)
    "desert_dawn":   dict(kind="land", sun=7, sun_col=(1.0, 0.62, 0.34), sun_e=4.0, sky="nishita", sand="#c98b4f", dune=1.0, mtn_start=180, mtn_h=34, wind=0.5, dust=2.0),
    "desert_night":  dict(kind="land", sun=-90, moon=True, sand="#27264a", dune=1.0, mtn_start=180, mtn_h=34, wind=0.3, night=True),
    "mountain_dawn": dict(kind="land", sun=9, sun_col=(1.0, 0.72, 0.5), sun_e=3.5, sky="nishita", sand="#6f6a63", dune=0.5, mtn_start=60, mtn_h=70, wind=0.6, dust=1.2),
    "sea_calm":      dict(kind="sea", sun=22, sun_col=(1.0, 0.9, 0.75), sun_e=3.5, sky="nishita", water="#0f5c80", mtn_start=9e9, mtn_h=0, dune=0, wind=0.5, chop=0.9),
    "night_sea":     dict(kind="sea", sun=-90, moon=True, water="#08203a", mtn_start=9e9, mtn_h=0, dune=0, wind=0.4, night=True, chop=0.7),
    "sea_storm":     dict(kind="sea", sun=3, sun_col=(0.5, 0.55, 0.6), sun_e=1.0, sky="nishita", water="#143040", mtn_start=9e9, mtn_h=0, dune=0, wind=1.0, chop=2.4, dust=6.0),
    "sky_stars":     dict(kind="land", sun=-90, moon=True, sand="#1a1a38", dune=0.8, mtn_start=140, mtn_h=26, wind=0.2, night=True),
}

def build_world(env):
    w = bpy.data.worlds.new("w"); bpy.context.scene.world = w; w.use_nodes = True
    nt = w.node_tree; nt.nodes.clear(); out = nt.nodes.new("ShaderNodeOutputWorld"); bg = nt.nodes.new("ShaderNodeBackground")
    if env.get("night"):
        tc = nt.nodes.new("ShaderNodeTexCoord"); no = nt.nodes.new("ShaderNodeTexNoise"); no.inputs["Scale"].default_value = 900; no.inputs["Detail"].default_value = 0
        cr = nt.nodes.new("ShaderNodeValToRGB"); cr.color_ramp.elements[0].position = 0.905; cr.color_ramp.elements[1].position = 0.915
        mixc = nt.nodes.new("ShaderNodeMix"); mixc.data_type = "RGBA"; mixc.inputs["A"].default_value = (0.02, 0.035, 0.085, 1); mixc.inputs["B"].default_value = (1, 0.95, 0.85, 1)
        nt.links.new(tc.outputs["Generated"], no.inputs["Vector"]); nt.links.new(no.outputs["Fac"], cr.inputs["Fac"]); nt.links.new(cr.outputs["Color"], mixc.inputs["Factor"])
        nt.links.new(mixc.outputs["Result"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = 1.0
    else:
        sky = nt.nodes.new("ShaderNodeTexSky"); sky.sky_type = "MULTIPLE_SCATTERING"
        sky.sun_elevation = math.radians(env["sun"]); sky.sun_rotation = math.radians(150); sky.aerosol_density = env.get("dust", 2.0); sky.air_density = 1.0
        sky.sun_disc = True; sky.sun_intensity = 0.4
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = env.get("sky_str", 0.12)
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

def build_lights(env):
    if env.get("night"):
        bpy.ops.object.light_add(type="SUN", rotation=(math.radians(58), 0, math.radians(200)))
        l = bpy.context.object; l.data.energy = 2.4; l.data.color = (0.62, 0.72, 1.0); l.data.angle = math.radians(3)
        moon = prim("sphere", (-60, 210, 90), (9, 9, 9), None, mat("moon", (1, 0.97, 0.85), emit=18.0))
    else:
        bpy.ops.object.light_add(type="SUN", rotation=(math.radians(90 - env["sun"]), 0, math.radians(150 + 180)))
        l = bpy.context.object; l.data.energy = env.get("sun_e", 3.5); l.data.color = env.get("sun_col", (1, 0.8, 0.6)); l.data.angle = math.radians(1.2)

def build_ground(env, cam_focus):
    if env["kind"] == "sea":
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=160, y_subdivisions=160, size=900); g = bpy.context.object
        solid(g, mat("sea", rgb(env["water"]), 0.12, metallic=0.0))
        m = g.modifiers.new("Ocean", "OCEAN"); m.geometry_mode = "GENERATE"; m.resolution = 14; m.spatial_size = 80
        m.wave_scale = 0.55 * env.get("chop", 1); m.choppiness = 1.2; m.wind_velocity = 14 * env.get("wind", 0.5) + 6; m.use_foam = False
        return g, m
    n = 260; size = 900
    u = np.linspace(-1, 1, n); xs = size / 2 * np.sign(u) * np.abs(u) ** 1.9; ys = -30 + 560 * np.linspace(0, 1, n) ** 2.2
    X, Y = np.meshgrid(xs, ys); Z = height(X, Y, env)
    me = bpy.data.meshes.new("terrain"); verts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = i * n + j, i * n + j + 1, (i + 1) * n + j + 1, (i + 1) * n + j
            faces += [(a, b, c), (a, c, d)]                                   # consistent triangulation: no quad-diagonal checker pattern
    me.from_pydata(verts.tolist(), [], faces); me.update()
    try: me.shade_smooth()
    except Exception: pass
    g = bpy.data.objects.new("terrain", me); bpy.context.collection.objects.link(g)
    for p in me.polygons: p.use_smooth = True
    solid(g, mat("sand", rgb(env["sand"]), 0.95)); return g, None

def build_clouds(env, count=9):
    cl = []
    for i in range(count):
        rng = np.random.default_rng(env["seed"] * 31 + i)
        c = empty(f"cloud{i}", (float(rng.uniform(-300, 300)), float(rng.uniform(150, 420)), float(rng.uniform(70, 130))))
        m = mat("cloud", (0.9, 0.9, 0.95) if not env.get("night") else (0.08, 0.09, 0.15), 1.0)
        for k in range(5):
            prim("sphere", (float(rng.uniform(-14, 14)), float(rng.uniform(-6, 6)), float(rng.uniform(-2, 3))), (float(rng.uniform(16, 30)), float(rng.uniform(10, 16)), float(rng.uniform(5, 9))), c, m)
        cl.append(c)
    return cl

# ---------------------------------------------------------------------------------------------------------- camera
def ease(u): return u * u * (3 - 2 * u)

def _cr(p0, p1, p2, p3, t):
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)

def sample_path(keys, u, name):
    pts = [Vector(k[name]) for k in keys]; us = [k["u"] for k in keys]
    u = min(max(u, us[0]), us[-1])
    i = max(j for j in range(len(us)) if us[j] <= u) if u < us[-1] else len(us) - 2
    t = (u - us[i]) / max(us[i + 1] - us[i], 1e-6)
    p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, len(pts) - 1)]
    return _cr(p0, p1, p2, p3, t)

def centroid(actors, focus):
    ps = [a.root.location.copy() for a in actors if a.kind != "bird"]
    if not ps: return Vector(focus)
    c = sum(ps, Vector()) / len(ps); c.z += 1.3; return c

def camera_pose(cam, u, t, actors, env):
    """Camera path = keyframes {u,pos,look} sampled with Catmull-Rom (smooth). If cam['rel'], pos/look are offsets from the
    live centroid of the actors, so the camera keeps tracking subjects that walk. Terrain-aware: never goes below the ground."""
    e = ease(u) if cam.get("ease", "smooth") == "smooth" else u
    P = sample_path(cam["path"], e, "pos"); T = sample_path(cam["path"], e, "look")
    if cam.get("rel"):
        c = centroid(actors, cam.get("focus", [0, 25, 1.5])); P = c + P; T = c + T
    gz = float(height(np.array(P.x), np.array(P.y), env)) if env["kind"] == "land" else 0.0
    P.z = max(P.z, gz + cam.get("clearance", 0.45))
    d = cam.get("drift", 0.04)
    P = P + Vector((d * math.sin(0.7 * t), d * math.sin(0.5 * t + 1), d * 0.6 * math.sin(0.9 * t + 2)))
    return P, T

def look(obj, target):
    d = (Vector(target) - obj.location); obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

def main(spec):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene; W, H = spec["res"]; fps = spec["fps"]
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
    sc.render.fps = fps; sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.compression = 3
    sc.render.engine = spec.get("engine", "CYCLES")
    if sc.render.engine == "CYCLES":
        sc.cycles.device = "CPU"
        if spec.get("device") == "GPU":                       # use a GPU only if Cycles can actually find one; otherwise stay on CPU
            try:
                pr = bpy.context.preferences.addons["cycles"].preferences
                for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
                    try:
                        pr.compute_device_type = kind; pr.get_devices()
                        if any(d.type != "CPU" for d in pr.devices):
                            for d in pr.devices: d.use = d.type != "CPU"
                            sc.cycles.device = "GPU"; break
                    except Exception: continue
            except Exception: pass
        sc.cycles.samples = spec.get("samples", 16); sc.cycles.use_denoising = True
        try: sc.cycles.denoiser = "OPENIMAGEDENOISE"
        except Exception: pass
        sc.cycles.max_bounces = 3; sc.cycles.diffuse_bounces = 2; sc.cycles.glossy_bounces = 2; sc.cycles.transmission_bounces = 0
        sc.cycles.use_adaptive_sampling = True; sc.cycles.adaptive_threshold = 0.05
    sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"
    env = dict(ENVS[spec["env"]]); env["seed"] = spec.get("seed", 1); env.update(spec.get("env_override", {}))
    build_world(env); build_lights(env); ground, ocean = build_ground(env, None); clouds = build_clouds(env); sway = build_props(env, spec.get('props', []), None)
    pal = spec["palette"]; actors = [Actor(a, env, pal) for a in spec.get("actors", [])]
    cd = bpy.data.cameras.new("cam"); cd.sensor_fit = "VERTICAL"; cd.sensor_height = 36; cd.lens = spec["camera"].get("lens", 30)
    cam = bpy.data.objects.new("cam", cd); bpy.context.collection.objects.link(cam); sc.camera = cam
    n = spec["frames"]; t0 = spec.get("t0", 0.0)
    for f in range(n):
        t = t0 + f / fps; u = f / max(n - 1, 1)
        for a in actors: a.pose(t, env)
        for i, c in enumerate(clouds): c.location.x = c.location.x + 0.012 * (1 + 0.2 * (i % 3))
        if ocean: ocean.time = t * 0.9
        for top, ph in sway: top.rotation_euler = (0.03 * math.sin(0.9 * t + ph), 0.03 * math.cos(0.7 * t + ph), 0)
        P, T = camera_pose(spec["camera"], u, t, actors, env); cam.location = P; look(cam, T)
        sc.render.filepath = f"{spec['out']}/f{f:05d}.png"
        bpy.ops.render.render(write_still=True)
        print("frame", f, flush=True)

if __name__ == "__main__":
    main(json.load(open(sys.argv[1])))
