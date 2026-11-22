"""The branch skeleton the growers fill in, and its conversion to a mesh datablock."""

import math
import random

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector, noise

GOLDEN_ANGLE = 2.39996
UP = np.array([0.0, 0.0, 1.0])


def lerp(a, b, t):
    return a + (b - a) * t


def rot_z(v, angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2]])


def horizontal(v):
    h = np.array([v[0], v[1], 0.0])
    n = np.linalg.norm(h)
    return h / n if n > 1e-6 else np.array([1.0, 0.0, 0.0])


class Warp:
    """Whole-tree deformation applied to everything a grower adds: a twist about the vertical
    axis that builds up over `twist_height`, then a lean that grows with height. The lean is
    a shear, so the trunk sweeps over while the foliage pads stay level."""

    def __init__(self, p, twist_height):
        self.twist = p["twist"]
        self.twist_height = max(twist_height, 1e-3)
        k = math.tan(p["lean"]) / (2.0 * p["height"])
        self.lean = np.array([math.cos(p["lean_dir"]) * k, math.sin(p["lean_dir"]) * k, 0.0])

    def angle(self, z):
        return self.twist * min(max(z / self.twist_height, 0.0), 1.0)

    def point(self, p):
        z = max(float(p[2]), 0.0)
        return rot_z(p, self.angle(p[2])) + self.lean * (z * z)

    def direction(self, p, d):
        return rot_z(d, self.angle(p[2]))


def smooth_joint(points, radii, joint, reach=3, passes=3):
    """Round off the corner where two runs of a chain meet at index `joint`."""
    points, radii = [np.asarray(q, float) for q in points], list(radii)
    for _ in range(passes):
        old_p, old_r = list(points), list(radii)
        for k in range(max(1, joint - reach), min(len(points) - 1, joint + reach)):
            points[k] = 0.25 * old_p[k - 1] + 0.5 * old_p[k] + 0.25 * old_p[k + 1]
            radii[k] = 0.25 * old_r[k - 1] + 0.5 * old_r[k] + 0.25 * old_r[k + 1]
    return points, radii


class Skeleton:
    def __init__(self, warp=None):
        self.warp = warp
        self.points, self.radius, self.level, self.length, self.edges = [], [], [], [], []
        self.leaf_pos, self.leaf_rot, self.leaf_scale, self.leaf_rank = [], [], [], []
        self.leaf_card = []

    def branch(self, points, radii, level):
        if self.warp is not None:
            points = [self.warp.point(q) for q in points]
        base = len(self.points)
        travelled = 0.0
        for i, (p, r) in enumerate(zip(points, radii)):
            if i:
                travelled += float(np.linalg.norm(np.asarray(p) - np.asarray(points[i - 1])))
                self.edges.append((base + i - 1, base + i))
            self.points.append(tuple(float(c) for c in p))
            self.radius.append(float(r))
            self.level.append(level)
            self.length.append(travelled)

    def leaf(self, position, direction, scale, roll=0.0, rank=None, up=(0.0, 0.0, 1.0), variant=0):
        """Add a foliage card. The card's +Y points along `direction`, +Z is its top side.
        `variant` picks one of the species' cards, unless the species mixes them (leaf_variants)."""
        if self.warp is not None:
            direction = self.warp.direction(position, direction)
            position = self.warp.point(position)
        y = Vector(direction).normalized()
        x = y.cross(Vector(up))
        if x.length < 1e-4:
            x = Vector((1.0, 0.0, 0.0))
        x.normalize()
        z = x.cross(y)
        if roll:
            q = Quaternion(y, roll)
            x, z = q @ x, q @ z
        euler = Matrix((x, y, z)).transposed().to_euler("XYZ")
        if rank is None:
            # Low-discrepancy sequence: any density threshold keeps an evenly spread subset.
            rank = (len(self.leaf_pos) * 0.6180339887) % 1.0
        self.leaf_pos.append(tuple(float(c) for c in position))
        self.leaf_rot.append(tuple(euler))
        self.leaf_scale.append(tuple(float(c) for c in scale))
        self.leaf_rank.append(float(rank))
        self.leaf_card.append(variant)

    def leaf_variants(self, mix, seed, canopy):
        """Which leaf-atlas cell each foliage card uses, in the shares given by `mix`.
        Cells follow a smooth noise field, so each colour forms patches in the crown, with
        neighbouring cells of the atlas next to each other (green fades to red through pale)."""
        count = len(self.leaf_pos)
        if not mix or count == 0:
            return np.array(self.leaf_card, np.int32)
        rng = random.Random(seed + 7919)
        offset = Vector((rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)))
        frequency = 2.2 / max(canopy, 0.1)
        field = np.array([noise.noise(Vector(q) * frequency + offset) + rng.uniform(-0.12, 0.12)
                          for q in self.leaf_pos])
        quantile = (np.argsort(np.argsort(field)) + 0.5) / count      # evenly spread 0..1
        edges = np.cumsum(mix) / max(sum(mix), 1e-6)
        return np.minimum(np.searchsorted(edges, quantile), len(mix) - 1).astype(np.int32)

    def to_mesh(self, name, mix=None, seed=0, canopy=1.0):
        """A mesh datablock with the attributes nodes.py expects."""
        sk = self
        n_branch, n_leaf = len(sk.points), len(sk.leaf_pos)
        total = n_branch + n_leaf

        mesh = bpy.data.meshes.new(name)
        mesh.vertices.add(total)
        mesh.edges.add(len(sk.edges))
        mesh.vertices.foreach_set("co", np.array(sk.points + sk.leaf_pos, np.float32).ravel())
        if sk.edges:
            mesh.edges.foreach_set("vertices", np.array(sk.edges, np.int32).ravel())

        def attribute(attr_name, data_type, values, field="value"):
            mesh.attributes.new(attr_name, data_type, "POINT").data.foreach_set(field, values)

        attribute("radius", "FLOAT", np.array(sk.radius + [0.0] * n_leaf, np.float32))
        attribute("level", "INT", np.array(sk.level + [0] * n_leaf, np.int32))
        attribute("len", "FLOAT", np.array(sk.length + [0.0] * n_leaf, np.float32))
        attribute("leaf", "BOOLEAN", np.array([False] * n_branch + [True] * n_leaf, bool))
        attribute("rank", "FLOAT", np.array([0.0] * n_branch + sk.leaf_rank, np.float32))
        attribute("variant", "INT", np.concatenate(
            [np.zeros(n_branch, np.int32), sk.leaf_variants(mix, seed, canopy)]))
        zeros = [(0.0, 0.0, 0.0)] * n_branch
        attribute("rot", "FLOAT_VECTOR", np.array(zeros + sk.leaf_rot, np.float32).ravel(), "vector")
        attribute("lscale", "FLOAT_VECTOR", np.array(zeros + sk.leaf_scale, np.float32).ravel(), "vector")
        mesh.update()
        return mesh
