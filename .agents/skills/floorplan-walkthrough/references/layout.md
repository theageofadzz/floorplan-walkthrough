# 用户型数据搭建漫游草稿

先根据平面图画出墙的中心线、洞口和可通行区域，再将实际尺寸换算成米。设一个易复核的图上角点为原点，约定向右为 X 正向、向上为 Y 正向，地面完成面为 Z = 0。如果从图片像素取点，先把向下递增的像素纵坐标换成向上递增的 Y。用另一方向的图上尺寸复核比例，有视角倾斜的照片先做透视校正。把读到的尺寸和估算值分别记在中文制作说明里。

## 输入字段

输入为 UTF-8 编码的 JSON。下面的尺寸为独立虚构示例，用于展示字段。

```json
{
  "fps": 24,
  "resolution": [1280, 720],
  "floors": [
    {"name": "起居室", "rect": [0, 0, 4, 3]},
    {"name": "卧室", "rect": [4, 0, 7, 3], "color": [0.35, 0.22, 0.15]}
  ],
  "walls": [
    {"name": "南侧外墙", "start": [0, 0], "end": [7, 0], "thickness": 0.18,
      "openings": [{"offset": 1, "width": 1, "bottom": 0, "top": 2.15}]},
    {"name": "东侧外墙", "start": [7, 0], "end": [7, 3], "thickness": 0.18,
      "openings": [{"offset": 0.8, "width": 1.4, "bottom": 0.85, "top": 2.10}]},
    {"name": "北侧外墙", "start": [7, 3], "end": [0, 3], "thickness": 0.18},
    {"name": "西侧外墙", "start": [0, 3], "end": [0, 0], "thickness": 0.18},
    {"name": "卧室隔墙", "start": [4, 0], "end": [4, 3],
      "openings": [{"offset": 1.05, "width": 0.9, "bottom": 0, "top": 2.1}]}
  ],
  "furniture": [
    {"name": "沙发占位", "center": [1.5, 2.55, 0.4], "size": [2.2, 0.65, 0.8], "color": [0.25, 0.31, 0.24]}
  ],
  "camera": [
    {"frame": 1, "position": [6.0, -7.0, 8.0], "target": [3.1, 1.4, 0.0], "lens": 32, "label": "户型俯瞰"},
    {"frame": 73, "position": [1.5, -2.3, 1.6], "target": [1.5, 1.7, 1.4], "label": "入户"},
    {"frame": 121, "position": [1.5, 1.5, 1.55], "target": [4.0, 1.5, 1.4], "label": "起居室"},
    {"frame": 192, "position": [5.2, 1.5, 1.55], "target": [6.8, 1.5, 1.4], "label": "卧室"}
  ]
}
```

| 字段 | 写法 |
| --- | --- |
| `floors` | 至少一个矩形。`rect` 顺序为 `[x最小, y最小, x最大, y最大]`。不规则地面可用若干贴边且不重叠的矩形拼合，再在工程中细化。`color` 可省略。 |
| `walls` | 至少一根墙，沿 `start` 到 `end` 两点确定的中心线生成。每根墙可设置 `thickness` 和 `height`，默认 0.14 米和 2.65 米。墙是独立网格，先检查端点交接，必要时修齐转角。 |
| `openings` | `offset` 是从墙起点沿中心线量到洞口第一边的距离，`width` 是洞宽，`bottom` 和 `top` 是离地的上下沿高度。门洞 `bottom` 可省略，默认为 0。洞口须在墙面范围内，沿同一中心线不能重叠。 |
| `camera` | 至少两个关键帧，从第 1 帧开始递增，最后一个决定时长。`position` 和 `target` 都是 `[x, y, z]`，`lens` 默认 28 毫米，`label` 是可选的时间轴标记。镜头在关键帧之间直线行走，转弯前后各设路径点，过门时让相机穿过真实洞口。 |
| `furniture` | 可选。`center` 是体块的三维中心，`size` 是对应方向的长宽高。`color` 可省略，颜色用 0 到 1 的线性 RGB 三个数。 |
| `fps`、`resolution` | 可选，默认每秒 24 帧和 `[1280, 720]`。输出视频时优先选偶数宽高。 |

## 生成和复查

把 `SKILL_DIR` 改成技能目录的绝对路径。将 `blender` 替换为本机可执行文件的路径。macOS 的默认路径是 `/Applications/Blender.app/Contents/MacOS/Blender`。

```sh
blender -b --factory-startup --python-exit-code 1 \
  --python "$SKILL_DIR/scripts/build_layout.py" -- \
  --layout layout.json --output build/漫游草稿.blend

blender -b build/漫游草稿.blend -o //试渲染/ -F PNG -f 1,73,121,192
```

草稿含分组的地面、墙片、家具体块、基础草稿灯光和可编辑的相机关键帧。门窗先留洞，门扇、窗框、玻璃、顶面、家具细节、真实材质和正式灯光按实际需求补齐。完整影片需要细化模型和镜头，调整进入门洞、转弯、停留和回望的节奏。相机经过窄处前，核对眼高、门宽和家具之间的余量，再用低清预览逐段检查。时间轴标记可作为导览起点，图卡时间要按成片入画时间确定。

草稿默认用处理器渲染 PNG 帧序列，便于在无可用图形处理器的后台环境试跑。试渲染示例中的帧号要按实际时间轴替换。生成全程预览时，可先在 Blender 里降低输出比例，再用 `-a` 渲染动画。
