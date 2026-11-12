# 引擎导出

export_engines.py 读取本技能 manifest.json 与逐帧 PNG，产出工程目录和 ZIP。name 为字母开头的 ASCII 标识符，独立资源目录/类名避免多角色冲突。

## Unity 6 / 6000.x

复制 Assets/<name> 到工程，执行 Tools > Video Sprites > Build <name>。
在编辑器内生成各动作 .anim、Animator Controller、角色 Prefab。默认第一个动作；其他非循环动作结束可返回默认循环动作。用 Animator.Play("动作名") 切换。
Single Sprite、完整画布、固定 pivot、FullRect、关闭 Mipmap；默认 PPU=100，可改清单。引擎创建 GUID，重复运行保留动画引用。
Generated 是工具管理的目录，重建会更新生成 Prefab 和管理的状态/转换，手工修改放在副本中。
没有 Unity 时不能宣称导入/运行通过，也不把文件夹包称作已验证的 .unitypackage。

## Cocos Creator 3.8.x

复制 assets，Canvas 下 Sprite 节点挂 <name>VideoSpritePlayer 组件。资源路径随包名设置；加载 ImageAsset 创建完整纹理、SpriteFrame，再用原生 ObjectTrack 创建动画，保留非均匀时长。
关闭 Trim、固定 UITransform，清单 pivot 为左下坐标。监听 video-sprite-ready 后调用 play("动作名")。
运行时 Clip 不出现在资源面板；用户要可编辑 .anim、Prefab 或其他版本时另行实现，不能标为跨版本支持。

## 验证与性能

检查文件引用、尺寸、透明通道、时长、循环标志和 pivot；类型检查不等于场景验收。有工程/编辑器再检查播放、循环和切换。
当前每帧一张纹理，Cocos 预加载所有动作；不自动图集压缩、按需加载或碰撞判定。未压缩 RGBA 约为 帧数×宽×高×4 字节，另有运行时开销；按项目预算再优化。

接口参考：
- https://docs.unity.com/en-us/engine/6000.0/script-reference/unityeditor/animationutility
- https://docs.unity.com/en-us/engine/6000.0/script-reference/unityeditor/textureimportersettings
- https://docs.cocos.com/creator/3.8/api/en/class/AnimationClip
- https://docs.cocos.com/creator/3.8/manual/en/ui-system/components/engine/trim.html
