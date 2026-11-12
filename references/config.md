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
- loop=true 只设播放行为；使用 selection=loop 才搜索周期。搜索结果仍不自动修复/证明接缝。

输出：manifest.json、frames/<动作>/、atlases/、previews/、preview.html、validation.json。
manifest 的 pivotX/pivotY 为**左下原点归一化坐标**；图集矩形 x/y 为左上原点。引擎复用 pivot，不再次翻转。
输出目录非空时停止；重做使用新目录，避免混入旧动作。遮罩缓存按源文件路径/大小/修改时间、mask 配置及遮罩管线版本区分，不复用其他视频或旧管线的遮罩。外部自定义清理脚本还需独立版本或缓存目录。

清单/PNG 播放时长保留浮点毫秒。WebP 以毫秒、GIF 以 10 毫秒量化，按累计边界取整避免每帧误差累积；极短帧受编码最小间隔限制，实际预览总时长记录在 previewTimingMs。游戏时序以清单为准。

## 累计运动量选帧

```json
{"name":"attack", "start":0, "end":3, "count":12,
 "selection":"motion", "loop":false, "duration":0.6}
```

对区间内所有源帧抠图后，在固定 `analysis_crop`（默认全局 crop）内缩小至最长边 64px，以预乘 alpha 的 RGB 和 alpha 计算相邻变化，按累计变化等距挑选。透明背景中隐藏的 RGB 不计入运动量。不是骨骼动作识别；镜头运动、遮罩闪烁和背景残留都会干扰，先检查抠图。`analysis_crop` 使用源像素 [left,top,right,bottom]，只影响分析，不改变导出裁剪、缩放或锚点。

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

manifest 和 validation 的 selection 记录源帧区间、时间、姿态差、速度差和评分，candidateOnly=true；loopSeamVerified 仍为 false，等待实际播放验收。镜像半步、静止抖动和真实步态变化仍可能误导搜索。

motion/loop 会处理区间内所有源帧，模型分割成本高于只导出少量帧。先限定短动作区间；循环搜索最多接受 1500 个源帧，超过需缩短范围。

## 显式色键去溢色

```json
{"mode":"chroma", "key":[255,0,255], "threshold":70, "softness":30,
 "despill":{"color":"magenta", "scope":"edge", "radius":2,
            "strength":1, "cap_scale":1.18, "cap_offset":30}}
```

color 为 magenta 或 green，应对应本片色键。去溢色默认关闭。紫色限制 R/B 上限为 G×cap_scale+cap_offset；绿色限制 G 上限为 max(R,B)×cap_scale+cap_offset。上限方法来自 h3-game-sprites；没有直接套用原版的二值色键和全图改色。

scope 默认 edge：仅处理 alpha>0 且在透明像素 radius 源像素邻域内，或 0<alpha<255 的像素；radius 为 1–32。scope=all 扩展至所有可见像素，可能改变角色本色，明确需要时才使用。strength 为 [0,1] 的修正比例；cap_scale/cap_offset 为有限非负数。去溢色不改变 alpha，不能修复错误轮廓，也不保证去掉所有反射染色。
