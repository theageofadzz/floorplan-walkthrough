"""在 Blender 后台中按预览或成片设置输出连续 PNG 帧。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import bpy


def bounded_integer(minimum, maximum):
    def parse(value):
        try:
            number = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError("请输入整数") from error
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"数值须在 {minimum} 至 {maximum} 之间")
        return number
    return parse


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="PNG 帧和渲染记录的输出目录")
    parser.add_argument("--preset", choices=("preview", "final"), default="preview")
    parser.add_argument("--scale", type=bounded_integer(1, 100), help="分辨率比例，预览默认 25，成片默认 100")
    parser.add_argument("--samples", type=bounded_integer(1, 65536), help="Cycles 采样数，预览默认 12，成片默认 64")
    parser.add_argument("--start-frame", type=bounded_integer(1, 1048574))
    parser.add_argument("--end-frame", type=bounded_integer(1, 1048574))
    parser.add_argument("--engine", choices=("CYCLES", "EEVEE"), help="可选，覆盖工程的渲染引擎；EEVEE 自动匹配本机 Blender 标识")
    parser.add_argument("--device", choices=("CPU", "GPU"), help="可选，覆盖 Cycles 的运算设备")
    parser.add_argument("--overwrite", action="store_true", help="允许重渲染选定范围内已存在的编号帧")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    scene = bpy.context.scene
    if not bpy.app.background:
        parser.error("请在 Blender 后台模式运行")
    if not bpy.data.filepath:
        parser.error("请先加载已保存的 .blend 工程")
    if scene.camera is None or scene.camera.type != "CAMERA":
        parser.error("工程须设置用于渲染的相机")
    first = args.start_frame if args.start_frame is not None else scene.frame_start
    last = args.end_frame if args.end_frame is not None else scene.frame_end
    if first > last or first < scene.frame_start or last > scene.frame_end:
        parser.error("渲染帧范围须递增，且位于工程时间轴范围内")

    scale = args.scale if args.scale is not None else (25 if args.preset == "preview" else 100)
    samples = args.samples if args.samples is not None else (12 if args.preset == "preview" else 64)
    if args.preset == "preview":
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
    if args.engine == "CYCLES":
        scene.render.engine = "CYCLES"
    elif args.engine == "EEVEE":
        for identifier in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
            try:
                scene.render.engine = identifier
                break
            except (TypeError, ValueError):
                continue
        else:
            parser.error("本机 Blender 没有可用的 Eevee 引擎")
    if args.device:
        if scene.render.engine != "CYCLES":
            parser.error("--device 只适用于 Cycles")
        scene.cycles.device = args.device
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
    elif args.samples is not None:
        parser.error("--samples 只适用于 Cycles")
    scene.render.resolution_percentage = scale
    width = max(1, scene.render.resolution_x * scale // 100)
    height = max(1, scene.render.resolution_y * scale // 100)
    if width < 128 or height < 72:
        parser.error("缩放后画面须至少为 128×72 像素，请提高 --scale")
    if scene.render.fps <= 0 or scene.render.fps_base <= 0:
        parser.error("工程帧率须大于零")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not args.overwrite:
        existing = next((output / f"{frame:04d}.png" for frame in range(first, last + 1)
                         if (output / f"{frame:04d}.png").exists()), None)
        if existing:
            parser.error(f"编号帧已存在：{existing}。使用新目录，或明确传入 --overwrite")
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.use_file_extension = True
    scene.render.use_overwrite = True
    scene.render.use_placeholder = False
    manifest = {
        "blend_file": str(Path(bpy.data.filepath).resolve()),
        "blender_version": bpy.app.version_string,
        "scene": scene.name,
        "camera": scene.camera.name,
        "preset": args.preset,
        "engine": scene.render.engine,
        "device": scene.cycles.device if scene.render.engine == "CYCLES" else None,
        "samples": scene.cycles.samples if scene.render.engine == "CYCLES" else None,
        "resolution": [width, height],
        "scale": scale,
        "fps": scene.render.fps / scene.render.fps_base,
        "fps_numerator": scene.render.fps,
        "fps_denominator": scene.render.fps_base,
        "scene_frame_range": [scene.frame_start, scene.frame_end],
        "render_frame_range": [first, last],
        "completed_frames": [],
        "status": "rendering",
        "started_at": utc_now(),
    }
    record = output / "render-info.json"

    def save_record():
        record.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save_record()
    try:
        for frame in range(first, last + 1):
            scene.frame_set(frame)
            scene.render.filepath = str(output / f"{frame:04d}.png")
            bpy.ops.render.render(write_still=True)
            manifest["completed_frames"].append(frame)
            save_record()
            print(f"已渲染第 {frame} 帧，本次共 {last - first + 1} 帧。", flush=True)
        manifest["status"] = "complete"
    except BaseException as error:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        manifest["finished_at"] = utc_now()
        save_record()
    print(f"渲染完成：{output}", flush=True)


if __name__ == "__main__":
    main()
