"""Object names for everything the add-on makes: "<thing>-<style>-<n>", e.g.
cottage-timber-1, tree-pine-2, rock-boulder-1, sofa-old-3seat-1.

<n> is one more than the highest number already used by that prefix (objects and
collections both count), so names never clash and never get Blender's ".001".
"""

import re

import bpy

_AUTO = re.compile(r"^([a-z0-9]+(?:-[a-z0-9]+)*)-(\d+)$")


def slug(*parts):
    """'Old Wood', 'MAPLE_AUTUMN' -> 'old-wood', 'maple-autumn'; parts joined with '-'."""
    words = []
    for p in parts:
        s = re.sub(r"[^a-z0-9]+", "-", str(p).lower()).strip("-")
        if s:
            words.append(s)
    return "-".join(words)


def next_name(prefix):
    """The next free '<prefix>-<n>'."""
    prefix = slug(prefix)
    pat = re.compile(re.escape(prefix) + r"-(\d+)$")
    used = [int(m.group(1)) for coll in (bpy.data.objects, bpy.data.collections)
            for name in coll.keys() if (m := pat.match(name))]
    return f"{prefix}-{max(used, default=0) + 1}"


def prefix_of(name):
    """'cottage-timber-3' -> 'cottage-timber'; None for a name not made by next_name."""
    m = _AUTO.match(name)
    return m.group(1) if m else None


def keep_or_next(name, prefix):
    """Keep `name` when it already carries `prefix`, else the next name for `prefix`
    (used when a rebuild or a settings change turns a piece into another kind)."""
    return name if prefix_of(name) == slug(prefix) else next_name(prefix)


def rename_if_auto(ob, prefix):
    """Follow a kind change (e.g. a tree's species): rename `ob` if its current name was
    made by next_name for another prefix. Names the user typed are left alone."""
    old = prefix_of(ob.name)
    if old is not None and old != slug(prefix):
        ob.name = next_name(prefix)
        if ob.data is not None and ob.data.users == 1:
            ob.data.name = ob.name


def safe(name):
    """For file names and engine asset names: keeps letters, digits, '-' and '_'."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name)
