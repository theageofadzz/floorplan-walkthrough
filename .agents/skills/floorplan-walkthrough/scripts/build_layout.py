"""Generate an editable Blender blockout from measured plan and camera data."""

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def number(value, field, minimum=None, maximum=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{field} 须为有限数值")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} 须大于等于 {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field} 须小于等于 {maximum}")
    return float(value)


def integer(value, field, minimum, maximum):
    if type(value) is not int:
        raise ValueError(f"{field} 须为整数")
    return int(number(value, field, minimum, maximum))


def vector(value, length, field, minimum=None, maximum=None):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{field} 须包含 {length} 个数值")
    return tuple(number(component, field, minimum, maximum) for component in value)


def named(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 须为非空文字")
    return value.strip()


def records(value, field, minimum=0):
    if not isinstance(value, list) or len(value) < minimum or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{field} 须为对象列表，至少包含 {minimum} 项")
    return value


def load_layout(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("户型文件须包含一个对象")
    fps = integer(raw.get("fps", 24), "fps", 1, 240)
    resolution = raw.get("resolution", [1280, 720])
    if not isinstance(resolution, list) or len(resolution) != 2:
        raise ValueError("resolution 须包含宽和高")
    resolution = tuple(integer(value, "resolution", 4, 16384) for value in resolution)

    floors = []
    for index, item in enumerate(records(raw.get("floors"), "floors", 1)):
        field = f"floors[{index}]"
        name = named(item.get("name"), f"{field}.name")
        rect = vector(item.get("rect"), 4, f"{field}.rect")
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            raise ValueError(f"{field}.rect 的最大坐标须大于最小坐标")
        color = vector(item.get("color", [0.41, 0.29, 0.19]), 3, f"{field}.color", 0, 1)
        floors.append((name, rect, color))

    walls = []
    for index, item in enumerate(records(raw.get("walls"), "walls", 1)):
        field = f"walls[{index}]"
        name = named(item.get("name"), f"{field}.name")
        start = vector(item.get("start"), 2, f"{field}.start")
        end = vector(item.get("end"), 2, f"{field}.end")
        length = math.dist(start, end)
        if length < 0.01:
            raise ValueError(f"{field} 的长度须至少为 0.01 米")
        thickness = number(item.get("thickness", 0.14), f"{field}.thickness", 0.01)
        height = number(item.get("height", 2.65), f"{field}.height", 0.01)
        openings = []
        for opening_index, spec in enumerate(records(item.get("openings", []), f"{field}.openings")):
            opening = f"{field}.openings[{opening_index}]"
            offset = number(spec.get("offset"), f"{opening}.offset", 0, length)
            width = number(spec.get("width"), f"{opening}.width", 0.01)
            bottom = number(spec.get("bottom", 0), f"{opening}.bottom", 0, height)
            top = number(spec.get("top"), f"{opening}.top", 0, height)
            if offset + width > length + 1e-6 or top <= bottom:
                raise ValueError(f"{opening} 的洞口须位于墙面范围内，且上沿高于下沿")
            openings.append((offset, min(offset + width, length), bottom, top))
        openings.sort()
        if any(after[0] < before[1] - 1e-6 for before, after in zip(openings, openings[1:])):
            raise ValueError(f"{field} 的洞口沿墙长的范围不能重叠")
        walls.append((name, start, end, length, thickness, height, openings))

    camera = []
    for index, item in enumerate(records(raw.get("camera"), "camera", 2)):
        field = f"camera[{index}]"
        frame = integer(item.get("frame"), f"{field}.frame", 1, 1048574)
        position = vector(item.get("position"), 3, f"{field}.position")
        target = vector(item.get("target"), 3, f"{field}.target")
        if math.dist(position, target) < 0.01:
            raise ValueError(f"{field} 的相机和注视点须至少相距 0.01 米")
        lens = number(item.get("lens", 28), f"{field}.lens", 8, 200)
        label = named(item["label"], f"{field}.label") if "label" in item else None
        camera.append((frame, position, target, lens, label))
    if camera[0][0] != 1 or any(after[0] <= before[0] for before, after in zip(camera, camera[1:])):
        raise ValueError("camera 须从第 1 帧开始，并按帧号严格递增")

    furniture = []
    for index, item in enumerate(records(raw.get("furniture", []), "furniture")):
        field = f"furniture[{index}]"
        name = named(item.get("name"), f"{field}.name")
        center = vector(item.get("center"), 3, f"{field}.center")
        size = vector(item.get("size"), 3, f"{field}.size", 0.01)
        color = vector(item.get("color", [0.34, 0.29, 0.24]), 3, f"{field}.color", 0, 1)
        furniture.append((name, center, size, color))
    return fps, resolution, floors, walls, camera, furniture


def collection(scene, name):
    group = bpy.data.collections.new(name)
    scene.collection.children.link(group)
    return group


def material(name, color):
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1.0)
    if result.node_tree is None:
        result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = result.diffuse_color
    shader.inputs["Roughness"].default_value = 0.78
    return result


def box(group, name, center, size, surface, angle=0.0):
    x, y, z = (dimension / 2 for dimension in size)
    vertices = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
                (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    faces = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    group.objects.link(obj)
    obj.location = center
    obj.rotation_euler.z = angle
    mesh.materials.append(surface)
    return obj


def wall_pieces(group, wall, surface):
    name, start, end, length, thickness, height, openings = wall
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    pieces = []
    cursor = 0.0
    # Fill the wall between openings, plus the area above and below each opening.
    for left, right, bottom, top in openings:
        pieces.extend(((cursor, left, 0, height), (left, right, 0, bottom), (left, right, top, height)))
        cursor = right
    pieces.append((cursor, length, 0, height))
    for index, (left, right, bottom, top) in enumerate(pieces, 1):
        if right - left < 1e-6 or top - bottom < 1e-6:
            continue
        midpoint = (left + right) / 2
        center = (start[0] + midpoint * math.cos(angle), start[1] + midpoint * math.sin(angle), (bottom + top) / 2)
        box(group, f"{name}·{index:02d}", center, (right - left, thickness, top - bottom), surface, angle)


def set_linear_interpolation(animated):
    animation = animated.animation_data
    action = animation.action
    if bpy.app.version >= (4, 4, 0):
        curves = action.layers[0].strips[0].channelbag(animation.action_slot).fcurves
    else:
        curves = action.fcurves
    for curve in curves:
        for keyframe in curve.keyframe_points:
            keyframe.interpolation = "LINEAR"


def build_scene(layout):
    fps, resolution, floors, walls, route, furniture = layout
    scene = bpy.context.scene
    scene.name = "户型漫游草稿"
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.frame_start, scene.frame_end = 1, route[-1][0]
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 12
    scene.cycles.use_denoising = True
    scene.render.fps = fps
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = "//frames/"

    floor_group = collection(scene, "地面")
    light_group = collection(scene, "草稿灯光")
    light_height = max(wall[5] for wall in walls) + 0.4
    for name, (x0, y0, x1, y1), color in floors:
        x, y = (x0 + x1) / 2, (y0 + y1) / 2
        width, depth = x1 - x0, y1 - y0
        box(floor_group, name, (x, y, -0.05), (width, depth, 0.1), material(name, color))
        light_data = bpy.data.lights.new(f"{name}·草稿灯光", "AREA")
        light_data.energy = max(45, 21 * width * depth)
        light_data.shape = "DISK"
        light_data.size = max(0.25, min(width, depth) * 0.7)
        light = bpy.data.objects.new(light_data.name, light_data)
        light_group.objects.link(light)
        light.location = (x, y, light_height)

    sun_data = bpy.data.lights.new("柔和补光", "SUN")
    sun_data.energy, sun_data.angle = 1.2, math.radians(20)
    sun = bpy.data.objects.new(sun_data.name, sun_data)
    light_group.objects.link(sun)
    sun.rotation_euler = tuple(map(math.radians, (28, -25, 0)))

    wall_group = collection(scene, "墙体与洞口")
    wall_surface = material("墙面", (0.81, 0.76, 0.68))
    for wall in walls:
        wall_pieces(wall_group, wall, wall_surface)
    if furniture:
        furniture_group = collection(scene, "家具占位")
        for name, center, size, color in furniture:
            box(furniture_group, name, center, size, material(name, color))

    camera_group = collection(scene, "漫游相机")
    camera_data = bpy.data.cameras.new("漫游相机")
    camera_data.clip_start = 0.04
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    camera_group.objects.link(camera)
    scene.camera = camera
    camera.rotation_mode = "QUATERNION"
    previous_rotation = None
    for frame, position, target, lens, label in route:
        camera.location = position
        rotation = (Vector(target) - camera.location).to_track_quat("-Z", "Y")
        if previous_rotation is not None and rotation.dot(previous_rotation) < 0:
            rotation.negate()
        camera.rotation_quaternion = rotation
        previous_rotation = rotation
        camera_data.lens = lens
        camera.keyframe_insert("location", frame=frame)
        camera.keyframe_insert("rotation_quaternion", frame=frame)
        camera_data.keyframe_insert("lens", frame=frame)
        if label is not None:
            scene.timeline_markers.new(label, frame=frame)
    set_linear_interpolation(camera)
    set_linear_interpolation(camera_data)
    scene.frame_set(1)


def main():
    parser = argparse.ArgumentParser(description="按已校准的户型数据生成可编辑的漫游草稿")
    parser.add_argument("--layout", type=Path, required=True, help="输入户型数据文件")
    parser.add_argument("--output", type=Path, required=True, help="输出的 Blender 工程路径")
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if not bpy.app.background:
        parser.error("请在 Blender 后台模式运行")
    if options.output.suffix.lower() != ".blend":
        parser.error("--output 须以 .blend 结尾")
    try:
        layout = load_layout(options.layout)
    except (OSError, ValueError, OverflowError) as error:
        parser.error(str(error))
    build_scene(layout)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    preferences = bpy.context.preferences.filepaths
    original_preview = preferences.file_preview_type
    preferences.file_preview_type = "NONE"
    try:
        bpy.ops.wm.save_as_mainfile(filepath=str(options.output.resolve()))
    finally:
        preferences.file_preview_type = original_preview


if __name__ == "__main__":
    main()
