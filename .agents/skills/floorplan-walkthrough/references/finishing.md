# 中文导览与视频合成

## 准备

- 用 Blender 导出同尺寸、连续编号的 PNG 帧。记录第一帧编号和工程帧率，换算时间时从第一张输出画面开始计为零秒。
- 准备 Python 3.9 或更新版本，以及带 `libx264` 编码器的 FFmpeg。加图卡时，FFmpeg 还需带 `drawtext` 滤镜。可分别运行 `ffmpeg -encoders`、`ffmpeg -filters` 核对。脚本支持用 `--ffmpeg` 指定其他可执行文件。
- 用本机已有、覆盖简体中文的字体文件。优先选当前机器上可用的思源黑体或苹方等字体，具体位置以实际文件为准。图卡在视频内烧录，回放时无需安装字体。
- 需要配乐或旁白时，先完成音量、音轨和淡入淡出，再用 `--audio` 传入混好的音频。这样换音乐时可重新合成而无需重渲染模型。

## 分两次渲染

下面从本次项目目录运行，`SKILL_DIR` 是技能目录的绝对路径，`blender` 换成本机实际命令或路径。先对已保存的工程出低清全程预览，再给已精修的工程出正式帧。渲染工具读取现有工程，不会另存或修改源 `.blend`。

```bash
blender -b 成片.blend --python-exit-code 1 \
  --python "$SKILL_DIR/scripts/render_frames.py" -- \
  --output 预览帧 --preset preview

blender -b 成片.blend --python-exit-code 1 \
  --python "$SKILL_DIR/scripts/render_frames.py" -- \
  --output 正式帧 --preset final
```

| 参数 | 作用 |
| --- | --- |
| `--preset preview` | 使用 Cycles 处理器，画面为工程分辨率的 25%，12 个采样并降噪，适合检查全程。 |
| `--preset final` | 使用工程中的渲染引擎与设备，100% 分辨率；若是 Cycles，则用 64 个采样并降噪。先检查样帧再决定是否提高。 |
| `--scale 50`、`--samples 32` | 分别覆盖输出比例和 Cycles 采样数；最终尺寸至少为 128 × 72。 |
| `--start-frame 120 --end-frame 180` | 只渲染工程范围内的这段帧。适合先估算耗时或补渲，帧号保留工程编号。 |
| `--engine CYCLES` 或 `--engine EEVEE` | 覆盖引擎。Eevee 会自动匹配当前 Blender 的标识，使用前核对本机图形设备能否渲染。 |
| `--device CPU` 或 `--device GPU` | 覆盖 Cycles 运算设备。GPU 需要本机已有可用设备和对应 Blender 设置。 |
| `--overwrite` | 允许替换选定范围内的编号帧。默认遇到已有帧会停止。 |

目录内的 `render-info.json` 记录帧率、实际尺寸、引擎、完成帧与状态。分段补渲时，这份记录描述本次选定范围；合成前还须核对全片编号连续。正式预设只控制渲染参数，画面中的门窗、家具、材质和灯光需要事先在工程里完成。

例如每秒 24 帧的工程从第 1 帧输出时，第 `n` 帧对应 `(n-1)/24` 秒。只合成从第 120 帧开始的片段时，用 `--start-frame 120`，导览时序以该片段第一张画面为零秒重新编排。

## 编写导览时序

UTF-8 编码的 `cues.json` 采用下列格式。

```json
[
  {"start": 0, "end": 2, "label": "户型一览", "text": "从入户门走向客厅。", "kind": "title"},
  {"start": 2, "end": 5, "label": "客厅", "text": "窗边留出一处休息区。"}
]
```

- `start`、`end` 以秒计，包含起点，不包含终点。各条按时间排好，互不重叠，最后一条不能超过帧数除以帧率。图卡一般留两秒或更久，以实际阅读速度调整。
- `label` 可省略。 `text` 写一句画面能支持的说明。标题最多十六字，正文最多三十六字，文字越短越易读。 `kind` 可用 `title`、`body` 或 `ending`，默认 `body`。
- 按空间实际入镜时间安排图卡。检查画面里的装饰品、贴图和家电标牌，用简体中文或无字素材替换不合要求的可见文字。

例如已有从 `0001.png` 起的 120 帧，按每秒 24 帧合成五秒的影片。

```bash
python3 "<技能目录>/scripts/compose_video.py" \
  --frames "frames/%04d.png" --start-frame 1 --fps 24 \
  --cues "cues.json" --font "/本机字体目录/简体中文字体.otf" \
  --output "户型漫游.mp4"
```

若 Blender 输出 `tour_0001.png`，帧模板应写成 `frames/tour_%04d.png`。省略图卡参数可以先导出纯画面。脚本生成通用的 H.264 MP4，可选音轨编码为 AAC，完成解码检查后才写入成片路径。相机和字幕仍需回看确认。

## 交付前

先看关键画面，核对窗边和暗处的亮度、图卡是否遮挡空间、字体是否缺字。按正常速度通看全片，检查门洞与转弯、阅读时间、音量及片长。将完整视频、可编辑 Blender 工程、布置或尺寸假设、房间时间点和必要素材一起交付。带外部素材的工程要重新打开核对路径。
