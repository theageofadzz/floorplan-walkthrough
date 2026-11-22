#!/usr/bin/env python3
"""将连续编号的渲染帧、中文导览和可选配乐合成为 MP4。"""

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory


NUMBER_PATTERN = re.compile(r"%(?:0([1-9][0-9]?))?d")
PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def read_fps(value):
    try:
        fps = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise argparse.ArgumentTypeError("帧率应为数字或分数。") from exc
    if not 1 <= fps <= 120:
        raise argparse.ArgumentTypeError("帧率应在 1 至 120 之间。")
    return fps


def png_size(path):
    with path.open("rb") as source:
        header = source.read(24)
    if len(header) != 24 or header[:16] != PNG_HEADER:
        raise ValueError(f"文件不是有效的 PNG 帧：{path}")
    return struct.unpack(">II", header[16:])


def sequence_info(pattern, start):
    matches = list(NUMBER_PATTERN.finditer(pattern.name))
    if len(matches) != 1 or pattern.suffix.lower() != ".png":
        raise ValueError("帧路径应包含一个 %d 或 %04d 这样的编号，且以 .png 结尾。")
    field = matches[0]
    prefix, suffix = pattern.name[:field.start()], pattern.name[field.end():]
    if "%" in prefix or "%" in suffix:
        raise ValueError("帧文件名只能在编号处包含百分号。")
    padding = int(field.group(1) or 0)
    name_shape = re.compile(re.escape(prefix) + r"([0-9]+)" + re.escape(suffix))
    numbered_frames = []
    for path in pattern.parent.iterdir():
        match = name_shape.fullmatch(path.name)
        if match:
            number = int(match.group(1))
            if number >= start and match.group(1) == str(number).zfill(padding):
                numbered_frames.append((number, path))
    numbered_frames.sort()
    if not numbered_frames:
        raise ValueError(f"没有找到起始帧：{pattern}")
    width, height = png_size(numbered_frames[0][1])
    if width < 128 or height < 72:
        raise ValueError("输出画面须至少为 128×72 像素。")
    for expected, (number, path) in enumerate(numbered_frames, start):
        if number != expected:
            raise ValueError(f"帧序列缺少第 {expected} 帧。")
        if png_size(path) != (width, height):
            raise ValueError(f"帧尺寸与首帧不一致：{path}")
    return len(numbered_frames), width, height


def cue_seconds(value, index):
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        raise ValueError(f"第 {index} 条导览的时间应为以秒计的数字。")
    return Fraction(str(value))


def read_cues(path, frame_count, fps):
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list):
        raise ValueError("导览时序应为 JSON 数组。")
    duration = frame_count / fps
    previous_end = 0
    cues = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 条导览应为 JSON 对象。")
        start = cue_seconds(item.get("start"), index)
        end = cue_seconds(item.get("end"), index)
        if not previous_end <= start < end <= duration:
            raise ValueError(f"第 {index} 条导览的时间重叠、未按顺序排列或超出视频时长。")
        first, stop = math.ceil(start * fps), math.ceil(end * fps)
        if first >= stop:
            raise ValueError(f"第 {index} 条导览的时间范围内没有视频帧。")
        label, body = item.get("label", ""), item.get("text")
        if not isinstance(label, str) or not isinstance(body, str):
            raise ValueError(f"第 {index} 条导览的 label 和 text 应为字符串。")
        label, body = " ".join(label.split()), " ".join(body.split())
        if not body or len(label) > 16 or len(body) > 36:
            raise ValueError(f"第 {index} 条导览须有正文，标题最多 16 字，正文最多 36 字。")
        if not all(line.isprintable() for line in (label, body)):
            raise ValueError(f"第 {index} 条导览含有不可显示的字符。")
        kind = item.get("kind", "body")
        if kind not in ("title", "body", "ending"):
            raise ValueError(f"第 {index} 条导览的 kind 应为 title、body 或 ending。")
        cues.append((first, stop, label, body, kind))
        previous_end = end
    return cues


def video_filter(directory, font, cues, width, height):
    filters = ["pad=ceil(iw/2)*2:ceil(ih/2)*2", "setsar=1"]
    if not cues:
        return ",".join(filters)
    shutil.copyfile(font, directory / "font")
    scale = min(width / 1280, height / 720)

    def px(value):
        return max(1, round(value * scale))

    for index, (first, stop, label, body, kind) in enumerate(cues):
        # 使用从零开始的帧号，确保图卡在 start 到 end（不含）的帧上显示。
        active = f"enable='gte(n,{first})*lt(n,{stop})'"
        panel_x, panel_y = px(48), height - px(139)
        label_size = px(23)
        body_size = px({"title": 43, "body": 31, "ending": 37}[kind])
        max_text_width = width - panel_x - px(110)
        body_size = min(body_size, max(1, max_text_width // len(body)))
        panel_width = max(px(260), px(48) + max(len(label)*label_size, len(body)*body_size))
        filters.extend([
            f"drawbox=x={panel_x}:y={panel_y}:w={panel_width}:h={px(92)}"
            f":color=0x202824@0.83:t=fill:{active}",
            f"drawbox=x={panel_x}:y={panel_y}:w={px(3)}:h={px(92)}"
            f":color=0xC5D6AC:t=fill:{active}",
        ])
        for text, key, size, inset, color in (
            (label, "label", label_size, 13, "0xD4E4C5"),
            (body, "body", body_size, 40 if label else 24, "0xFFF8EA"),
        ):
            if not text:
                continue
            text_file = f"cue-{index}-{key}.txt"
            (directory / text_file).write_text(text, encoding="utf-8")
            filters.append(
                f"drawtext=fontfile=font:textfile={text_file}:expansion=none"
                f":x={panel_x+px(23)}:y={panel_y+px(inset)}:fontsize={size}"
                f":fontcolor={color}:{active}"
            )
    return ",".join(filters)


def validate_font(font):
    if not font or not font.is_file():
        raise ValueError("输出导览时须用 --font 指定本机可用的简体中文字体。")
    with font.open("rb") as source:
        # 避免将误命名的其他文件交给 FFmpeg，触发系统默认字体回退。
        header = source.read(12)
    if len(header) < 12 or header[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"ttcf", b"true"):
        raise ValueError("字体无法识别，请选择有效的 OTF、TTF 或 TTC 文件。")


def ffmpeg_run(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"FFmpeg 退出，状态码 {result.returncode}。")


def encode(command, output_options, directory):
    try:
        ffmpeg_run(command + ["-/filter:v", "video.ffgraph"] + output_options, directory)
    except ValueError as exc:
        if "Unrecognized option '/filter:v'" not in str(exc):
            raise
        # 较早的 FFmpeg 用 filter_script 读取同一张滤镜图。
        ffmpeg_run(command + ["-filter_script:v", "video.ffgraph"] + output_options, directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", required=True, type=Path, help="帧路径模板，例如 frames/%%04d.png")
    parser.add_argument("--fps", required=True, type=read_fps, help="渲染帧率，例如 24 或 30000/1001")
    parser.add_argument("--start-frame", default=1, type=int)
    parser.add_argument("--cues", type=Path, help="导览时序 JSON")
    parser.add_argument("--font", type=Path, help="本机覆盖简体中文的字体文件")
    parser.add_argument("--audio", type=Path, help="可选配乐文件，按成片时长裁切或补静音")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg 命令或可执行文件路径")
    parser.add_argument("--output", required=True, type=Path, help="MP4 保存路径")
    args = parser.parse_args()

    if args.start_frame < 0:
        parser.error("起始帧编号须为非负整数。")
    if args.output.suffix.lower() != ".mp4":
        parser.error("输出文件应以 .mp4 结尾。")
    ffmpeg = shutil.which(args.ffmpeg)
    if ffmpeg is None:
        parser.error("找不到 FFmpeg。请配置 PATH 或用 --ffmpeg 指定路径。")
    binary = str(Path(ffmpeg).resolve())

    try:
        frames = args.frames.absolute()
        output = args.output.absolute()
        count, width, height = sequence_info(frames, args.start_frame)
        cues = read_cues(args.cues, count, args.fps) if args.cues else []
        if cues:
            validate_font(args.font)
        if args.audio and not args.audio.is_file():
            raise ValueError(f"配乐文件不存在：{args.audio}")
        if args.audio and args.audio.resolve() == output.resolve():
            raise ValueError("配乐的路径须与视频输出路径不同。")
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".walkthrough-", dir=output.parent) as work:
            directory = Path(work)
            graph = video_filter(directory, args.font, cues, width, height)
            (directory / "video.ffgraph").write_text(graph, encoding="utf-8")
            frame_pattern = str(frames.parent).replace("%", "%%") + "/" + frames.name
            common = [binary, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror"]
            command = common + [
                "-framerate", str(args.fps), "-start_number", str(args.start_frame),
                "-start_number_range", "1", "-i", frame_pattern,
            ]
            if args.audio:
                command += ["-i", str(args.audio.absolute())]
            command += ["-map", "0:v:0"]
            output_options = []
            if args.audio:
                output_options += ["-map", "1:a:0", "-af", "apad", "-c:a", "aac", "-b:a", "160k", "-shortest"]
            output_options += [
                "-frames:v", str(count), "-c:v", "libx264", "-preset", "medium",
                "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "video.mp4",
            ]
            try:
                encode(command, output_options, directory)
            except ValueError as exc:
                if "No such filter: 'drawtext'" in str(exc):
                    raise ValueError("这套 FFmpeg 不含 drawtext，请改用带该滤镜的版本。") from exc
                raise
            ffmpeg_run(common + ["-i", "video.mp4", "-map", "0:v:0", "-map", "0:a?", "-f", "null", "-"], directory)
            (directory / "video.mp4").replace(output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"已生成 {count} 帧、{float(count / args.fps):.2f} 秒的视频：{output}")


if __name__ == "__main__":
    main()
