# CLI 与配置

各命令先看 --help。基础依赖 Python、Pillow、NumPy、OpenCV、FFmpeg/FFprobe；model 模式另需 rembg/ONNX。

```text
python scripts/video_sprites.py inspect --video VIDEO --work WORK
python scripts/video_sprites.py export --config CONFIG.json
python scripts/export_engines.py --pack PACK --target unity6 --output ENGINE_OUT --name Character
python scripts/export_engines.py --pack PACK --target cocos3.8 --output ENGINE_OUT --name Character
```

inspect 产出 probe.json 与 contact.jpg；时间戳相对于第一帧。区间 [start,end)，单位秒。读取真实解码帧时间戳；缺失则停止，不假定 24 FPS。

以下数值仅示例，不能直接套用到其他视频。路径相对配置文件。

```json
{
  "source": "source.mp4", "work": "work/character", "output": "outputs/character",
  "canvas": [512, 512], "crop": [0, 0, 1024, 1024], "pivot_source": [512, 950],
  "mask": {"mode": "chroma", "key": [255, 0, 255], "threshold": 70, "softness": 30},
  "animations": [
    {"name": "walk", "start": 0.5, "end": 1.5, "count": 12, "loop": true},
    {"name": "hit", "indices": [40, 43, 47], "duration_ms": [60, 90, 140], "loop": false}
  ]
}
```

- crop 为原视频固定 [left,top,right,bottom]，默认全画面。pivot_source 必填，是参考站姿脚底或组合地面中心的原视频像素坐标，不逐帧重算。
- canvas 默认 512×512，padding 默认 8。自动等比缩放 crop；可指定 scale，放不进画布时报错。全动作共享变换。
- mask.mode 必填：chroma、model、none；none 保留背景，不能称作透明角色。model 默认 u2netp，model_dir 可指定已有缓存。regions 为分区配置，默认全图预测；详见 masking.md。inset 默认 0。
- start/end/count 默认 `selection=uniform`，均匀采样；去重后不够 count 会报错。indices 可指定时间递增、不重复的解码帧索引，不能与自动运动/循环选帧并用。
- duration_ms 是每帧时长数组；否则显式 duration（秒）平均分配。uniform 区间默认 duration=end-start；indices 默认保留源时间间隔，末帧用源帧时长。motion/loop 的默认时序见下文。
- columns 可指定图集列数，默认至多 6。当前不自动分页，超目标纹理尺寸时缩小画布或另做分页。
- loop=true 只设播放行为；使用 selection=loop 才搜索周期。搜索结果仍是候选；loop=true 的成品由 `seam` 自动检测并修复首尾接缝，数值达标不代替播放验收，见下文。

输出：manifest.json、frames/<动作>/、atlases/、previews/、preview.html、validation.json。
manifest 的 pivotX/pivotY 为**左下原点归一化坐标**；图集矩形 x/y 为左上原点。引擎复用 pivot，不再次翻转。
输出目录非空时停止；重做使用新目录，避免混入旧动作。遮罩缓存按源文件路径/大小/修改时间、mask 配置及遮罩管线版本区分，不复用其他视频或旧管线的遮罩。外部自定义清理脚本还需独立版本或缓存目录。

清单/PNG 播放时长保留浮点毫秒。WebP 以毫秒、GIF 以 10 毫秒量化，按累计边界取整避免每帧误差累积；极短帧受编码最小间隔限制，实际预览总时长记录在 previewTimingMs。游戏时序以清单为准。

## 累计运动量选帧

```json
{"name":"attack", "start":0, "end":3, "count":12,
 "selection":"motion", "loop":false, "duration":0.6}
```

对区间内所有源帧抠图后，在固定 `analysis_crop`（默认全局 crop）内缩小至最长边 64px，以预乘 alpha 的 RGB 和 alpha 计算相邻变化，按累计变化等距挑选。透明背景中隐藏的 RGB 不计入运动量。不是骨骼动作识别；遮罩闪烁和背景残留仍会干扰，先检查抠图；镜头平移可先由 `stabilize` 补偿。`analysis_crop` 使用源像素 [left,top,right,bottom]，只影响分析，不改变导出裁剪、缩放或锚点。

保证输出 count 个递增且不重复的源帧；count>1 时保留区间首末可用帧。静止片段退回按时间分布选帧，并在报告记录 staticFallback。长静止段不自动裁除，应先缩小动作区间。

未指定 duration/duration_ms 时保留相邻所选帧的实际时间差，末帧到 end。若 start 落在两帧之间，总时长从首个可用帧开始计算。示例中的 duration 则把这些姿态等分为总计 0.6 秒；不等时序使用 duration_ms。

## 持续动作的循环候选

```json
{"name":"walk", "start":0, "end":5, "count":12,
 "selection":"loop", "loop":true,
 "loop_search":{"min_duration":0.7, "max_duration":1.2,
                "window":[0.2,0.85], "min_motion":0.001,
                "velocity_weight":0.25}}
```

min_duration/max_duration 必填，为秒，不是帧数；按实际步速设置，示例不是通用步态标准。window 是分析区间首末可用时间跨度内的相对搜索范围，默认 [0.2,0.85]，用于避开起步、收步；可设 [0,1]。同时满足候选长度内源帧数不少于 count，且 count>=2。

比较候选首尾姿态差，并以 velocity_weight 加权惩罚运动方向/速度差。min_motion 为归一化分析特征的平均相邻变化下限，默认 0.001，帮助排除静止区间；对低对比度小角色需按样张调整，不是语义分类阈值。无候选时明确报错，不悄悄把整段设为无缝循环。

在 [候选起点,匹配终点) 内按源时间均匀选 count 帧，排除重复的匹配终点。默认逐帧时长来自真实时间差，末帧补到匹配终点，不补回整个视频尾部。显式 duration/duration_ms 可另定游戏时序。

manifest 和 validation 的 selection 记录源帧区间、时间、姿态差、速度差和评分，candidateOnly=true。seamRepair 记录首尾差异修复前后的数值、过渡帧数与 loopSeamVerified 数值判定；仍需实际播放验收。镜像半步、静止抖动和真实步态变化仍可能误导搜索。

motion/loop 会处理区间内所有源帧，模型分割成本高于只导出少量帧。先限定短动作区间；循环搜索最多接受 1500 个源帧，超过需缩短范围。

## 显式色键去溢色

```json
{"mode":"chroma", "key":[255,0,255], "threshold":70, "softness":30,
 "despill":{"color":"magenta", "scope":"edge", "radius":2,
            "strength":1, "cap_scale":1.18, "cap_offset":30}}
```

color 为 magenta 或 green，应对应本片色键。去溢色默认关闭。紫色限制 R/B 上限为 G×cap_scale+cap_offset；绿色限制 G 上限为 max(R,B)×cap_scale+cap_offset。上限方法来自 h3-game-sprites；没有直接套用原版的二值色键和全图改色。

scope 默认 edge：仅处理 alpha>0 且在透明像素 radius 源像素邻域内，或 0<alpha<255 的像素；radius 为 1–32。scope=all 扩展至所有可见像素，可能改变角色本色，明确需要时才使用。strength 为 [0,1] 的修正比例；cap_scale/cap_offset 为有限非负数。去溢色不改变 alpha，不能修复错误轮廓，也不保证去掉所有反射染色。

## 镜头稳定（stabilize）

顶层 `stabilize` 对象，默认 `{"mode":"auto"}`。启用时会顺序读取所有被选中的源帧，在下采样灰度图上用相位相关估计相邻帧平移，累积成轨迹后做中值平滑（剔除主体运动尖峰），再以参考帧归零。**补偿施加在抠图之前的源帧上**：先把每帧平移 `-offset`，再走原有抠图、固定 `crop`、缩放、画布与锚点。所有动作仍共享同一坐标系，不会逐帧居中或改 pivot。

```json
"stabilize": {"mode": "auto", "activate_shift": 1.0, "max_shift": 24,
              "min_response": 0.03, "smooth": 7,
              "reference": "middle", "border": "replicate"}
```

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| mode | auto | `off` 关闭；`auto` 自动检测，仅当最大累计位移达到阈值才真正补偿，静态机位不会引入重采样 |
| activate_shift | 1.0 | 触发补偿的最小累计位移，原图像素 |
| max_shift | 24 | 单帧允许的最大位移估计，超过视为失败并沿用上一帧 |
| min_response | 0.03 | 相位相关置信度下限，低于它的帧不计位移 |
| smooth | 7 | 轨迹中值滤波窗口（奇数），滤掉主体运动造成的尖峰 |
| reference | middle | 对齐基准帧：`middle` / `first` / 具体帧索引 |
| border | replicate | 平移后的补边方式：replicate / reflect / constant |

`manifest.stabilization` 记录检测到的最大位移、实际补偿量、参考帧、分析帧数与被拒绝的估计数；每个动作的 `validation` 里有 `stabilizationApplied`。遮罩缓存指纹包含稳定化配置和帧范围，改参数会自动重算，不会复用旧遮罩。

只补偿**平移**：切镜、大幅旋转/缩放、透视变化和 AI 变形不在范围内。相位相关在纹理极少的画面上可能失准；位移较大时边缘补边会拉伸，`maxCompensatedPixels` 可供判断。用 `{"mode":"off"}` 可完全跳过这段额外读帧。

## 循环接缝修复（seam）

顶层 `seam` 对象，或写在单个 `animations[]` 里覆盖全局；默认 `{"mode":"auto"}`。仅对 `loop=true` 的动作生效。先用预乘 alpha 的缩放特征量化首帧与末帧差异 `before`，超过 `activate` 才生成过渡帧并插到序列末尾，使播放回到首帧时不再突跳。

```json
"seam": {"mode": "auto", "transition_frames": 2,
         "transition_ms": null, "activate": 0.01, "tolerance": 0.02}
```

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| mode | auto | `off` 关闭；`auto` 差异大时用 `morph`，否则用 `blend`；也可显式指定 `morph` / `blend` |
| transition_frames | 2 | 追加的过渡帧数量，0–8 |
| transition_ms | null | 每帧过渡时长（毫秒）；null 取该动作的中位帧时长，会相应增加循环总时长 |
| activate | 0.01 | 首尾差异低于此值视为无需修复 |
| tolerance | 0.02 | 修复后差异的数值达标线 |

`morph` 用 Farneback 光流把末帧向首帧形变，再按预乘 alpha 做交叉溶解；`blend` 只做交叉溶解。若修复后差异没有下降，**保留原始帧不做改动**并写明原因。过渡帧是合成帧：atlas JSON 里 `sourceFrame` / `sourceTimeSeconds` 为 null，标记 `synthetic=loopSeamTransition`；`files` 与 `durationMs` 同步增加，引擎导出脚本可直接消费。

`validation` 的 `seamRepair` 记录模式、before/after、过渡帧数与时长；`loopSeamVerified` 只表示**数值达标**，不等于视觉合格。光流过渡帧仍可能重影或局部拉伸，`maskVisuallyVerified` 保持 false，必须播放预览页确认。切镜造成的跳变、方向相反的半步和语义错误的步态周期不会被数值修复变成正确的循环。
