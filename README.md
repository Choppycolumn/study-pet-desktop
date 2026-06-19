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

## 互动菜单与养成

- 鼠标移入桌宠：显示“摸头、玩耍、喂食、学习、设置”快捷按钮，移开后自动隐藏。
- 单击桌宠：打开摸头、陪伴学习、学习打卡、玩耍、喂食、送礼物、对话和状态菜单。
- 右键桌宠：打开学习模式、暂停提醒、今日统计、角色切换、动作预览、设置、同步和退出菜单。
- 拖动桌宠：依次播放 `drag_start / dragging / drag_end`，不会被菜单阻断。

每个角色独立保存 `mood`、`affection`、`hunger`、`energy` 和 `discipline`，范围均为 0-100。喂食使饥饿度 -20、心情 +5、亲密度 +2；玩耍使心情 +8、精力 -5、亲密度 +3；送礼使亲密度 +5、心情 +10；摸头使亲密度 +1、心情 +2。每累计 30 分钟学习增加一单位心情、亲密度和自律值；娱乐超时降低 3 点心情和 2 点自律值。

养成状态和事件保存在 `%APPDATA%\ExamPlannerPet\pet.sqlite` 的 `pet_status` 与 `pet_interaction_events` 表。设置页“自律与互动”标签可以关闭养成、悬停菜单或互动气泡，并调整三种互动冷却和暂停提醒时长。

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
  "version": "1.0.0",
  "id": "my_pet",
  "name": "我的桌宠",
  "displayName": "我的桌宠",
  "author": "local",
  "description": "用于学习陪伴的原创角色",
  "tags": ["study", "cute"],
  "renderer": "webview_skin_rig",
  "preview": "preview.png",
  "skin": "skin.png",
  "atlas": "atlas.json",
  "rig": "rig.json",
  "animations": "animations.json",
  "defaultAnimation": "idle_normal",
  "supportedStates": ["idle_normal", "study_normal", "warning_soft", "happy"],
  "fallbackProfile": "standard",
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
  "defaultFps": 60,
  "timeUnit": "ms",
  "clips": {
    "idle_normal": {
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

成熟动作协议分为 `idle`、`study`、`discipline`、`emotion`、`interaction`、`routine`、`system`、`easter_egg`、`care` 和 `menu` 十类。完整目录定义在 `pet/action_library.py`；角色不必实现全部动作，解析器会沿多级 fallback 查找，最终回到 `idle_normal`。例如 `study_typing → study_normal → idle_normal`、`warning_strong → warning_medium → warning_soft → idle_normal`、`pet_head → shy → happy → click → idle_normal`。

| 分类 | 标准动作 |
| --- | --- |
| idle | `idle_normal`, `idle_blink`, `idle_breathe`, `idle_look_left/right`, `idle_stretch`, `idle_sit/lie/bored`, `idle_random_01..03` |
| study | `study_normal/focus/reading/typing/writing/thinking/encourage/complete`, `ask_study`, `study_together`, `check_progress`, `praise_study` |
| discipline | `warning_soft/medium/strong`, `angry_soft/strong`, `disappointed`, `stare`, `block_screen`, `force_study`, `forgive` |
| emotion | `happy`, `excited`, `proud`, `shy`, `sad`, `wronged`, `angry`, `surprised`, `confused`, `tired`, `sleepy`, `calm` |
| interaction | `click`, `double_click`, `pet_head`, `drag_start/dragging/drag_end`, `greet`, `wave`, `nod`, `shake_head`, `poke`, `hide`, `return_back` |
| routine | `wake_up`, `sleep`, `nap`, `good_morning/afternoon/evening`, `late_night_warning`, `break_time`, `back_to_work` |
| system | `syncing`, `sync_success/error`, `network_error`, `config_error`, `loading`, `update_available`, `achievement` |
| easter_egg | `dance`, `cheer`, `celebrate`, `roll`, `hide_and_peek`, `special_01..03` |
| care | `feed`, `eating`, `full`, `hungry`, `play/playing`, `gift`, `love`, `pet_head`, `shy`, `spoiled`, `lonely`, `want_attention` |
| menu | `menu_open`, `menu_hover`, `menu_select`, `settings_open` |

`PetBehaviorScheduler` 维护“主状态 + 临时动作”：随机待机、点击、拖动、同步和互动完成后自动回到当前学习、提醒或待机主状态。默认待机间隔可在设置页调整。

## 成熟角色美术清单

建议把以下内容拆成独立透明部件，并为旋转留出透明边距：

- 身体：头、脸、前发、后发、身体、左右手臂、左右手、左右腿和左右脚。
- 表情：正常眼、闭眼、生气眼、星星眼、困眼、泪眼；普通嘴、微笑嘴、生气嘴、张嘴、睡觉嘴；腮红、汗滴和眼泪。
- 道具：书、笔、本子、电脑、提醒牌、闹钟、爱心、感叹号、Zzz、星星和成就徽章。
- 姿势：指向手、握拳手、张开手、挥手、趴下、坐下、睡觉、生气和学习姿势。

先让 `idle_normal`、`idle_blink`、`study_normal`、`warning_soft`、`warning_strong`、`angry_soft`、`happy`、`sleep`、`click`、`dragging` 十个核心动作可用，再补随机待机、互动和彩蛋。默认角色已经原生提供这些核心动作，并额外提供呼吸、左看、右看、伸懒腰、喂食、玩耍、礼物、摸头、菜单、同步错误、学习完成和庆祝动作；随机调度会避免连续重复同一个待机动作。

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

把完整目录放到 `characters/<角色ID>/`；打包版放到 `StudyPet/_internal/characters/<角色ID>/`。打开设置页“角色与动作”，点击“重载角色”即可看到合法角色和非法包错误。角色页显示预览图、renderer、版本、作者、支持/缺失动作数，并可按分类选择动作；点击“预览动作”会显示请求动作实际使用的 fallback。

点击“应用角色”或保存设置后立即切换，选择会写入配置并在重启后恢复。角色缺失时自动回退 `default_pet`。也可直接设置：

```json
{ "characterId": "my_pet" }
```

猫娘、小白、小鸡毛和穹妹目前保留独立角色包入口；仓库不附带第三方版权美术。放入你有权使用的素材后，可以继续使用兼容渲染器，也可以迁移为上述 Skin Rig 格式。

## 添加动作

1. 在 `animations.json.clips` 添加动作名、时长、循环方式和轨道。
2. 把动作名加入 `character.json.supportedStates`；应用状态映射可写入 `stateMap`。
3. 缺少动作时可在 `stateFallbacks` 指定角色级回退，公共规则位于 `pet/action_library.py`。
4. 运行校验器，确保轨道目标都存在于 `rig.json`，关键帧时间有效。
5. 在设置页预览动作，确认一次性动作结束后回到主状态。

## 角色包与动画验收

```powershell
python tools/generate_default_skin.py --check
python tools/validate_character_package.py
$env:QT_QPA_PLATFORM = "offscreen"
$env:QTWEBENGINE_CHROMIUM_FLAGS = "--disable-gpu"
python tools/webview_smoke_test.py
```

校验器检查 PNG 尺寸、atlas 边界、rig 父子与部件引用、动画轨道目标和表情/手臂关键帧。WebView 测试真实加载 Qt WebEngine，并依次切换默认角色的十个核心成熟动作。

## 浏览器域名识别

MVP 从活动窗口标题提取域名。Chrome/Edge 的精确方案是后续 MV3 扩展读取活动标签 URL，再向只监听 `127.0.0.1` 的桌宠本地接口发送 `{ url, title, browser }`。这不需要管理员权限，也不建议开启 remote debugging 端口。

## 后续扩展

渲染器接口与监控、分类、存储、提醒、同步解耦。未来可新增 `Live2DRenderer`、`SpineRenderer`、`LottieRenderer`、`WebGLRenderer` 和可视化 `CharacterEditor`；实现 `BaseRenderer` 后调用 `register_renderer()` 注册即可，不需要修改桌宠业务窗口。Live2D/Spine 适合高质量专业模型，但制作和授权链路更重，因此不作为第一阶段导入角色的门槛。
