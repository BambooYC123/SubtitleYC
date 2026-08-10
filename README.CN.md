# SubtitleYC

[English README](README.md)

[中文说明](README.CN.md) | [参与贡献](CONTRIBUTING.md) | [MIT 许可证](LICENSE) | [安全政策](SECURITY.md) | [隐私声明](PRIVACY.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

SubtitleYC 是依据 MIT 许可证发布的开源软件。

SubtitleYC 是一款开源 Windows 桌面应用，用于从视频中的硬字幕提取、检查和编辑字幕。它可以通过 `yt-dlp` 下载用户有权下载的视频网址，也可以打开本地视频；提供原生、帧精确的视频预览和裁剪控制；运行 VideOCR CLI；并导出 `.srt`、`.txt` 或 `.ass` 文件。

> **早期版本提示：** 请保留备份，并在依赖生成的字幕之前仔细检查其内容。

## 下载

请从 [GitHub Releases](https://github.com/BambooYC123/SubtitleYC/releases) 下载 Windows 版本。CPU 版无需 Nvidia GPU；CUDA 版可在支持的 Nvidia 系统上提供更快的 OCR 速度。

安装程序及其捆绑的 SubtitleYC 应用文件依据 MIT 许可证分发。捆绑的第三方工具继续适用各自的许可证，相关许可证会随安装文件一同提供。

应用会以普通桌面窗口打开。其内部运行一个仅绑定到 `127.0.0.1` 的私有本地 FastAPI 后端，因此普通用户无需管理服务器或浏览器标签页。

## SubtitleYC 的工作方式

### 1. 打开视频或继续已有项目

下载视频网址、打开本地视频，或继续最近使用的项目。SubtitleYC 会将来源控制、OCR 设置、预览和活动状态集中在主工作区中。

![SubtitleYC 主工作区及最近项目](docs/screenshots/01-project-library.png)

### 2. 定义字幕区域并运行 OCR

将裁剪框拖到视频中的硬字幕区域，选择识别语言和输出格式，然后运行 VideOCR。提取期间，活动面板会显示进度，原生预览仍可用于逐帧检查。

![SubtitleYC 从选定的视频区域提取字幕](docs/screenshots/02-ocr-workflow.png)

### 3. 检查、修正并导出

打开 SubtitleYC Editor，在视频旁逐条检查字幕。你可以修改字幕文字和时间、逐帧移动、添加或删除字幕条目、设置文字样式、保存更改，并导出完成的字幕文件。

![SubtitleYC Editor 对照视频检查字幕条目](docs/screenshots/03-subtitle-editor.png)

## 快速开始

1. 下载 CPU 或 GPU Windows 安装程序。
2. 启动 `SubtitleYC.exe`。
3. 通过网址加载视频，或选择本地视频文件。
4. 如果使用网址，让 SubtitleYC 自动检查可用格式；也可以选择特定格式和下载文件夹。
5. 拖动预览进度，并在视频硬字幕区域周围绘制裁剪框。
6. 选择 OCR 语言、字幕输出格式以及时间和图像设置。
7. 运行 VideOCR。
8. 检查或编辑字幕，然后下载生成的字幕文件。

请只下载你有权下载的视频。

安装程序默认将应用文件保存在 `Program Files\SubtitleYC` 下，并自动创建桌面和开始菜单快捷方式。对于体积较大的 GPU 版本，可以在安装目录页面选择其他驱动器上的 `Program Files` 文件夹。用户项目、设置、日志和生成的文件保存在 `%LOCALAPPDATA%\SubtitleYC\workspace` 下，与应用文件分开。

## 主要功能

- 使用 `yt-dlp` 下载视频，包括自动检查格式、选择特定格式、自定义保存文件夹，以及选择性导入网站字幕。
- 针对 Bilibili 网址使用 `30080+30280` 等 1080p 格式回退方案和类似 Bilibili 浏览器的请求标头。
- 选择本地视频文件并立即加载。
- 使用 `ffmpeg` 和 `ffprobe` 提取预览帧并检测视频元数据。
- 拖动视频进度、移动到上一帧或下一帧，并绘制可重复使用的字幕裁剪区域。
- 视频加载后立即显示预览。在桌面应用中，预览面板可以使用集成的 Qt/PySide 原生 PyAV 界面和内存帧缓存，提供类似 VideOCR 的逐帧拖动体验。
- 使用高级设置运行已安装或捆绑的 VideOCR CLI / PaddleOCR。
- 将字幕导出为 SubRip `.srt`、纯文本 `.txt` 或 Advanced SubStation Alpha `.ass`。
- 将 `.srt`、`.ass` 或 `.ssa` 定时字幕导入当前视频会话。
- 预览、编辑、设置样式、添加、删除、保存和下载字幕条目。
- 按帧微调单条字幕的开始和结束时间、移动全部字幕，以及将字幕时间对齐到视频帧网格。
- 在视频预览下跳转到上一处或下一处字幕边界。
- 下载和 OCR 作业使用独立活动行，活动中的作业带有停止按钮。
- 应用内日志抽屉支持筛选、复制、保存、刷新和清除。
- 应用内存储管理器可清理下载、上传、预览、生成的字幕、VideOCR 运行文件和日志。
- 提供英文和简体中文界面；首次启动时，安装程序所选语言会传递给应用。
- 设置抽屉可配置应用语言、默认下载文件夹、主题、OCR 语言、输出格式，以及 OCR 和时间设置的默认值。

## 字幕工作流程

### 生成字幕

选择视频，绘制裁剪框，选择字幕输出格式，然后点击 `Run VideOCR`。SubtitleYC 会将裁剪区域和设置传给 VideOCR CLI，并将生成的定时字幕条目转换为所选输出格式。

支持的输出格式：

- `.srt`：带时间信息的 SubRip 字幕。
- `.txt`：根据识别出的字幕条目生成的纯文本稿。
- `.ass`：Advanced SubStation Alpha 字幕。

### 编辑字幕

使用 `SubtitleYC Editor` 打开字幕编辑器。你可以：

- 编辑字幕文字、开始时间和结束时间。
- 为所选文字或整条字幕应用粗体、斜体、下划线或文字颜色。
- 添加或删除字幕条目。
- 将视频定位到某条字幕。
- 按指定帧数微调字幕的开始或结束时间。
- 将全部字幕向前或向后移动。
- 将字幕时间对齐到视频帧网格。
- 将编辑后的条目保存回当前字幕文件。

当 PySide6 可用时，桌面预览会使用集成的原生 PyAV 界面；浏览器模式或非 Qt 模式则使用网页画布作为后备。

视频下方的预览控制也可以微调当前可见或选中的字幕。`Prev Subtitle` 会跳到当前字幕的开始位置；如果当前没有显示字幕，则跳到上一条字幕的结束位置。`Next Subtitle` 会跳到当前字幕的结束位置；如果当前没有显示字幕，则跳到下一条字幕的开始位置。

### 导入字幕

使用 `Upload Subtitles` 将已有的定时字幕文件附加到当前视频。通过网址下载时，可以打开 `Video URL subtitles` 检查网站字幕或自动字幕。SubtitleYC 会尽可能将下载的字幕转换为 `.srt`，并可将匹配的字幕轨道附加到当前会话，或单独下载。

支持导入：

- `.srt`
- `.ass`
- `.ssa`

纯 `.txt` 文件不包含时间信息，因此只能导出，不能导入。

## 可下载的应用版本

请选择包含适合你电脑的 OCR 运行环境的安装程序：

- `SubtitleYC-0.5.1-windows-cpu-setup.exe`：推荐所有 Windows 用户默认使用。
- `SubtitleYC-0.5.1-windows-gpu-cuda-12.9-setup.exe`：适用于 Nvidia GTX 16 至 RTX 50 系列。

每个捆绑安装程序只包含一个 VideOCR 运行环境。安装其他版本时会升级同一份 SubtitleYC 安装并替换原有 OCR 运行环境，避免重复占用数 GB 空间。GPU 版首次运行时会启用 GPU 加速；CPU 版则保持不可用。

发布页面也包含 GitHub 自动生成的源代码压缩包。这些压缩包面向开发者，不能替代 Windows 安装程序。

## 所需的外部应用

如果使用捆绑压缩包或安装程序，SubtitleYC 会先在应用目录中查找工具：

```text
SubtitleYC\tools\videocr-cli-*\videocr-cli.exe
SubtitleYC\tools\ffmpeg\ffmpeg.exe
SubtitleYC\tools\ffmpeg\ffprobe.exe
```

如果没有捆绑工具，SubtitleYC 会自动搜索已安装的 VideOCR CPU 和 GPU 文件夹，包括 `C:\Program Files\VideOCR` 下带版本号的 CLI 目录。

如果 VideOCR 安装在其他位置，请在启动 SubtitleYC 前设置 `VIDEOCR_CLI`：

```powershell
$env:VIDEOCR_CLI = "C:\Path\To\videocr-cli.exe"
```

SubtitleYC 还需要在捆绑的 `tools\ffmpeg` 文件夹中或系统 `PATH` 上找到 `ffmpeg` 和 `ffprobe`。

## 常用环境变量

```powershell
$env:VIDEOCR_CLI = "C:\Path\To\videocr-cli.exe"
$env:SUBTITLEYC_DATA_DIR = "D:\SubtitleYCWorkspace"
$env:SUBTITLEYC_PORT = "8000"
$env:SUBTITLEYC_MAX_JOBS = "2"
$env:SUBTITLEYC_YTDLP_FRAGMENTS = "2"
$env:SUBTITLEYC_MAX_VIDEO_UPLOAD_MB = "20480"
$env:SUBTITLEYC_MIN_FREE_DISK_MB = "1024"
$env:SUBTITLEYC_NO_BROWSER = "1"
$env:SUBTITLEYC_USE_BROWSER = "1"
```

说明：

- `SUBTITLEYC_DATA_DIR` 用于移动应用工作区目录。未设置时，打包后的 Windows 版本使用 `%LOCALAPPDATA%\SubtitleYC\workspace`；开发环境使用代码目录中的 `workspace\`。
- `SUBTITLEYC_MAX_JOBS` 会限制在 `1` 到 `2` 之间。
- `SUBTITLEYC_YTDLP_FRAGMENTS` 会限制在 `1` 到 `4` 之间。
- `SUBTITLEYC_MAX_VIDEO_UPLOAD_MB` 限制复制和通过浏览器上传的视频大小，默认值为 20 GB。
- `SUBTITLEYC_MIN_FREE_DISK_MB` 在复制和下载期间保留工作区或目标磁盘的可用空间，默认值为 1 GB。
- `SUBTITLEYC_NO_BROWSER` 和 `SUBTITLEYC_USE_BROWSER` 是启动器诊断和后备选项。

## 设置

修改设置后会自动保存，并在下次启动 SubtitleYC 时重新加载。如果希望在关闭抽屉前明确保存，仍可使用 `Save Settings` 按钮。

设置抽屉可以保存以下默认值：

- 下载文件夹。
- OCR 语言和字幕输出格式。
- 置信度、文字相似度、SSIM、跳帧数、合并间隔、最短持续时间和时间偏移。
- 对齐到帧的行为。
- 亮度阈值和最大 OCR 图像宽度。
- 服务器模型、GPU 加速、全帧 OCR、角度分类、后处理和繁体中文规范化。

首次运行时的 OCR 语言为英文 + 简体中文。SubtitleYC 提供 VideOCR 的本地 PaddleOCR 模型，覆盖常见的东亚、东南亚、南亚、西亚和中亚语言，以及主要欧洲语言。其中包括简体中文、繁体中文、日语、韩语、越南语、泰语、印度尼西亚语、马来语、菲律宾语/他加禄语、印地语、马拉地语、尼泊尔语、泰米尔语、泰卢固语、阿拉伯语、波斯语、乌尔都语、维吾尔语、土耳其语、哈萨克语和蒙古语。GPU 加速需要兼容的 GPU 和 VideOCR GPU 版本。同时安装 CPU 和 GPU 版本时，SubtitleYC 会优先选择与当前模式匹配的可执行文件。

## 键盘快捷键

主预览：

- `Space`：播放或暂停。
- `Left` / `Right`：上一帧或下一帧。
- `Shift+Left` / `Shift+Right`：上一处或下一处字幕边界。
- `Ctrl+O`：上传视频。
- `Ctrl+U`：为当前视频上传字幕。
- `Ctrl+E`：打开字幕编辑器。

字幕编辑器：

- `Space`：播放或暂停。
- `Left` / `Right`：上一帧或下一帧。
- `Shift+Left` / `Shift+Right`：上一处或下一处字幕边界。
- `Ctrl+S`：保存字幕编辑。
- `Ctrl+B` / `Ctrl+I` / `Ctrl+U`：编辑字幕条目时，为所选文字设置粗体、斜体或下划线。
- `Ctrl+Z` / `Ctrl+Y`：撤销或重做字幕编辑。
- `Ctrl+U`：上传字幕；当文字编辑框处于焦点时，此快捷键用于下划线。
- `Ctrl+R`：重新加载字幕。
- `Delete`：删除选中的字幕条目。

## 日志和存储

打包后的 Windows 版本将生成的数据保存在 `%LOCALAPPDATA%\SubtitleYC\workspace`；开发环境保存在 `workspace\`；设置 `SUBTITLEYC_DATA_DIR` 后则使用该变量指定的位置。

常用目录：

```text
workspace\downloads
workspace\uploads
workspace\previews
workspace\results
workspace\logs
workspace\videocr-runtime
workspace\settings.json
```

使用 `Logs` 查看应用、下载、OCR 和错误信息。使用 `Storage` 检查和清理由 SubtitleYC 生成且可以安全重新创建的文件。

## 构建 Windows 版本

构建不含外部工具、面向高级用户的小型压缩包：

```powershell
.\scripts\build-windows.ps1
```

要构建一个自包含版本，请提供对应的已安装或暂存 VideOCR CLI：

```powershell
.\scripts\build-installer.ps1 `
  -BundleExternalTools `
  -VideOCRVariant CPU `
  -VideOCRCliPath "C:\Program Files\VideOCR\videocr-cli-CPU-v1.5.1\videocr-cli.exe"
```

有效版本为 `CPU` 和 `GPU-CUDA-12.9`。GPU 路径必须与所选 CUDA 版本匹配，以防意外发布标签错误的安装程序。

要构建公开发布矩阵，请暂存匹配的 CPU 和 CUDA 12.9 软件包，然后运行：

```powershell
.\scripts\build-public-releases.ps1 `
  -CpuVideOCRCliPath "C:\VideOCR-Staging\videocr-cli-CPU-v1.5.1\videocr-cli.exe" `
  -GpuCuda129VideOCRCliPath "C:\VideOCR-Staging\videocr-cli-GPU-v1.5.1-CUDA-12.9\videocr-cli.exe" `
  -FFmpegPath "C:\FFmpeg-Shared\bin\ffmpeg.exe" `
  -FFprobePath "C:\FFmpeg-Shared\bin\ffprobe.exe" `
  -ArtifactsRoot "D:\SubtitleYCBuild\SubtitleYC-0.5.1"
```

该矩阵要求两个版本使用相同的 VideOCR 版本号。它只编译一次 SubtitleYC，然后为每个安装程序替换捆绑的 OCR 运行环境。使用 `-ArtifactsRoot` 可以将体积较大的 `build`、`dist` 和 `release` 目录放到空间充足的驱动器；省略时则使用仓库目录。脚本会生成 CPU 和 CUDA 12.9 安装程序、本地 SHA-256 校验文件，以及将两个安装程序关联到同一次源代码构建的清单。公开 GitHub Release 只包含两个安装程序；请将校验文件和清单保留在发布记录中。若要在不移除编解码器的情况下减小软件包，请传入 FFmpeg 完整共享构建中的匹配 `ffmpeg.exe` 和 `ffprobe.exe` 路径；相邻的必要 DLL 会自动打包。当前 VideOCR 软件包请参阅 [VideOCR 发布页面](https://github.com/timminator/VideOCR/releases/latest)。

发布构建只安装 `requirements-release.txt` 中带哈希锁定的依赖项，运行 `pip check` 和 `pip-audit`，收集第三方许可证文件，并验证输出校验值。

公开发布时，请使用可信的 Windows 代码签名证书并强制要求签名：

```powershell
$env:SUBTITLEYC_SIGNING_CERT_THUMBPRINT = "YOUR_CERTIFICATE_THUMBPRINT"
.\scripts\build-public-releases.ps1 `
  -CpuVideOCRCliPath "C:\VideOCR-Staging\videocr-cli-CPU-v1.5.1\videocr-cli.exe" `
  -GpuCuda129VideOCRCliPath "C:\VideOCR-Staging\videocr-cli-GPU-v1.5.1-CUDA-12.9\videocr-cli.exe" `
  -RequireSigning
```

构建脚本会从 Windows SDK 查找 `signtool.exe`，应用并验证带 SHA-256 时间戳的签名；使用 `-RequireSigning` 时会拒绝未签名的输出。

## 安全

SubtitleYC 的 API 只监听随机的本机回环端口。桌面启动器每次运行都会创建私有令牌；API 请求必须携带该会话令牌，并会拒绝外部 Host、Origin 和嵌入式浏览器导航请求。Qt 桥只公开明确允许的方法列表。

远程下载只接受不包含嵌入式凭据的 HTTP(S) 网址。视频复制和上传设有可配置的大小限制；下载和复制会保留可用磁盘空间；字幕上传有大小上限；失败的部分上传文件会被移除。请将下载的媒体和字幕视为不受信任的数据，并及时更新 SubtitleYC、yt-dlp、VideOCR、FFmpeg 和 Windows 安全补丁。

漏洞报告请参阅 `SECURITY.md`；本地存储、日志和网络行为请参阅 `PRIVACY.md`。

## 从源代码运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
subtitleyc
```

也可以双击：

```text
Start-SubtitleYC.bat
```

## 测试

```powershell
python -m unittest discover -s tests
python -m compileall subtitleyc tests
```

如果已安装 Node.js，可以使用 `node --check static\app.js` 检查 JavaScript 语法。

## 注意事项

- 字幕时间取决于源视频 FPS、裁剪质量和 OCR 设置。可使用时间偏移、对齐到帧、字幕边界跳转和字幕编辑器进行精细调整。
- 某些网站可能需要更新的 yt-dlp 提取器支持或仅限账户访问。SubtitleYC 无法绕过访问限制。
- 可以从活动行停止正在进行的下载和 OCR 作业。

## 参与贡献

欢迎提交 Issue 和 Pull Request。环境配置、测试、贡献流程和安全报告指南请参阅 `CONTRIBUTING.md`。

## 致谢

SubtitleYC 的实现离不开以下开源项目及其贡献者：

- [VideOCR](https://github.com/timminator/VideOCR) 提供用于提取视频硬字幕的命令行 OCR 工作流程。
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) 提供视频、格式和网站字幕下载。
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) 提供 VideOCR 使用的文字识别引擎。
- [FFmpeg](https://github.com/FFmpeg/FFmpeg) 提供媒体检测、转换和流处理。
- [PyAV](https://github.com/PyAV-Org/PyAV) 为 SubtitleYC 的原生视频预览提供直接帧解码。
- [Qt for Python / PySide6](https://code.qt.io/cgit/pyside/pyside-setup.git/) 提供桌面窗口、WebEngine 集成和原生界面组件。
- [FastAPI](https://github.com/fastapi/fastapi) 提供连接界面和 SubtitleYC Python 服务的私有本地 API。
- [PyInstaller](https://github.com/pyinstaller/pyinstaller) 和 [Inno Setup](https://github.com/jrsoftware/issrc) 提供 Windows 应用和安装程序打包。

感谢这些项目的维护者和贡献者。相关软件继续适用各自的许可证；详细声明和源代码信息请参阅 `THIRD-PARTY-NOTICES.txt` 和 `licenses` 目录。

## 许可证

SubtitleYC 是依据 MIT 许可证发布的开源软件。在遵守 `LICENSE` 中版权和许可声明的前提下，你可以使用、复制、修改、分发、再许可和销售副本。

SubtitleYC 使用依据不同许可证发布的第三方软件，包括 VideOCR（MIT）、yt-dlp（The Unlicense）、Qt/PySide6（LGPLv3），以及 Windows 发布版本捆绑的 FFmpeg 构建（目前为 GPLv3-or-later）。完整声明、许可证文本和源代码链接请参阅 `THIRD-PARTY-NOTICES.txt` 和 `licenses` 目录。

Windows 发布构建还会从实际安装的 Python 发行包中收集许可证文件并保存到 `licenses/python`，确保声明包与发布版本中打包的依赖项一致。构建也会在 `licenses/FFmpeg-build/BUILD-INFO.txt` 中记录准确的 FFmpeg 哈希、版本输出和构建配置。
