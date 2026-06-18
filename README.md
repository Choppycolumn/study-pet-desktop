# Windows 桌宠自律助手

这是一个 Windows 常驻桌宠。它采样活动窗口、按规则判断学习/娱乐、写入本地 SQLite，在娱乐超时后显示气泡和可退出的强提醒，并把日报同步到网站。

第一阶段动画核心是 **WebView + 高分辨率 Skin Atlas + JSON Rig + JSON Animation Clips**。Canvas 在运行时裁切、拼装和插值播放角色，不依赖逐帧 PNG，也不要求用户先学习 Live2D 或 Spine。

本项目是从网站仓库中拆出的独立桌宠程序，源代码和 Windows 发布包位于 [study-pet-desktop](https://github.com/Choppycolumn/study-pet-desktop)。

## 下载使用

1. 从 [Releases](https://github.com/Choppycolumn/study-pet-desktop/releases) 下载 `StudyPet-windows-x64-*.zip`。
2. 解压整个目录，双击 `StudyPet.exe`。
3. 首次运行会在 `%APPDATA%\ExamPlannerPet\config.json` 创建配置，在同目录保存 `pet.sqlite`。

程序不要求管理员权限。请保留完整解压目录；Qt WebEngine 运行所需的文件与 EXE 放在一起。

## 从源码启动

```powershell
python -m pip install -r requirements.txt
python app.py
```

`config.json` 的 `timezone` 固定为 `Asia/Shanghai`。`apiToken` 必须与网站端 `STUDY_PET_API_TOKEN` 一致。也可以设置 `EXAM_PLANNER_PET_HOME` 或 `EXAM_PLANNER_PET_CONFIG` 覆盖默认数据和配置路径。

## 构建与快捷方式

在 Windows 上运行：

```powershell
.\build.cmd
.\install-shortcut.cmd
```

构建结果位于 `dist\StudyPet\StudyPet.exe`，快捷方式会创建在当前用户桌面。也可以运行 `scripts\install-shortcut.ps1 -StartWithWindows` 增加当前用户的开机启动项。发布包使用 onedir 模式，优先保证 PySide6 与 Qt WebEngine 的资源加载稳定性。

## 功能与安全边界

- 透明置顶、可拖动桌宠和托盘菜单
- 托盘退出、紧急暂停、设置、角色切换和立即同步
- 活动窗口、进程、空闲时间、软件和网站时长统计
- 规则优先的 `study/entertainment/tool/social/unknown` 分类
- 气泡、置顶弹窗、倒计时和“开始学习”确认
- 本地 SQLite 与失败重试队列
- 后台线程同步，不阻塞 WebView 动画

强提醒不会锁屏、杀进程、拦截系统快捷键，也不会移除托盘退出入口。

## 动画架构

`character.json` 的 `renderer` 决定渲染后端：

| renderer | 用途 |
| --- | --- |
| `webview_skin_rig` | 默认；Canvas 实时拼装高分辨率皮肤并播放 JSON 关键帧 |
| `frame_sequence` | 兼容 PNG/GIF 序列 |
| `sprite_sheet` | 兼容 Sprite Sheet |
| `static` | 静态图与程序化兜底 |

默认角色包位于 `characters/default_pet/`：

```text
default_pet/
├─ character.json
├─ preview.png
├─ skin.png
├─ atlas.json
├─ rig.json
├─ animations.json
└─ fallback/
   ├─ idle/
   └─ warning/
```

`webview/renderer.js` 使用 `requestAnimationFrame`，图片只在角色包加载时读取一次。Python 通过 Qt WebChannel 发送状态；渲染失败时主窗口自动切到 `StaticRenderer`，监控、计时、提醒和同步继续运行。

## 角色包格式

### character.json

```json
{
  "id": "my_pet",
  "displayName": "我的桌宠",
  "renderer": "webview_skin_rig",
  "preview": "preview.png",
  "skin": "skin.png",
  "atlas": "atlas.json",
  "rig": "rig.json",
  "animations": "animations.json",
  "defaultAnimation": "idle",
  "stateMap": {
    "tool": "study",
    "strong": "angry",
    "paused": "sleep"
  }
}
```

### skin.png 与 atlas.json

`skin.png` 是透明 RGBA 部件图，推荐 2048×2048，最大建议 4096×4096。每个部件四周保留透明边距，避免旋转时被裁切。可包含头、前后发、脸、眼睛开闭、不同嘴型、躯干、上下臂、手、上下腿、脚、书本、电脑和提醒特效。

`atlas.json` 用 `parts`、`sprites` 或 `frames` 记录裁切矩形：

```json
{
  "image": "skin.png",
  "size": { "width": 2048, "height": 2048 },
  "sprites": {
    "head": { "x": 32, "y": 32, "width": 400, "height": 400 },
    "torso": { "x": 464, "y": 32, "width": 400, "height": 440 }
  }
}
```

### rig.json

`rig.json` 定义画布、父子关系、部件、位置、旋转中心、缩放、层级和默认可见性。子节点继承父节点变换。

```json
{
  "canvas": { "width": 512, "height": 768 },
  "nodes": [
    { "id": "root", "parent": null, "position": [256, 735] },
    {
      "id": "head",
      "parent": "body",
      "sprite": "head",
      "position": [0, -195],
      "pivot": [170, 170],
      "scale": [0.5, 0.5],
      "layer": 31
    }
  ]
}
```

### animations.json

`animations.json` 是关键帧，不是逐帧图片。轨道支持 `position.x/y`、`rotation`、`scale.x/y`、`opacity` 和 `visible`；数值轨道线性插值，可循环或在一次性动作结束后跳到 fallback。

```json
{
  "timeUnit": "ms",
  "clips": {
    "idle": {
      "duration": 2000,
      "loop": true,
      "tracks": [
        {
          "target": "head",
          "property": "rotation",
          "keyframes": [
            { "time": 0, "value": -1 },
            { "time": 1000, "value": 1 },
            { "time": 2000, "value": -1 }
          ]
        }
      ]
    }
  }
}
```

内置状态包括 `idle/study/entertainment/warning/angry/happy/sleep/drag/click/error`。缺少 clip 时按 `character.json.stateFallbacks` 回退，最终使用 `idle`。

## 从正面照制作 skin.png

1. 只使用你有权使用的正面照片或原创角色图，先去除背景并保留透明通道。
2. 在绘图工具中把头、前后发、脸、眼睛开闭、嘴型、四肢关节和道具拆到独立图层。
3. 补画被遮挡区域，例如头发下的脸、上臂下的躯干和关节连接处。
4. 把图层排入一张 2048 或 4096 方形透明画布；每块周围留足旋转边距。
5. 导出 `skin.png`，把每块像素矩形写入 `atlas.json`。
6. 在 `rig.json` 中指定父子节点与 pivot；先验证静态拼装，再写 `animations.json`。
7. 运行校验器和 WebView 冒烟测试，确认无越界、无断层且状态能切换。

图像生成工具可以帮助拆层和补全遮挡，但最终 atlas 坐标、pivot 与动作仍应人工检查。角色正面照本身不能直接作为完整 rig 使用。

## 导入与切换角色

把完整目录放到 `characters/<角色ID>/`，重启后即可在托盘“切换角色”或设置页选择。也可直接设置：

```json
{ "characterId": "my_pet" }
```

猫娘、小白、小鸡毛和穹妹目前保留独立角色包入口；仓库不附带第三方版权美术。放入你有权使用的素材后，可以继续使用兼容渲染器，也可以迁移为上述 Skin Rig 格式。

## 角色包与动画验收

```powershell
python tools/generate_default_skin.py --check
python tools/validate_character_package.py
$env:QT_QPA_PLATFORM = "offscreen"
$env:QTWEBENGINE_CHROMIUM_FLAGS = "--disable-gpu"
python tools/webview_smoke_test.py
```

校验器检查 PNG 尺寸、atlas 边界、rig 父子与部件引用、动画轨道目标和表情/手臂关键帧。WebView 测试真实加载 Qt WebEngine，并切换 `idle/study/warning/angry`。

## 浏览器域名识别

MVP 从活动窗口标题提取域名。Chrome/Edge 的精确方案是后续 MV3 扩展读取活动标签 URL，再向只监听 `127.0.0.1` 的桌宠本地接口发送 `{ url, title, browser }`。这不需要管理员权限，也不建议开启 remote debugging 端口。

## 后续扩展

渲染器接口与监控、分类、存储、提醒、同步解耦。未来可新增 `Live2DRenderer`、`SpineRenderer`、`LottieRenderer`、`WebGLRenderer` 和可视化 `CharacterEditor`；实现 `BaseRenderer` 后调用 `register_renderer()` 注册即可，不需要修改桌宠业务窗口。Live2D/Spine 适合高质量专业模型，但制作和授权链路更重，因此不作为第一阶段导入角色的门槛。
