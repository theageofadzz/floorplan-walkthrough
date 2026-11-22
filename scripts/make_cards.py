"""把导览文字排成带透明背景的影片图卡。"""

import argparse
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
except ImportError as exc:
    raise SystemExit("请先安装 Pillow：python3 -m pip install Pillow") from exc


def read_cues(path):
    with path.open(encoding="utf-8-sig") as source:
        cues = json.load(source)
    if not isinstance(cues, list) or not cues:
        raise ValueError("导览文件应包含一个非空数组。")

    for index, cue in enumerate(cues, 1):
        if not isinstance(cue, dict):
            raise ValueError(f"第 {index} 条导览应为对象。")
        start, end = cue.get("start"), cue.get("end")
        if not all(valid_time(value) for value in (start, end)) or not 0 <= start < end:
            raise ValueError(f"第 {index} 条导览的起止时间无效，请填写以秒为单位的数字。")
        for field in ("label", "text"):
            if not isinstance(cue.get(field), str):
                raise ValueError(f"第 {index} 条导览的 {field} 应为字符串。")
            cue[field] = " ".join(cue[field].split())
        if not cue["text"]:
            raise ValueError(f"第 {index} 条导览缺少正文。")
        if cue.get("kind", "body") not in ("body", "title", "ending"):
            raise ValueError(f"第 {index} 条导览的 kind 应为 body、title 或 ending。")
    return cues


def valid_time(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def smoothstep(value):
    value = min(1, max(0, value))
    return value * value * (3 - 2 * value)


def background(size, text_right, emphasized):
    width, height = size
    scale = min(width / 1280, height / 720)
    fade_start = text_right + round(22 * scale)
    fade_width = max(1, round(215 * scale))
    fade_height = max(1, round((258 if emphasized else 220) * scale))
    horizontal = bytes(
        round(255 * (1 - smoothstep((x - fade_start) / fade_width))) for x in range(width)
    )
    vertical = bytes(
        round(204 * smoothstep((y - (height - fade_height)) / fade_height)) for y in range(height)
    )
    x_mask = Image.frombytes("L", (width, 1), horizontal).resize(size, Image.Resampling.NEAREST)
    y_mask = Image.frombytes("L", (1, height), vertical).resize(size, Image.Resampling.NEAREST)
    layer = Image.new("RGBA", size, (16, 19, 15, 0))
    layer.putalpha(ImageChops.multiply(x_mask, y_mask))
    return layer


def fit_text(base_font, text, font_size, max_width):
    font = base_font.font_variant(size=font_size)
    left, _, right, _ = font.getbbox(text, anchor="ls")
    if right - left <= max_width:
        return font, left, right - left

    minimum = max(1, round(font_size * 0.6))
    size = max(minimum, min(font_size - 1, int(font_size * max_width / (right - left))))
    for adjusted_size in range(size, minimum - 1, -1):
        font = base_font.font_variant(size=adjusted_size)
        left, _, right, _ = font.getbbox(text, anchor="ls")
        if right - left <= max_width:
            return font, left, right - left
    raise ValueError("单行文字过长，请缩短文案或拆成多张图卡。")


def render_card(cue, size, base_font):
    width, height = size
    doubled = (width * 2, height * 2)
    scale = min(width / 1280, height / 720) * 2
    style = cue.get("kind", "body")
    emphasized = style != "body"
    body_size, heading_gap = {"title": (50, 63), "ending": (41, 56), "body": (31, 45)}[style]
    left = round(55 * scale)
    bottom = doubled[1] - round((51 if emphasized else 49) * scale)
    max_width = max(1, min(round(870 * scale), round(doubled[0] * 0.82)))
    lines = [
        (cue["label"], max(1, round(18 * scale)), bottom - round(heading_gap * scale), (215, 225, 202, 255)),
        (cue["text"], max(1, round(body_size * scale)), bottom, (252, 248, 234, 255)),
    ]

    # 用双倍尺寸画字，缩回成片尺寸时保留中文细笔画。
    foreground = Image.new("RGBA", doubled)
    shadow_mask = Image.new("L", doubled)
    draw = ImageDraw.Draw(foreground)
    draw_shadow = ImageDraw.Draw(shadow_mask)
    occupied_width = 0
    for content, font_size, baseline, color in lines:
        if not content:
            continue
        font, bearing, line_width = fit_text(base_font, content, font_size, max_width)
        occupied_width = max(occupied_width, line_width)
        x = left - bearing
        draw.text((x, baseline), content, font=font, fill=color, anchor="ls")
        draw_shadow.text((x, baseline + round(scale)), content, font=font, fill=180, anchor="ls")

    shadow = Image.new("RGBA", doubled, (15, 17, 12, 0))
    shadow.putalpha(shadow_mask.filter(ImageFilter.GaussianBlur(max(1, 2.4 * scale))))
    lettering = Image.alpha_composite(shadow, foreground).resize(size, Image.Resampling.LANCZOS)
    return Image.alpha_composite(background(size, round((left + occupied_width) / 2), emphasized), lettering)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cues", required=True, type=Path, help="导览文件的路径（UTF-8 编码，时间单位为秒）")
    parser.add_argument("--output", required=True, type=Path, help="透明图卡的输出目录")
    parser.add_argument("--font", required=True, type=Path, help="覆盖简体中文字符的 OTF、TTF 或 TTC 字体文件")
    parser.add_argument("--font-index", type=int, default=0, help="字体合集中的字体序号，默认值为 0")
    parser.add_argument("--resolution", type=int, nargs=2, default=(1280, 720), metavar=("宽", "高"))
    args = parser.parse_args()
    size = tuple(args.resolution)
    if min(size) < 64:
        parser.error("宽和高都须至少为 64 像素。")
    if args.font_index < 0:
        parser.error("字体序号须为非负整数。")
    if not args.font.is_file():
        parser.error(f"字体文件不存在：{args.font}")

    try:
        try:
            font = ImageFont.truetype(str(args.font), 32, index=args.font_index)
        except OSError as exc:
            raise ValueError(f"无法载入字体：{args.font}（序号 {args.font_index}）") from exc
        cues = read_cues(args.cues)
        args.output.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".cards-", dir=args.output) as temporary:
            staging = Path(temporary)
            for index, cue in enumerate(cues, 1):
                try:
                    card = render_card(cue, size, font)
                except ValueError as exc:
                    raise ValueError(f"第 {index} 条导览无法排版：{exc}") from exc
                card.save(staging / f"card_{index:03d}.png")
            for file in staging.iterdir():
                file.replace(args.output / file.name)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"已生成 {len(cues)} 张 {size[0]}×{size[1]} 的透明图卡，编号与导览文件的记录顺序一致。")


if __name__ == "__main__":
    main()
