"""Builds the shared Geometry Nodes group that turns a skeleton into a tree.

Input geometry is a mesh made by species.py:
  * edge chains = branches, with point attributes
        radius (float)  tube radius
        level  (int)    0 trunk, 1 limbs/roots, 2 secondary branches, 3 twigs
        len    (float)  distance along the branch in metres (bark V coordinate)
  * loose vertices = foliage anchors, with point attributes
        leaf   (bool)   True
        rank   (float)  0..1, cards with rank below the density threshold are kept
        variant (int)   which card of the species' set to use (leaf atlas cell)
        rot    (vector) XYZ euler orientation of the card
        lscale (vector) card scale

The group does: one of three game LODs (picked by the "LOD" input),
triangle-budget scaling, bark tubes with UVs, and foliage card instancing.

A tight triangle budget is spent on foliage first: the bark loses resolution, then its
twigs and secondary branches, while the remaining cards get simpler and larger so the
crown stays full.
"""

import math

import bpy

GROUP_NAME = "TreeGen_Tree"
VERSION = 9

BASE_LEAF_FRACTION = 0.7          # share of foliage anchors used at natural quality
LOD_SIDES = (1.0, 0.6, 0.4)       # tube sides multiplier per LOD
LOD_SEGMENT = (1.0, 2.0, 3.5)     # segment length multiplier per LOD
LOD_LEAF_FRACTION = (1.0, 0.55, 0.38)
LOD_LEAF_WIDTH = (1.0, 1.25, 1.55)  # cards get wider as they get fewer
LOD_MAX_LEVEL = (3.0, 2.0, 1.0)   # deepest branch level kept per LOD
GROUP_SIDES = (1.0, 0.6, 0.4)     # trunk / limbs / small branches
GROUP_SEGMENT = (1.0, 1.0, 1.5)
BARK_U_FRACTION = (1.0, 0.6, 0.3)   # texture repeats around trunk / limbs / small branches
GROUP_MIN_SIDES = (5.0, 3.0, 3.0)

TIGHT_LEAF_SHARE = 0.6            # share of the triangles foliage gets when the budget is far below natural
CARD_TIERS = (0.12, 0.05)         # below these LOD 0 leaf fractions, use the LOD 1 / LOD 2 card instead
CARD_GROW_POWER = 0.4             # fewer cards get larger: (natural fraction / fraction) ** power ...
CARD_GROW_MAX = 2.2               # ... up to this
MIN_BARK_QUALITY = 0.45           # tube resolution never drops below this share of natural
PRUNE_BELOW = 0.2                 # bark budget ratio under which twigs, then branches, are removed


class _Builder:
    def __init__(self, group):
        self.group = group
        self.nodes = group.nodes
        self.links = group.links

    def node(self, type_name, label=None, **props):
        node = self.nodes.new(type_name)
        for key, value in props.items():
            setattr(node, key, value)
        if label:
            node.label = label
        return node

    def put(self, socket, value):
        """Link a socket or set a constant."""
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, socket)
        else:
            socket.default_value = value

    def math(self, operation, a, b=None, c=None, label=None):
        node = self.node("ShaderNodeMath", label, operation=operation)
        for socket, value in zip(node.inputs, (a, b, c)):
            if value is not None:
                self.put(socket, value)
        return node.outputs[0]

    def clamp(self, value, low, high):
        return self.math("MINIMUM", self.math("MAXIMUM", value, low), high)

    def named(self, name, data_type):
        node = self.node("GeometryNodeInputNamedAttribute", name, data_type=data_type)
        node.inputs["Name"].default_value = name
        return node.outputs["Attribute"]

    def by_lod(self, lod, values, data_type="FLOAT", label=None):
        node = self.node("GeometryNodeIndexSwitch", label, data_type=data_type)
        while len(node.index_switch_items) < len(values):
            node.index_switch_items.new()
        self.links.new(lod, node.inputs[0])
        for socket, value in zip(list(node.inputs)[1:], values):
            self.put(socket, value)
        return node.outputs[0]


def _value_input(node):
    return next(s for s in node.inputs if s.name == "Value" and s.enabled)


def _layout(group):
    depth = {}

    def visit(node):
        if node.name in depth:
            return depth[node.name]
        depth[node.name] = 0
        best = 0
        for socket in node.inputs:
            for link in socket.links:
                best = max(best, visit(link.from_node) + 1)
        depth[node.name] = best
        return best

    columns = {}
    for node in group.nodes:
        columns.setdefault(visit(node), []).append(node)
    for column, nodes in columns.items():
        for row, node in enumerate(nodes):
            node.location = (column * 240.0, -row * 220.0)


def _interface(group):
    def add(name, socket_type, default=None, low=None, high=None, in_out="INPUT"):
        socket = group.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
        if default is not None:
            socket.default_value = default
        if low is not None:
            socket.min_value = low
        if high is not None:
            socket.max_value = high
        return socket

    add("Geometry", "NodeSocketGeometry", in_out="OUTPUT")
    add("Geometry", "NodeSocketGeometry")
    add("LOD", "NodeSocketInt", 0, 0, 2).description = "Level of detail to build: 0 hero, 1 mid, 2 far"
    add("Triangles Min", "NodeSocketInt", 10000, 0)
    add("Triangles Max", "NodeSocketInt", 30000, 0)
    add("Budget Trim", "NodeSocketFloat", 1.0, 0.0001, 100.0).description = \
        "Correction to the bark's share, applied by the add-on after measuring the real triangle count"
    add("Leaf Trim", "NodeSocketFloat", 1.0, 0.001, 1.0).description = \
        "Cut to the foliage's share, used only when the bark alone cannot get under the budget"
    add("Leaf Scale", "NodeSocketFloat", 1.0, 0.0)
    add("Segment Length", "NodeSocketFloat", 0.35, 0.01)
    add("Trunk Sides", "NodeSocketInt", 12, 3, 32)
    add("Bark V Scale", "NodeSocketFloat", 0.25, 0.0)
    add("Bark U Tiles", "NodeSocketInt", 1, 1, 32).description = \
        "Times the bark texture repeats around the trunk; limbs and twigs repeat less"
    for index in range(3):
        add("Card LOD %d" % index, "NodeSocketCollection").description = \
            "Foliage cards for this LOD, one object per variant, each with its leaf material"
    add("Bark Material", "NodeSocketMaterial")
    add("Realize", "NodeSocketBool", False).description = "Turn foliage instances into real mesh (for baking)"


def _build(group):
    b = _Builder(group)
    _interface(group)
    gin = b.node("NodeGroupInput").outputs
    gout = b.node("NodeGroupOutput")

    # ---- 1. Level of detail (chosen by the add-on: preview or export) -----
    lod = gin["LOD"]

    lod_sides = b.by_lod(lod, LOD_SIDES, label="LOD Sides")
    lod_segment = b.by_lod(lod, LOD_SEGMENT, label="LOD Segment")
    lod_leaf_fraction = b.by_lod(lod, LOD_LEAF_FRACTION, label="LOD Leaf Fraction")
    lod_leaf_width = b.by_lod(lod, LOD_LEAF_WIDTH, label="LOD Leaf Width")
    lod_max_level = b.by_lod(lod, LOD_MAX_LEVEL, label="LOD Max Level")

    # ---- 2. Split skeleton from foliage anchors ----------------------------
    split = b.node("GeometryNodeSeparateGeometry", "Split Leaves / Skeleton", domain="POINT")
    b.links.new(gin["Geometry"], split.inputs["Geometry"])
    b.links.new(b.named("leaf", "BOOLEAN"), split.inputs["Selection"])
    leaf_points = split.outputs["Selection"]

    to_curve = b.node("GeometryNodeMeshToCurve")
    b.links.new(split.outputs["Inverted"], to_curve.inputs["Mesh"])
    set_radius = b.node("GeometryNodeSetCurveRadius")
    b.links.new(to_curve.outputs["Curve"], set_radius.inputs["Curve"])
    b.links.new(b.named("radius", "FLOAT"), set_radius.inputs["Radius"])
    curves = set_radius.outputs["Curve"]

    level = b.named("level", "INT")
    group_selection = (
        b.math("LESS_THAN", level, 0.5),
        b.math("COMPARE", level, 1.0, 0.25),
        b.math("GREATER_THAN", level, 1.5),
    )
    group_curves, group_length, group_count = [], [], []
    for index, selection in enumerate(group_selection):
        sep = b.node("GeometryNodeSeparateGeometry", ("Trunk", "Limbs", "Small Branches")[index],
                     domain="CURVE")
        b.links.new(curves, sep.inputs["Geometry"])
        b.links.new(selection, sep.inputs["Selection"])
        length = b.node("GeometryNodeCurveLength")
        b.links.new(sep.outputs["Selection"], length.inputs["Curve"])
        size = b.node("GeometryNodeAttributeDomainSize", component="CURVE")
        b.links.new(sep.outputs["Selection"], size.inputs["Geometry"])
        group_curves.append(sep.outputs["Selection"])
        group_length.append(length.outputs["Length"])
        group_count.append(size.outputs["Spline Count"])

    # ---- 3. Triangle budget ---------------------------------------------
    # Estimate the LOD 0 triangle count at natural quality, then scale tube
    # resolution and foliage density so the estimate lands inside Min..Max.
    sides_in, segment_in = gin["Trunk Sides"], gin["Segment Length"]
    natural_sides = [sides_in] + [
        b.math("MAXIMUM", b.math("ROUND", b.math("MULTIPLY", sides_in, f)), 3.0)
        for f in GROUP_SIDES[1:]]
    bark_estimate = None
    for index in range(3):
        segments = b.math("ADD",
                          b.math("DIVIDE", group_length[index],
                                 b.math("MULTIPLY", segment_in, GROUP_SEGMENT[index])),
                          b.math("MULTIPLY", group_count[index], 0.5))
        tris = b.math("MULTIPLY", b.math("MULTIPLY", segments, natural_sides[index]), 2.0)
        bark_estimate = tris if bark_estimate is None else b.math("ADD", bark_estimate, tris)

    # Foliage cards: a collection per LOD, one child per variant (all with the same face count).
    cards, card_faces = [], []
    for index in range(3):
        info = b.node("GeometryNodeCollectionInfo", "Cards LOD %d" % index, transform_space="ORIGINAL")
        info.inputs["Separate Children"].default_value = True
        info.inputs["Reset Children"].default_value = True
        b.links.new(gin["Card LOD %d" % index], info.inputs["Collection"])
        real = b.node("GeometryNodeRealizeInstances")
        b.links.new(info.outputs[0], real.inputs["Geometry"])
        faces = b.node("GeometryNodeAttributeDomainSize", "Card Triangles", component="MESH")
        b.links.new(real.outputs["Geometry"], faces.inputs["Geometry"])
        variants = b.node("GeometryNodeAttributeDomainSize", "Card Variants", component="INSTANCES")
        b.links.new(info.outputs[0], variants.inputs["Geometry"])
        cards.append(info.outputs[0])
        card_faces.append(b.math("DIVIDE", faces.outputs["Face Count"],
                                 b.math("MAXIMUM", variants.outputs["Instance Count"], 1.0)))
    leaf_size = b.node("GeometryNodeAttributeDomainSize", "Leaf Anchors", component="MESH")
    b.links.new(leaf_points, leaf_size.inputs["Geometry"])
    anchors = leaf_size.outputs["Point Count"]
    leaf_estimate = b.math("MULTIPLY", b.math("MULTIPLY", anchors, BASE_LEAF_FRACTION), card_faces[0])

    natural = b.math("MAXIMUM", b.math("ADD", bark_estimate, leaf_estimate), 1.0,
                     label="Natural Triangles")
    target = b.math("MINIMUM", b.math("MAXIMUM", natural, gin["Triangles Min"]),
                    b.math("MAXIMUM", gin["Triangles Max"], gin["Triangles Min"]),
                    label="Target Triangles")

    # Foliage is served first. At or above natural size it keeps its natural share of the
    # triangles; the further the budget drops below that, the closer it gets to TIGHT_LEAF_SHARE.
    squeeze = b.clamp(b.math("DIVIDE", target, natural), 0.0, 1.0)
    natural_share = b.math("DIVIDE", leaf_estimate, natural)
    share = b.math("ADD", TIGHT_LEAF_SHARE,
                   b.math("MULTIPLY", b.math("SUBTRACT", natural_share, TIGHT_LEAF_SHARE), squeeze),
                   label="Leaf Share")
    leaf_target = b.math("MULTIPLY", b.math("MULTIPLY", target, share), gin["Leaf Trim"],
                         label="Leaf Triangles")
    # With few triangles to spend, simpler cards buy more of them: more cards fill a crown
    # better than a few nicely bent ones.
    fraction_0 = b.math("DIVIDE", leaf_target,
                        b.math("MAXIMUM", b.math("MULTIPLY", anchors, card_faces[0]), 1.0))
    tier = b.math("ADD", b.math("LESS_THAN", fraction_0, CARD_TIERS[0]),
                  b.math("LESS_THAN", fraction_0, CARD_TIERS[1]), label="Card Tier")
    tier_faces = b.by_lod(tier, card_faces, label="Tier Card Triangles")
    all_cards = b.math("MAXIMUM", b.math("MULTIPLY", anchors, tier_faces), 1.0)
    leaf_fraction = b.clamp(b.math("DIVIDE", leaf_target, all_cards), 0.0, 1.0)
    card_grow = b.clamp(b.math("POWER", b.math("DIVIDE", BASE_LEAF_FRACTION,
                                               b.math("MAXIMUM", leaf_fraction, 0.01)), CARD_GROW_POWER),
                        1.0, CARD_GROW_MAX)

    # The bark gets what is left. It first loses resolution, then twigs, then secondary branches.
    leaf_triangles = b.math("MULTIPLY", leaf_fraction, all_cards)
    bark_ratio = b.math("MULTIPLY",
                        b.math("DIVIDE", b.math("MAXIMUM", b.math("SUBTRACT", target, leaf_triangles), 0.0),
                               b.math("MAXIMUM", bark_estimate, 1.0)),
                        gin["Budget Trim"], label="Bark Budget Ratio")
    bark_quality = b.clamp(b.math("SQRT", bark_ratio), MIN_BARK_QUALITY, 2.5)
    branch_keep = b.clamp(b.math("DIVIDE", bark_ratio, PRUNE_BELOW), 0.0, 1.0)

    # ---- 4. Bark tubes ------------------------------------------------------
    bark_parts = []
    for index in range(3):
        source = group_curves[index]
        if index == 2:
            # Each branch gets a removal order: twigs (upper half) go before secondary
            # branches (lower half), in a random order within each.
            random = b.node("FunctionNodeRandomValue", "Branch Order", data_type="FLOAT")
            order = b.math("ADD", b.math("MULTIPLY", next(o for o in random.outputs if o.enabled), 0.5),
                           b.math("MULTIPLY", b.math("GREATER_THAN", level, 2.5), 0.5))
            prune = b.node("GeometryNodeDeleteGeometry", "Prune Twigs", domain="CURVE")
            b.links.new(source, prune.inputs["Geometry"])
            b.links.new(b.math("MAXIMUM",
                               b.math("GREATER_THAN", level, b.math("ADD", lod_max_level, 0.5)),
                               b.math("GREATER_THAN", order, branch_keep)),
                        prune.inputs["Selection"])
            source = prune.outputs["Geometry"]

        segment = b.math("MULTIPLY",
                         b.math("DIVIDE", b.math("MULTIPLY", segment_in, GROUP_SEGMENT[index]),
                                bark_quality),
                         lod_segment)
        resample = b.node("GeometryNodeResampleCurve")
        if hasattr(resample, "mode"):
            resample.mode = "LENGTH"
        else:                                   # Blender 5: the mode is a menu socket
            resample.inputs["Mode"].default_value = "Length"
        b.links.new(source, resample.inputs["Curve"])
        b.links.new(segment, resample.inputs["Length"])

        sides = b.clamp(
            b.math("ROUND", b.math("MULTIPLY", b.math("MULTIPLY", natural_sides[index], bark_quality),
                                   lod_sides)),
            GROUP_MIN_SIDES[index], 32.0)
        # An open arc (first and last point coincide) instead of a circle, so
        # the U coordinate runs 0..1 with a proper seam.
        arc = b.node("GeometryNodeCurveArc", "Profile")
        b.put(arc.inputs["Resolution"], b.math("ADD", sides, 1.0))
        arc.inputs["Radius"].default_value = 1.0
        arc.inputs["Start Angle"].default_value = 0.0
        arc.inputs["Sweep Angle"].default_value = 2.0 * math.pi
        capture = b.node("GeometryNodeCaptureAttribute", "Capture U", domain="POINT")
        capture.capture_items.new("FLOAT", "U")
        b.links.new(arc.outputs["Curve"], capture.inputs["Geometry"])
        b.links.new(b.node("GeometryNodeSplineParameter").outputs["Factor"], capture.inputs["U"])

        tube = b.node("GeometryNodeCurveToMesh")
        b.links.new(resample.outputs["Curve"], tube.inputs["Curve"])
        b.links.new(capture.outputs["Geometry"], tube.inputs["Profile Curve"])
        if "Scale" in tube.inputs:              # Blender 4.5+: radius is no longer applied implicitly
            b.links.new(b.node("GeometryNodeInputRadius").outputs[0], tube.inputs["Scale"])

        uv = b.node("ShaderNodeCombineXYZ", "Bark UV")
        tiles = b.math("MAXIMUM", b.math("ROUND", b.math("MULTIPLY", gin["Bark U Tiles"], BARK_U_FRACTION[index])), 1.0)
        b.put(uv.inputs["X"], b.math("MULTIPLY", capture.outputs["U"], tiles))
        b.put(uv.inputs["Y"], b.math("MULTIPLY", b.named("len", "FLOAT"), gin["Bark V Scale"]))
        store = b.node("GeometryNodeStoreNamedAttribute", "Store UVMap",
                       data_type="FLOAT2", domain="CORNER")
        store.inputs["Name"].default_value = "UVMap"
        b.links.new(tube.outputs["Mesh"], store.inputs["Geometry"])
        b.links.new(uv.outputs["Vector"], _value_input(store))
        bark_parts.append(store.outputs["Geometry"])

    join_bark = b.node("GeometryNodeJoinGeometry", "Join Bark")
    for part in reversed(bark_parts):
        b.links.new(part, join_bark.inputs[0])
    weld = b.node("GeometryNodeMergeByDistance", "Weld UV Seam")
    b.links.new(join_bark.outputs[0], weld.inputs["Geometry"])
    weld.inputs["Distance"].default_value = 0.0002
    smooth = b.node("GeometryNodeSetShadeSmooth")
    b.links.new(weld.outputs["Geometry"], smooth.inputs["Geometry"])
    bark_material = b.node("GeometryNodeSetMaterial", "Bark Material")
    b.links.new(smooth.outputs["Geometry"], bark_material.inputs["Geometry"])
    b.links.new(gin["Bark Material"], bark_material.inputs["Material"])

    # ---- 5. Foliage instances ----------------------------------------------
    card = b.by_lod(b.math("MAXIMUM", lod, tier), cards, data_type="GEOMETRY", label="Cards For LOD")

    keep = b.math("LESS_THAN", b.named("rank", "FLOAT"),
                  b.math("MULTIPLY", leaf_fraction, lod_leaf_fraction), label="Density Cull")
    rotation = b.node("FunctionNodeEulerToRotation")
    b.links.new(b.named("rot", "FLOAT_VECTOR"), rotation.inputs[0])
    leaf_scale = b.math("MULTIPLY", gin["Leaf Scale"], card_grow)
    length_scale = b.math("MULTIPLY", leaf_scale,
                          b.math("ADD", 1.0, b.math("MULTIPLY",
                                                    b.math("SUBTRACT", lod_leaf_width, 1.0), 0.35)))
    lod_scale = b.node("ShaderNodeCombineXYZ", "LOD Card Scale")
    b.put(lod_scale.inputs["X"], b.math("MULTIPLY", leaf_scale, lod_leaf_width))
    b.put(lod_scale.inputs["Y"], length_scale)
    b.put(lod_scale.inputs["Z"], length_scale)
    scale_vector = b.node("ShaderNodeVectorMath", operation="MULTIPLY")
    b.links.new(b.named("lscale", "FLOAT_VECTOR"), scale_vector.inputs[0])
    b.links.new(lod_scale.outputs["Vector"], scale_vector.inputs[1])

    instance = b.node("GeometryNodeInstanceOnPoints", "Foliage Instances")
    b.links.new(leaf_points, instance.inputs["Points"])
    b.links.new(keep, instance.inputs["Selection"])
    b.links.new(card, instance.inputs["Instance"])
    instance.inputs["Pick Instance"].default_value = True
    b.links.new(b.named("variant", "INT"), instance.inputs["Instance Index"])
    b.links.new(rotation.outputs[0], instance.inputs["Rotation"])
    b.links.new(scale_vector.outputs["Vector"], instance.inputs["Scale"])
    # Enlarged cards grow about their middle, not out of the crown from their stem.
    recentre = b.node("ShaderNodeCombineXYZ", "Recentre Grown Card")
    b.put(recentre.inputs["Y"],
          b.math("MULTIPLY", b.math("SUBTRACT", b.math("DIVIDE", 1.0, card_grow), 1.0), 0.5))
    shift = b.node("GeometryNodeTranslateInstances")
    b.links.new(instance.outputs["Instances"], shift.inputs["Instances"])
    b.links.new(recentre.outputs["Vector"], shift.inputs["Translation"])
    shift.inputs["Local Space"].default_value = True
    foliage = shift.outputs["Instances"]

    # ---- 6. Output ------------------------------------------------------------
    join = b.node("GeometryNodeJoinGeometry", "Join Tree")
    b.links.new(foliage, join.inputs[0])
    b.links.new(bark_material.outputs["Geometry"], join.inputs[0])
    realize = b.node("GeometryNodeRealizeInstances")
    b.links.new(join.outputs[0], realize.inputs["Geometry"])
    output = b.node("GeometryNodeSwitch", "Realize For Baking", input_type="GEOMETRY")
    b.links.new(gin["Realize"], output.inputs["Switch"])
    b.links.new(join.outputs[0], output.inputs["False"])
    b.links.new(realize.outputs["Geometry"], output.inputs["True"])
    b.links.new(output.outputs[0], gout.inputs["Geometry"])

    _layout(group)


def ensure_group():
    """Return the shared node group, (re)building it if missing or outdated."""
    group = bpy.data.node_groups.get(GROUP_NAME)
    if group is not None and group.get("treegen_version") == VERSION:
        return group
    if group is None:
        group = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    else:
        group.nodes.clear()
        group.interface.clear()
    _build(group)
    group["treegen_version"] = VERSION
    return group


def socket_ids(group):
    """Map input names to the identifiers used as modifier property keys."""
    return {item.name: item.identifier for item in group.interface.items_tree
            if item.item_type == "SOCKET" and item.in_out == "INPUT"}
