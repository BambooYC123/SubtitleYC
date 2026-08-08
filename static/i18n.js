"use strict";

// Shared UI localization for the main workspace and SubtitleYC Editor.
window.SubtitleYCI18n = (() => {
  const STORAGE_KEY = "subtitleyc:ui-language";
  const UPDATE_KEY = "subtitleyc:ui-language-updated";
  const supported = new Set(["en", "zh-CN"]);
  let language = "en";
  let restoringEnglish = false;
  let observer = null;
  const sourceText = new WeakMap();
  const sourceAttributes = new WeakMap();

  const zh = {
    "Checking tools": "正在检查工具",
    "Primary navigation": "主导航",
    "Library": "项目库",
    "Settings": "设置",
    "Utilities": "实用工具",
    "Logs": "日志",
    "Storage": "存储管理",
    "Source": "来源",
    "Download or open a video": "下载或打开视频",
    "Video save folder": "视频保存文件夹",
    "Default URL download folder": "默认 URL 下载文件夹",
    "Browse": "浏览",
    "Format": "格式",
    "Best available (recommended)": "最佳可用格式（推荐）",
    "Check Formats": "检查格式",
    "Refresh Formats": "刷新格式",
    "Checking...": "正在检查...",
    "Checking available formats...": "正在检查可用格式...",
    "Video URL subtitles": "视频 URL 字幕",
    "Optional": "可选",
    "Import with video": "随视频导入",
    "Check Subtitles": "检查字幕",
    "Site subtitle": "网站字幕",
    "Download Subtitle": "下载字幕",
    "Download Video": "下载视频",
    "or": "或",
    "Open Video": "打开视频",
    "Only enable this if you want SubtitleYC to keep its own copy for later.": "仅在希望 SubtitleYC 保留副本以便以后使用时启用。",
    "Keep a copy in SubtitleYC": "在 SubtitleYC 中保留副本",
    "Extract subtitles from the cropped region": "从裁剪区域提取字幕",
    "Recognition": "识别",
    "Language": "语言",
    "Subtitle file": "字幕文件",
    "Subtitle text": "字幕文本",
    "Subtitle cue list": "字幕条目列表",
    "Subtitle cues": "字幕条目",
    "English": "英语",
    "Simplified Chinese": "简体中文",
    "English + Chinese Simplified": "英语 + 简体中文",
    "English + Chinese Traditional": "英语 + 繁体中文",
    "Chinese Simplified": "简体中文",
    "Chinese Traditional": "繁体中文",
    "Arabic": "阿拉伯语",
    "Filipino / Tagalog": "菲律宾语 / 他加禄语",
    "French": "法语",
    "German": "德语",
    "Hindi": "印地语",
    "Indonesian": "印度尼西亚语",
    "Italian": "意大利语",
    "Japanese": "日语",
    "Kazakh": "哈萨克语",
    "Korean": "韩语",
    "Malay": "马来语",
    "Marathi": "马拉地语",
    "Mongolian": "蒙古语",
    "Nepali": "尼泊尔语",
    "Persian": "波斯语",
    "Portuguese": "葡萄牙语",
    "Russian": "俄语",
    "Spanish": "西班牙语",
    "Tamil": "泰米尔语",
    "Telugu": "泰卢固语",
    "Thai": "泰语",
    "Turkish": "土耳其语",
    "Ukrainian": "乌克兰语",
    "Urdu": "乌尔都语",
    "Uyghur": "维吾尔语",
    "Vietnamese": "越南语",
    "SubRip (.srt)": "SubRip (.srt)",
    "Plain text (.txt)": "纯文本 (.txt)",
    "Advanced SubStation Alpha (.ass)": "Advanced SubStation Alpha (.ass)",
    "Confidence": "置信度",
    "Text similarity": "文本相似度",
    "Timing": "时间设置",
    "skip, gaps, offset, trim": "跳帧、间隔、偏移、裁剪",
    "Frames to skip": "跳过帧数",
    "Max merge gap": "最大合并间隔",
    "Min duration": "最短持续时间",
    "Timing offset (frames)": "时间偏移（帧）",
    "Snap timing to frames": "将时间对齐到帧",
    "Start": "开始",
    "End": "结束",
    "Full video": "完整视频",
    "Image": "图像",
    "brightness, scaling": "亮度、缩放",
    "Brightness threshold": "亮度阈值",
    "Off": "关闭",
    "Max OCR width": "最大 OCR 宽度",
    "Engine": "引擎",
    "model & OCR behavior": "模型与 OCR 行为",
    "Use Server Model": "使用服务器模型",
    "Use GPU Acceleration": "使用 GPU 加速",
    "Use Full Frame OCR": "使用全帧 OCR",
    "Enable Angle Classification": "启用角度分类",
    "Enable Post Processing": "启用后处理",
    "Normalize Traditional Chinese": "规范化繁体中文",
    "Run VideOCR": "运行 VideOCR",
    "No video loaded": "未加载视频",
    "Crop: none": "裁剪：无",
    "Previous Projects": "以前的项目",
    "Recent videos": "最近的视频",
    "View Library": "查看项目库",
    "Prev Frame": "上一帧",
    "Next Frame": "下一帧",
    "Play": "播放",
    "Pause": "暂停",
    "Visible subtitle timing": "当前字幕时间",
    "Open project files": "打开项目文件",
    "Subtitle project actions": "字幕项目操作",
    "Video preview": "视频预览",
    "Jump to subtitle": "跳转到字幕",
    "Previous": "上一个",
    "Next": "下一个",
    "Trim visible cue": "调整当前字幕",
    "Move the visible subtitle start earlier": "将当前字幕开始时间提前",
    "Move the visible subtitle start later": "将当前字幕开始时间延后",
    "Move the visible subtitle end earlier": "将当前字幕结束时间提前",
    "Move the visible subtitle end later": "将当前字幕结束时间延后",
    "Move start earlier": "将开始时间提前",
    "Move start later": "将开始时间延后",
    "Move end earlier": "将结束时间提前",
    "Move end later": "将结束时间延后",
    "Activity": "活动",
    "SubtitleYC Editor": "SubtitleYC 编辑器",
    "Upload Subtitles": "上传字幕",
    "Download .srt": "下载 .srt",
    "Close": "关闭",
    "Log filter": "日志筛选",
    "All": "全部",
    "All -": "全部 -",
    "All +": "全部 +",
    "Downloads": "下载",
    "Errors": "错误",
    "Refresh": "刷新",
    "Copy": "复制",
    "Save": "保存",
    "Clear": "清除",
    "Open videos and timed subtitles already copied into SubtitleYC": "打开已复制到 SubtitleYC 的视频和定时字幕",
    "Previous Videos": "以前的视频",
    "Uploaded videos and URL downloads": "上传的视频和 URL 下载",
    "Previous Subtitles": "以前的字幕",
    "Attach to the current video": "附加到当前视频",
    "Delete Selected": "删除所选内容",
    "Delete files?": "删除文件？",
    "Total": "总计",
    "Space you can clear": "可清理空间",
    "Deleting files cannot be undone": "删除文件后无法恢复",
    "Check the selected rows before clearing videos, subtitles, previews, or logs.": "清理视频、字幕、预览或日志前，请检查所选项目。",
    "App workspace": "应用工作区",
    "Subtitles": "字幕",
    "Subtitle timing tools": "字幕时间工具",
    "Frames": "帧数",
    "Move all cues earlier": "将所有字幕提前",
    "Move all cues later": "将所有字幕延后",
    "Snap all cue times to the video frame grid": "将所有字幕时间对齐到视频帧网格",
    "Snap": "对齐",
    "Upload File": "上传文件",
    "Add Cue": "添加字幕",
    "Undo": "撤销",
    "Redo": "重做",
    "Defaults used the next time you load a video": "下次加载视频时使用的默认设置",
    "Appearance": "外观",
    "App language": "应用语言",
    "Choose the language used throughout SubtitleYC.": "选择 SubtitleYC 全部界面使用的语言。",
    "Theme": "主题",
    "Dark": "深色",
    "Light": "浅色",
    "Default video folder": "默认视频文件夹",
    "Default language": "默认识别语言",
    "Default subtitle file": "默认字幕文件",
    "Recognition thresholds": "识别阈值",
    "Timing and Image": "时间与图像",
    "skip, gaps, offset, brightness": "跳帧、间隔、偏移、亮度",
    "Tools": "工具",
    "Checking": "正在检查",
    "Not installed": "未安装",
    "Reset": "重置",
    "Save Settings": "保存设置",
    "Confirm action": "确认操作",
    "This action cannot be undone.": "此操作无法撤销。",
    "Cancel": "取消",
    "Confirm": "确认",
    "Ready": "就绪",
    "Loading": "正在加载",
    "No active jobs": "没有活动任务",
    "Stop": "停止",
    "Working": "处理中",
    "Job": "任务",
    "Open": "打开",
    "Attach": "附加",
    "Delete": "删除",
    "No storage data": "没有存储数据",
    "No recent videos": "没有最近的视频",
    "No previous videos yet": "还没有以前的视频",
    "No previous timed subtitles yet": "还没有以前的定时字幕",
    "Load a video first": "请先加载视频",
    "Original file": "原始文件",
    "Stored video copy": "已保存的视频副本",
    "URL download": "URL 下载",
    "Saved subtitle output": "已保存的字幕输出",
    "Project file": "项目文件",
    "Recent video": "最近的视频",
    "URL video downloads": "URL 视频下载",
    "Uploaded video copies": "已上传的视频副本",
    "Preview frame cache": "预览帧缓存",
    "Saved subtitle outputs": "已保存的字幕输出",
    "VideOCR runtime files": "VideOCR 运行文件",
    "No subtitle cues": "没有字幕条目",
    "Load a subtitle file, add a cue, or run VideOCR.": "请加载字幕文件、添加字幕条目或运行 VideOCR。",
    "Seek": "定位",
    "Unsaved changes": "有未保存的更改",
    "Settings saved": "设置已保存",
    "Settings reset": "设置已重置",
    "Opened SubtitleYC Editor": "已打开 SubtitleYC 编辑器",
    "Could not open SubtitleYC Editor": "无法打开 SubtitleYC 编辑器",
    "Loaded video from SubtitleYC Editor": "已从 SubtitleYC 编辑器加载视频",
    "Tool check unavailable": "无法检查工具",
    "Missing": "缺少",
    "ffmpeg, ffprobe, and VideOCR GPU acceleration ready.": "ffmpeg、ffprobe 和 VideOCR GPU 加速已就绪。",
    "ffmpeg, ffprobe, and VideOCR CPU ready. GPU build not installed.": "ffmpeg、ffprobe 和 VideOCR CPU 已就绪。未安装 GPU 版本。",
    "Close SubtitleYC Editor": "关闭 SubtitleYC 编辑器",
    "Ready to review subtitles": "可以开始检查字幕",
    "Open a video and upload subtitles to begin": "打开视频并上传字幕以开始",
    "Open a copied video, or attach timed subtitles to the current video": "打开已复制的视频，或将定时字幕附加到当前视频",
    "Reload": "重新加载",
    "Keep copy": "保留副本",
    "Add": "添加",
    "No subtitle cues loaded": "未加载字幕条目",
    "Empty subtitle": "空字幕",
    "Save Changes": "保存更改",
    "Start -": "开始 -",
    "Start +": "开始 +",
    "End -": "结束 -",
    "End +": "结束 +",
    "Prev Subtitle": "上一条字幕",
    "Next Subtitle": "下一条字幕",
    "Logs copied": "日志已复制",
    "Logs saved": "日志已保存",
    "Logs cleared": "日志已清除",
    "Tool versions refreshed": "工具版本已刷新",
    "No storage location is available": "没有可用的存储位置",
    "Open location is available in the desktop app": "仅桌面应用可以打开文件位置",
    "Could not open storage location": "无法打开存储位置",
    "Choose storage rows to clear": "请选择要清理的存储项目",
    "Undid subtitle edit": "已撤销字幕编辑",
    "Redid subtitle edit": "已重做字幕编辑",
    "No subtitle file is available": "没有可用的字幕文件",
    "Load a video before opening subtitles": "请先加载视频再打开字幕",
    "No subtitle cues to jump through": "没有可跳转的字幕条目",
    "Choose a subtitle cue to nudge": "请选择要调整的字幕条目",
    "Move the playhead over a cue or focus a cue row before nudging it": "调整前，请将播放位置移到字幕条目上或选中字幕行",
    "No subtitle cues to nudge": "没有可调整的字幕条目",
    "No subtitle cues to snap": "没有可对齐的字幕条目",
    "Snapped subtitle timings to the video frame grid": "已将字幕时间对齐到视频帧网格",
    "Native preview failed": "原生预览失败",
    "Could not load preview frame": "无法加载预览帧",
    "Preview cache failed": "预览缓存失败",
    "Video loaded": "视频已加载",
    "Loaded imported video copy": "已加载导入的视频副本",
    "VideOCR CLI is missing. Install VideOCR or set VIDEOCR_CLI to videocr-cli.exe.": "缺少 VideOCR CLI。请安装 VideOCR，或将 VIDEOCR_CLI 设置为 videocr-cli.exe。",
    "Checking formats for this URL": "正在检查此 URL 的格式",
    "Checking available video formats": "正在检查可用视频格式",
    "Ready to download with best available format": "可以使用最佳可用格式下载",
    "Checking available site subtitles": "正在检查可用的网站字幕",
    "No site subtitles found for this URL": "此 URL 没有可用的网站字幕",
    "Choose where to save the subtitle file": "选择字幕文件的保存位置",
    "Could not choose subtitle save location": "无法选择字幕保存位置",
    "Paste a URL before downloading subtitles": "请先粘贴 URL 再下载字幕",
    "Check subtitles and choose a track first": "请先检查字幕并选择字幕轨道",
    "Subtitle download cancelled": "已取消字幕下载",
    "Could not choose folder": "无法选择文件夹",
    "Load": "加载",
    "Copying video into SubtitleYC": "正在将视频复制到 SubtitleYC",
    "Opening video": "正在打开视频",
    "Loaded stored video copy": "已加载保存的视频副本",
    "Loaded video without copying": "已加载视频且未复制",
    "Could not choose video": "无法选择视频",
    "Importing video copy": "正在导入视频副本",
    "Could not save subtitle file": "无法保存字幕文件",
    "Could not load preview frame": "无法加载预览帧",
    "Undid subtitle edit": "已撤销字幕编辑",
    "Redid subtitle edit": "已重做字幕编辑",
    "Save failed": "保存失败",
    "Open video failed": "打开视频失败",
    "Reload failed": "重新加载失败",
    "Cue updated": "字幕条目已更新",
    "Could not play video": "无法播放视频",
    "Upload a video or open Previous Projects": "请上传视频或打开以前的项目",
    "Load a video before loading subtitles": "请先加载视频再加载字幕",
    "Load a video before saving subtitles": "请先加载视频再保存字幕",
    "Load a video before downloading subtitles": "请先加载视频再下载字幕",
    "Save changes before downloading": "请先保存更改再下载",
    "No saved subtitle file is available": "没有可用的已保存字幕文件",
    "Subtitle save cancelled": "已取消保存字幕",
    "Load a video before uploading subtitles": "请先加载视频再上传字幕",
    "Could not open video": "无法打开视频",
    "Could not attach subtitles": "无法附加字幕",
    "Could not load previous projects": "无法加载以前的项目",
    "Refresh failed": "刷新失败",
    "Download failed": "下载失败",
    "Subtitle upload failed": "字幕上传失败",
    "Video upload failed": "视频上传失败",
    "Editor failed to load": "编辑器加载失败"
  };

  const patterns = [
    [/^Frame: (\d+) \/ (\d+) \| Time: (.+) \/ (.+)$/, "帧：$1 / $2 | 时间：$3 / $4"],
    [/^(\d+) lines$/, "$1 行"],
    [/^(\d+) files$/, "$1 个文件"],
    [/^(\d+) categories$/, "$1 个类别"],
    [/^(\d+) cues$/, "$1 条字幕"],
    [/^(\d+) cue$/, "$1 条字幕"],
    [/^(\d+) previous project files$/, "$1 个以前的项目文件"],
    [/^(\d+) previous project file$/, "$1 个以前的项目文件"],
    [/^(\d+) files \| (\d+) categories$/, "$1 个文件 | $2 个类别"],
    [/^(\d+) subtitle cues loaded$/, "已加载 $1 条字幕"],
    [/^Loaded (\d+) subtitle cues from (.+)$/, "已从 $2 加载 $1 条字幕"],
    [/^Loaded (\d+) cues from (.+)$/, "已从 $2 加载 $1 条字幕"],
    [/^Saved (\d+) subtitle cues$/, "已保存 $1 条字幕"],
    [/^Saved (\d+) cues$/, "已保存 $1 条字幕"],
    [/^Ready: (\d+) cues$/, "就绪：$1 条字幕"],
    [/^(.+) ready: (\d+) cues$/, "$1 已就绪：$2 条字幕"],
    [/^Found (\d+) site subtitle tracks?$/, "找到 $1 条网站字幕轨道"],
    [/^Ready to download\. (\d+) video formats? found\.$/, "可以下载。找到 $1 个视频格式。"],
    [/^Opened (.+)$/, "已打开 $1"],
    [/^Opening (.+)$/, "正在打开 $1"],
    [/^Loaded subtitle (.+)$/, "已加载字幕 $1"],
    [/^Loaded (.+)$/, "已加载 $1"],
    [/^Downloading (.+)$/, "正在下载 $1"],
    [/^Saved SRT to (.+)$/, "SRT 已保存到 $1"],
    [/^Saved (SRT|TXT|ASS) to (.+)$/, "$1 已保存到 $2"],
    [/^(SRT|TXT|ASS) save cancelled$/, "已取消保存 $1"],
    [/^Choose where to save the (SRT|TXT|ASS) file$/, "选择 $1 文件的保存位置"],
    [/^Subtitle saved: (.+)$/, "字幕已保存：$1"],
    [/^Saved (.+)$/, "已保存 $1"],
    [/^Preview cache (.+): (\d+) frames$/, "预览缓存$1：$2 帧"],
    [/^Jumped to cue (\d+) (.+)$/, "已跳转到第 $1 条字幕的$2"],
    [/^Nudged cue (\d+) (.+) (.+) by (.+) frames?$/, "已将第 $1 条字幕的$2向$3调整 $4 帧"],
    [/^Nudged all cues (later|earlier) by (.+) frames?$/, "已将所有字幕$1 $2 帧"],
    [/^Download \.(srt|txt|ass)$/, "下载 .$1"],
    [/^Crop: x (.+), y (.+), w (.+), h (.+)$/, "裁剪：x $1，y $2，宽 $3，高 $4"],
    [/^Missing: (.+)\. Install VideOCR or set VIDEOCR_CLI\.$/, "缺少：$1。请安装 VideOCR 或设置 VIDEOCR_CLI。"],
    [/^Recommended: (.+)$/, "推荐：$1"],
    [/^Subtitle: (.+)$/, "字幕：$1"]
  ];

  function normalize(value) {
    const candidate = String(value || "").trim();
    return supported.has(candidate) ? candidate : "en";
  }

  function translatedText(value) {
    const text = String(value ?? "");
    if (language !== "zh-CN") return text;
    const leading = text.match(/^\s*/)?.[0] || "";
    const trailing = text.match(/\s*$/)?.[0] || "";
    const core = text.trim();
    if (!core) return text;
    let translated = zh[core];
    if (!translated) {
      for (const [pattern, replacement] of patterns) {
        if (pattern.test(core)) {
          translated = core.replace(pattern, replacement);
          break;
        }
      }
    }
    return translated ? `${leading}${translated}${trailing}` : text;
  }

  function applyTextNode(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE) return;
    if (["SCRIPT", "STYLE"].includes(node.parentElement?.tagName)) return;
    if (node.parentElement?.closest("[data-i18n-skip], .subtitle-preview-overlay, .subtitle-overlay, .subtitle-cue-text, .cue-text, .log-output")) return;
    if (language === "en") {
      if (restoringEnglish && sourceText.has(node) && node.nodeValue !== sourceText.get(node)) node.nodeValue = sourceText.get(node);
      else sourceText.set(node, node.nodeValue);
      return;
    }
    const current = node.nodeValue || "";
    const translated = translatedText(current);
    if (translated !== current) {
      sourceText.set(node, current);
      node.nodeValue = translated;
    } else if (sourceText.has(node)) {
      const source = sourceText.get(node);
      const next = translatedText(source);
      if (next !== current) node.nodeValue = next;
    }
  }

  const localizedAttributes = ["placeholder", "title", "aria-label"];
  function applyElementAttributes(element) {
    if (!(element instanceof Element)) return;
    let originals = sourceAttributes.get(element);
    if (!originals) {
      originals = {};
      sourceAttributes.set(element, originals);
    }
    for (const name of localizedAttributes) {
      if (!element.hasAttribute(name)) continue;
      const current = element.getAttribute(name) || "";
      if (language === "en") {
        if (restoringEnglish && Object.prototype.hasOwnProperty.call(originals, name) && current !== originals[name]) element.setAttribute(name, originals[name]);
        else originals[name] = current;
      } else {
        const translated = translatedText(current);
        if (translated !== current) {
          originals[name] = current;
          element.setAttribute(name, translated);
        } else if (Object.prototype.hasOwnProperty.call(originals, name)) {
          const next = translatedText(originals[name]);
          if (next !== current) element.setAttribute(name, next);
        }
      }
    }
  }

  function apply(root = document) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      applyTextNode(root);
      return;
    }
    if (root instanceof Element) applyElementAttributes(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let node = walker.currentNode;
    while (node) {
      if (node.nodeType === Node.TEXT_NODE) applyTextNode(node);
      else applyElementAttributes(node);
      node = walker.nextNode();
    }
  }

  function set(nextLanguage, { broadcast = true } = {}) {
    const next = normalize(nextLanguage);
    restoringEnglish = next === "en" && language !== "en";
    language = next;
    document.documentElement.lang = language;
    localStorage.setItem(STORAGE_KEY, language);
    apply(document.documentElement);
    restoringEnglish = false;
    if (broadcast) localStorage.setItem(UPDATE_KEY, JSON.stringify({ language, at: Date.now() }));
    window.dispatchEvent(new CustomEvent("subtitleyc-language-changed", { detail: { language } }));
    return language;
  }

  function start() {
    language = normalize(localStorage.getItem(STORAGE_KEY));
    document.documentElement.lang = language;
    apply(document.documentElement);
    if (!observer) {
      observer = new MutationObserver((records) => {
        for (const record of records) {
          if (record.type === "characterData") applyTextNode(record.target);
          if (record.type === "attributes") applyElementAttributes(record.target);
          for (const node of record.addedNodes || []) apply(node);
        }
      });
      observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: localizedAttributes });
    }
  }

  window.addEventListener("storage", (event) => {
    if (event.key !== UPDATE_KEY || !event.newValue) return;
    try {
      set(JSON.parse(event.newValue).language, { broadcast: false });
    } catch {
      // Ignore malformed cross-window language updates.
    }
  });

  return { apply, current: () => language, normalize, set, start, t: translatedText };
})();

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => window.SubtitleYCI18n.start(), { once: true });
} else {
  window.SubtitleYCI18n.start();
}
