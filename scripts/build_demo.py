"""Build a small fictional apartment and a 13-second camera tour in Blender.

Usage from the repository root:
    blender -b --factory-startup --python-exit-code 1 --python scripts/build_demo.py -- --output demo.blend
    blender -b demo.blend -o /tmp/overview_ -F PNG -f 1

All measurements are in metres. The example uses procedural geometry and
materials, and the saved scene plays with ordinary Blender keyframes.
"""

import argparse
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


WIDTH, DEPTH = 8.0, 6.0
WALL_HEIGHT, WALL_THICKNESS = 2.65, 0.14
ENTRY_MIN, ENTRY_MAX = -0.56, 0.58
FPS, END_FRAME = 24, 312

# Room bounds (minimum x, maximum x, minimum y, maximum y).
# The south entry opens into the hall at (0, -DEPTH/2).
ROOMS = {
    "Bedroom": (-4.0, -0.78, -3.0, 3.0),
    "Hall": (-0.78, 0.78, -3.0, -1.16),
    "Kitchen": (0.78, 4.0, -3.0, -1.16),
    "Living room": (-0.78, 4.0, -1.16, 3.0),
}

# Frame, camera position, point the camera looks at, focal length (mm).
ROUTE = (
    (1, (6.80, -8.90, 11.15), (0.00, -0.08, 0.07), 32),
    (45, (5.20, -8.75, 9.55), (0.00, -0.08, 0.16), 32),
    (91, (1.20, -6.90, 4.60), (0.05, -2.15, 0.95), 31),
    (131, (0.01, -5.15, 1.72), (0.01, -0.55, 1.34), 27),
    (158, (0.00, -3.62, 1.62), (0.03, 0.20, 1.31), 26),
    (203, (0.04, -1.72, 1.62), (0.52, 1.52, 1.31), 26),
    (243, (0.10, -0.45, 1.62), (2.54, 1.46, 1.09), 26),
    (280, (0.77, 0.03, 1.63), (2.69, 1.43, 0.99), 26),
    (312, (1.22, 0.28, 1.65), (2.78, 1.42, 0.88), 25),
)


def material(name, color, roughness=0.6, metallic=0.0):
    mat = bpy.data.materials.new("MAT-" + name)
    mat.diffuse_color = (*color, 1)
    if mat.node_tree is None:
        mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return mat


def move_to(obj, collection):
    for previous in list(obj.users_collection):
        previous.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def cube(collection, name, center, size, mat, bevel=0.015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = "GEO-" + name
    # Bake each dimension into the mesh so bevel widths are in metres.
    for vertex in obj.data.vertices:
        for axis in range(3):
            vertex.co[axis] *= size[axis]
    obj.data.materials.append(mat)
    if bevel:
        edge = obj.modifiers.new("Soft edges", "BEVEL")
        edge.width = bevel
        edge.segments = 3
        obj.modifiers.new("Face normals", "WEIGHTED_NORMAL")
    return move_to(obj, collection)


def cylinder(collection, name, center, radius, height, mat):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32, radius=radius, depth=height, location=center
    )
    obj = bpy.context.object
    obj.name = "GEO-" + name
    obj.data.materials.append(mat)
    edge = obj.modifiers.new("Soft edges", "BEVEL")
    edge.width = 0.012
    edge.segments = 2
    obj.modifiers.new("Face normals", "WEIGHTED_NORMAL")
    return move_to(obj, collection)


def foliage(collection, name, center, dimensions, rotation, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, location=center)
    obj = bpy.context.object
    obj.name = "GEO-" + name
    obj.scale = dimensions
    obj.rotation_euler = rotation
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return move_to(obj, collection)


def area(collection, name, center, target, power, color, size):
    data = bpy.data.lights.new("LGT-" + name, "AREA")
    data.energy = power
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(data.name, data)
    collection.objects.link(obj)
    obj.location = center
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def build_scene():
    # This fresh scene owns every object made below. Work in background with
    # --factory-startup so unrelated open projects are never touched.
    scene = bpy.context.scene
    scene.name = "A small apartment"
    for obj in list(scene.objects):
        if obj.type in {"MESH", "LIGHT", "CAMERA"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    scene.unit_settings.system = "METRIC"
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = END_FRAME
    scene["Floor area (square metres)"] = WIDTH * DEPTH

    architecture = bpy.data.collections.new("COL-Architecture")
    furnishing = bpy.data.collections.new("COL-Furnishings")
    lighting = bpy.data.collections.new("COL-Lights")
    camera_collection = bpy.data.collections.new("COL-Camera")
    for collection in (architecture, furnishing, lighting, camera_collection):
        scene.collection.children.link(collection)

    ivory = material("Warm plaster", (0.82, 0.75, 0.62))
    trim = material("Linen trim", (0.69, 0.59, 0.45))
    oak = material("Honey oak", (0.42, 0.23, 0.105))
    floor_oak = material("Pale maple", (0.58, 0.39, 0.22))
    sage = material("Sage textile", (0.22, 0.36, 0.26), 0.83)
    clay = material("Terracotta textile", (0.50, 0.20, 0.12), 0.86)
    cream = material("Oat textile", (0.83, 0.72, 0.55), 0.84)
    dark = material("Bronze hardware", (0.060, 0.067, 0.054), 0.38, 0.35)
    limestone = material("Limestone", (0.67, 0.60, 0.48), 0.50)
    leaf = material("Olive leaves", (0.13, 0.25, 0.084), 0.75)
    base = material("Deep moss plinth", (0.09, 0.16, 0.139))
    backdrop = material("Muted studio green", (0.14, 0.22, 0.18))

    half_width, half_depth = WIDTH / 2, DEPTH / 2
    cube(architecture, "Plinth", (0, 0, -0.13), (WIDTH + 0.24, DEPTH + 0.24, 0.25), base, 0.075)
    cube(architecture, "Studio ground", (0, 0, -0.36), (200, 200, 0.12), backdrop, 0)
    floors = {"Bedroom": floor_oak, "Hall": limestone, "Kitchen": limestone, "Living room": floor_oak}
    for name, (x0, x1, y0, y1) in ROOMS.items():
        cube(architecture, name + " floor", ((x0+x1)/2, (y0+y1)/2, -0.032),
             (x1-x0, y1-y0, 0.064), floors[name], 0)

    # Parenting to a floor-level root lets the walls rise together.
    walls = bpy.data.objects.new("Walls · cutaway height", None)
    architecture.objects.link(walls)
    walls.empty_display_size = 0.18

    def wall(name, axis, fixed, start, end, z0=0, z1=WALL_HEIGHT):
        center = ((start + end)/2, fixed, (z0 + z1)/2)
        size = (end-start, WALL_THICKNESS, z1-z0)
        if axis == "y":
            center = (center[1], center[0], center[2])
            size = (size[1], size[0], size[2])
        panel = cube(architecture, name, center, size, ivory, 0.008)
        panel.parent = walls
        if z0 == 0 and z1 > 1.8:
            trim_obj = cube(architecture, name + " baseboard",
                            (center[0], center[1], 0.055),
                            (size[0] + (0.030 if axis == "y" else 0),
                             size[1] + (0.030 if axis == "x" else 0), 0.11),
                            trim, 0.004)
            trim_obj.parent = walls
        return panel

    wall("West exterior", "y", -half_width, -half_depth, half_depth)
    wall("East exterior", "y", half_width, -half_depth, half_depth)
    wall("South left of entry", "x", -half_depth, -half_width, ENTRY_MIN)
    wall("South right of entry", "x", -half_depth, ENTRY_MAX, half_width)
    wall("Entry lintel", "x", -half_depth, ENTRY_MIN, ENTRY_MAX, 2.22)
    wall("North bedroom", "x", half_depth, -half_width, -0.78)
    wall("North living left", "x", half_depth, -0.78, 0.25)
    wall("North living right", "x", half_depth, 2.65, half_width)
    wall("Window sill wall", "x", half_depth, 0.25, 2.65, 0, 0.81)
    wall("Window header", "x", half_depth, 0.25, 2.65, 2.22)
    wall("Bedroom divider south", "y", -0.78, -half_depth, -0.15)
    wall("Bedroom divider north", "y", -0.78, 0.82, half_depth)
    wall("Bedroom lintel", "y", -0.78, -0.15, 0.82, 2.22)
    wall("Hall kitchen divider", "y", 0.78, -half_depth, -1.16)
    wall("Kitchen return", "x", -1.16, 2.20, half_width)

    for x in (0.29, 1.46, 2.61):
        item = cube(architecture, f"Window mullion {x}", (x, half_depth, 1.515),
                    (0.065, 0.115, 1.41), dark, 0.005)
        item.parent = walls
    for z in (0.84, 2.19):
        item = cube(architecture, f"Window horizontal {z}", (1.45, half_depth, z),
                    (2.40, 0.115, 0.065), dark, 0.005)
        item.parent = walls

    hinge = bpy.data.objects.new("Entry door hinge", None)
    architecture.objects.link(hinge)
    hinge.parent = walls
    hinge.location = (ENTRY_MIN + 0.04, -half_depth, 0.025)
    hinge.empty_display_size = 0.10
    entry_door = cube(architecture, "Entry door", (0.515, 0, 1.075),
                      (1.03, 0.077, 2.15), oak, 0.013)
    entry_door.parent = hinge
    door_handle = cube(architecture, "Entry door lever", (0.92, -0.055, 1.02),
                       (0.13, 0.075, 0.04), dark, 0.01)
    door_handle.parent = hinge

    for frame, height in ((1, 0.34), (79, 0.34), (119, 1), (END_FRAME, 1)):
        walls.scale = (1, 1, height)
        walls.keyframe_insert("scale", frame=frame)
    for frame, angle in ((1, 0), (119, 0), (153, 93), (END_FRAME, 93)):
        hinge.rotation_euler.z = math.radians(angle)
        hinge.keyframe_insert("rotation_euler", frame=frame)

    # Bedroom. All visible textiles are separate editable volumes.
    cube(furnishing, "Bed frame", (-2.57, 1.56, 0.27), (1.66, 2.25, 0.44), oak, 0.07)
    cube(furnishing, "Mattress", (-2.57, 1.55, 0.52), (1.56, 2.11, 0.25), cream, 0.10)
    cube(furnishing, "Quilt", (-2.57, 1.12, 0.65), (1.54, 1.25, 0.09), clay, 0.04)
    cube(furnishing, "Headboard", (-2.57, 2.66, 0.57), (1.75, 0.115, 1.12), oak, 0.06)
    for x in (-2.97, -2.17):
        cube(furnishing, "Bed pillow", (x, 2.15, 0.70), (0.70, 0.51, 0.15), cream, 0.068)
    cube(furnishing, "Bedroom cabinet", (-3.45, -2.09, 0.91), (0.79, 1.63, 1.81), oak, 0.025)
    cube(furnishing, "Bedroom bench", (-2.59, -0.11, 0.23), (1.30, 0.48, 0.43), sage, 0.06)

    # Kitchen. Its open end looks into the living area.
    cube(furnishing, "Kitchen cabinets", (2.49, -2.64, 0.435), (2.80, 0.63, 0.86), sage, 0.035)
    cube(furnishing, "Kitchen worktop", (2.48, -2.64, 0.89), (2.86, 0.67, 0.06), limestone, 0.018)
    cube(furnishing, "Induction hob", (3.39, -2.59, 0.933), (0.63, 0.43, 0.022), dark, 0.016)
    for x in (3.24, 3.53):
        cylinder(furnishing, "Hob ring", (x, -2.59, 0.946), 0.11, 0.006, base)
    cube(furnishing, "Cutting board", (1.59, -2.59, 0.93), (0.32, 0.46, 0.025), oak, 0.015)
    for x in (1.47, 2.08, 2.69, 3.30):
        cube(furnishing, "Cabinet pull", (x, -2.31, 0.76), (0.22, 0.04, 0.024), dark, 0.008)

    # Living room. The longer axis of the sofa follows the east wall.
    cube(furnishing, "Living rug", (2.29, 1.30, 0.012), (2.87, 2.58, 0.023), cream, 0.010)
    cube(furnishing, "Sofa base", (3.31, 1.20, 0.28), (0.94, 2.31, 0.42), sage, 0.10)
    cube(furnishing, "Sofa back", (3.71, 1.20, 0.61), (0.22, 2.33, 0.80), sage, 0.10)
    for y in (0.42, 1.20, 1.98):
        cube(furnishing, "Sofa seat", (3.20, y, 0.52), (0.72, 0.70, 0.15), sage, 0.065)
        back = cube(furnishing, "Sofa cushion", (3.55, y, 0.76),
                    (0.16, 0.68, 0.40), sage, 0.074)
        back.rotation_euler.y = math.radians(-14)
    for y in (0.06, 2.34):
        cube(furnishing, "Sofa arm", (3.33, y, 0.57), (0.91, 0.15, 0.42), sage, 0.062)
    pillow = cube(furnishing, "Rust sofa pillow", (3.42, 1.96, 0.78),
                  (0.15, 0.42, 0.39), clay, 0.065)
    pillow.rotation_euler.x = math.radians(14)
    cylinder(furnishing, "Coffee table base", (2.12, 1.40, 0.19), 0.23, 0.33, oak)
    cylinder(furnishing, "Coffee table", (2.12, 1.40, 0.385), 0.51, 0.075, oak)
    cube(furnishing, "Book", (2.16, 1.51, 0.45), (0.30, 0.22, 0.055), clay, 0.012)
    cylinder(furnishing, "Coffee mug", (2.06, 1.17, 0.48), 0.048, 0.11, cream)
    cube(furnishing, "Wall art frame", (3.916, 1.24, 1.65), (0.065, 1.31, 0.77), oak, 0.024)
    cube(furnishing, "Wall art field", (3.878, 1.24, 1.65), (0.025, 1.18, 0.65), cream, 0.006)
    cube(furnishing, "Wall art terracotta rectangle", (3.861, 1.05, 1.65),
         (0.016, 0.40, 0.30), clay, 0.014)
    cube(furnishing, "Wall art green rectangle", (3.862, 1.51, 1.78),
         (0.016, 0.31, 0.18), sage, 0.011)

    cylinder(furnishing, "Planter", (0.26, 2.43, 0.16), 0.23, 0.32, clay)
    cylinder(furnishing, "Planter soil", (0.26, 2.43, 0.323), 0.19, 0.012, dark)
    cylinder(furnishing, "Plant stem", (0.26, 2.43, 0.61), 0.022, 0.60, leaf)
    for i in range(7):
        angle = i * 2.4
        radius = 0.18 + (i % 3) * 0.035
        foliage(
            furnishing, f"Plant leaf {i+1}",
            (0.26 + radius * math.cos(angle), 2.43 + radius * math.sin(angle), 0.55 + i*0.066),
            (0.22, 0.086, 0.027), (0, -0.38 if i % 2 else 0.24, angle), leaf,
        )

    # Warm daylight and a broad neutral fill are shared by both views.
    area(lighting, "Overhead daylight", (-1.5, 0.1, 7.2), (0, 0, 0), 1750, (1.0, 0.86, 0.70), 6.5)
    area(lighting, "Window bounce", (1.45, 2.76, 2.2), (2.65, 0.75, 0.88), 180, (1.0, 0.89, 0.75), 2.0)
    area(lighting, "Entry fill", (0, -4.4, 4.0), (0.1, -0.1, 0.4), 430, (0.79, 0.88, 1.0), 4.2)
    world = bpy.data.worlds.new("Soft studio ambient")
    if world.node_tree is None:
        world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.48, 0.55, 0.59, 1)
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.36
    scene.world = world

    camera_data = bpy.data.cameras.new("CAM-Walkthrough")
    camera_data.clip_start = 0.04
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    camera_collection.objects.link(camera)
    scene.camera = camera
    camera.rotation_mode = "QUATERNION"
    previous = None
    for frame, position, target, lens in ROUTE:
        camera.location = position
        rotation = (Vector(target) - Vector(position)).to_track_quat("-Z", "Y")
        if previous and previous.dot(rotation) < 0:
            rotation.negate()
        camera.rotation_quaternion = rotation
        camera_data.lens = lens
        camera.keyframe_insert("location", frame=frame)
        camera.keyframe_insert("rotation_quaternion", frame=frame)
        camera_data.keyframe_insert("lens", frame=frame)
        previous = rotation.copy()
    for label, frame in (("Cutaway overview", 1), ("Walls rise", 79),
                         ("Door opens", 119), ("Threshold", 158), ("Living room", 243)):
        scene.timeline_markers.new(label, frame=frame)

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = "//frames/"
    scene.view_settings.view_transform = "AgX"
    scene.frame_set(1)

    # The saved viewport opens on the first composition.
    for screen in bpy.data.screens:
        for viewport in screen.areas:
            if viewport.type == "VIEW_3D":
                space = viewport.spaces.active
                space.region_3d.view_perspective = "CAMERA"
                space.shading.color_type = "MATERIAL"
                space.overlay.show_overlays = False
    return scene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("demo.blend"), help="Destination .blend file")
    cli = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parser.parse_args(cli)
    output = args.output.expanduser().resolve()
    if output.suffix.lower() != ".blend":
        parser.error("--output must have a .blend extension")
    if output.exists():
        parser.error(f"Output already exists: {output}")
    if not bpy.app.background or bpy.data.filepath:
        parser.error("Start Blender in the background with --factory-startup and no project file")

    build_scene()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print(f"Saved the {END_FRAME / FPS:g}-second walkthrough to {output}")


if __name__ == "__main__":
    main()
