# 视频转 2D 游戏精灵（video-to-2d-game-sprites）

把一个**已有的视频**整理成可直接用于 2D 游戏的透明序列帧：主体选择、动作拆分、抠图、固定画布与统一锚点、逐帧时长、图集与预览页，并可导出 Cocos Creator 3.8 / Unity 6 适配包。

本仓库是一个 **Agent Skill**（`SKILL.md` + `references/` + `scripts/` + `assets/`），也可以只把 `scripts/` 当成独立命令行工具使用。

**不依赖视频生成模型或任何 API Key**：保留原片，不调用视频模型重新生成或重绘角色；接缝过渡帧是本地像素插值合成，不是新素材。

## 能做什么

- 读取真实解码帧时间戳抽帧，不假定 24 FPS
- 色键 / 本地主体分割两种抠图，可选边缘去溢色
- 按累计运动量选帧、搜索循环候选
- **自动镜头稳定**：相位相关估计低频漂移、中值平滑剔除主体运动，在抠图前对源帧做平移补偿；固定裁剪、缩放、画布与锚点保持不变
- **自动循环接缝修复**：量化首尾差异，用光流形变或交叉溶解生成过渡帧，报告修复前后数值；默认只作用于 `loop=true`
- 所有动作共享同一缩放、裁剪、画布和锚点，保持多主体相对位置稳定
- 输出透明逐帧 PNG、图集 + JSON、每帧时长与循环标记、动图、可离线调速 / 选帧 / 换背景的预览页、验证报告
- 按需产出 Unity 6（PNG + 时长清单 + 编辑器导入器）或 Cocos Creator 3.8（PNG + 清单 + TypeScript 组件）适配包

## 作为 Skill 安装

把本仓库放到你所用 Agent 的 skills 目录，保持 `SKILL.md` 位于该目录根部，例如：

```bash
git clone https://github.com/meitianchiMTC/video-to-2d-game-sprites.git ~/.claude/skills/video-to-2d-game-sprites
```

`SKILL.md` 的 frontmatter 提供 `name` / `description`，`agents/openai.yaml` 提供展示名与默认提示词。之后在对话里描述你的视频和目标引擎即可触发。

> 上面的路径只是常见示例，请按你所用 Agent 实际的 skills 目录调整。

## 环境依赖

- Python 3
- `Pillow`、`NumPy`、`opencv-python`
- `ffmpeg` / `ffprobe`（需在 PATH 中，脚本通过它们读取真实时间戳）
- 可选：`rembg` + ONNX 运行时（仅 `mask.mode = model` 的本地主体分割需要）

```bash
pip install Pillow NumPy opencv-python
```

自动镜头稳定与接缝修复复用上述 OpenCV，不引入额外依赖；`ffprobe` 仍由 `inspect` / `export` 用于读取真实时间戳。

## 作为 CLI 使用

```bash
# 1. 检查视频：真实时间戳、分辨率、带时间标签的接触表
python scripts/video_sprites.py inspect --video VIDEO --work WORK

# 2. 按配置导出通用素材包
python scripts/video_sprites.py export --config CONFIG.json

# 3. 按需导出引擎适配包
python scripts/export_engines.py --pack PACK --target unity6   --output ENGINE_OUT --name Character
python scripts/export_engines.py --pack PACK --target cocos3.8 --output ENGINE_OUT --name Character
```

配置字段、区间语义、选帧与去溢色参数见 [`references/config.md`](references/config.md)；抠图见 [`references/masking.md`](references/masking.md) 与 [`references/mask-refinement.md`](references/mask-refinement.md)；引擎差异见 [`references/engines.md`](references/engines.md)。所有命令先看 `--help`。

## 目录结构

```text
SKILL.md                   技能入口与工作流
agents/openai.yaml         展示名、简述与默认提示词
scripts/video_sprites.py   inspect / export 主 CLI
scripts/export_engines.py  Unity 6 / Cocos Creator 3.8 适配导出
references/                配置、抠图、引擎、生成前置约束等参考文档
assets/                    预览页模板、Unity C# 与 Cocos TypeScript 组件模板
THIRD_PARTY_NOTICES.md     上游改编说明与 MIT 全文
```

## 注意

- 镜头稳定与接缝修复默认自动启用（`stabilize.mode=auto` / `seam.mode=auto`），可分别关闭；报告给出补偿位移、修复前后差异与 `loopSeamVerified` 数值判定。这些**不能替代人工播放验收**：光流过渡帧可能重影或局部拉伸，切镜、大幅旋转/缩放和 AI 变形不在自动修复范围内。
- 输出目录非空时会停止，重做请使用新目录，避免混入旧动作。
- 本仓库不包含视频生成 API 提交器，不会自动生成新素材或产生额度消费。
- `references/` 中的数值均为示例，不能直接套用到其他视频。

## 第三方与许可

`scripts/video_sprites.py` 中的累计运动量弧长采样、最近姿态循环搜索与通道上限去溢色，改编自 [gary149/h3-game-sprites](https://github.com/gary149/h3-game-sprites)（Copyright (c) 2026 Victor Mustar，MIT）。完整署名、上游版本与 MIT 全文见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)，请勿删除。

本仓库其余内容采用 [MIT License](LICENSE)。
