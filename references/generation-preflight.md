# 为序列帧准备视频源

本参考吸收 [h3-game-sprites 的生成工作流](https://github.com/gary149/h3-game-sprites/blob/d1295576a3debe364d7d8a6023cfc7a9835e6522/skills/h3-game-sprites/SKILL.md)。用于用户另外要求生成新视频、重拍或重做源素材时；收到现有视频时直接处理，不擅自重生成。此技能没有附带 H3 API 提交器，使用当前可用生成能力并遵守用户的额度和授权。

## 先从源头减少抠图和动作问题

- 全身及脚部始终入镜，姿态与目标视角一致。给最大伸展的肢体和道具留出余量。
- 背景选与角色、道具、半透明特效不冲突的平整纯色。紫色或绿色只是候选；角色含相同颜色时更换背景或抠图方法。
- 明确背景边到边无渐变、阴影、地面线、颗粒、灰尘、纸纹、暗角及额外物体。画风可以有质感，但背景纹理会增加色键难度。
- 固定镜头，无平移、缩放、切镜和透视变化。禁止肢体接触边界。
- 引擎负责位移时，要求角色原地行走或奔跑，保留自然肢体和身体起伏。不得用后期逐帧居中来代替这一约束。
- 明确手脚尺寸、服装和道具保持一致，避免打击瞬间拳头膨胀、道具消失、人物复制。

可按本次主体改写以下简短约束，不原样套用颜色、朝向或主体数量：

```text
Full-body side view, feet always visible, with room for the entire action.
Locked camera: no pan, zoom, cut or perspective change.
The background remains one flat solid [chosen key color], edge to edge:
no gradient, cast shadow, ground line, grain, dust, paper texture or vignette.
The character performs [one action] in place on a consistent ground level.
Hands and feet retain their normal proportions; outfit and props remain consistent.
Only the specified subject(s) appear; no duplicates or extra figures.
```

多主体组合明确数量、相对位置和交互对象，不强加“仅一个人物”。白色绒毛、透明物体、烟雾或强反光另做小样，不能因为背景是纯色就保证可抠干净。

## 参考姿态与动作衔接

先做少量风格和动作小样，确认能运动且角色稳定，再生成整套动作。一个动作一段视频，便于单独重做。

生成能力支持首尾参考时，可让攻击、受击等返回站姿的动作使用同一 idle 参考作为首尾；死亡、倒地等使用实际结束姿态。固定参考有助于一致性，但不能保证中间不变形；成品首尾接缝可由 `seam` 自动修复，仍需播放验收。

行走循环要区分起步、持续步态和收步。全片首尾回 idle 不代表中间行走自动无缝；应在持续步态中寻找候选周期。预留至少两个完整步态周期，便于搜索和人工检查。不要把首尾钉回 idle 强制当成持续行走的循环点。

## 游戏时序单独设计

源视频只提供姿态。攻击的准备、命中、恢复时长以及待机节奏在清单中另配，不要求视频按最终游戏节奏演出。`selection=motion` 可把帧数集中到姿态变化较大的片段，但默认保留源时间间隔；需要改变节奏时显式设置 `duration` 或 `duration_ms`。没有验证碰撞、命中和状态机时，不称为完整战斗动作系统。
