import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from subtitleyc import main


ROOT = Path(__file__).resolve().parents[1]


class LocalizationTests(unittest.TestCase):
    def test_readme_links_to_complete_simplified_chinese_version(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese_readme = (ROOT / "README.CN.md").read_text(encoding="utf-8")

        self.assertLess(readme.index("[简体中文 README](README.CN.md)"), readme.index("[README](README.md) |"))
        self.assertIn("[English README](README.md)", chinese_readme)
        for heading in ("## 下载", "## 主要功能", "## 字幕工作流程", "## 键盘快捷键", "## 安全", "## 许可证"):
            self.assertIn(heading, chinese_readme)

        for build_file in ("SubtitleYC.spec", "scripts/build-windows.ps1", "scripts/build-installer.ps1", "scripts/build-public-releases.ps1", "scripts/stage-public-beta.ps1"):
            self.assertIn("README.CN.md", (ROOT / build_file).read_text(encoding="utf-8"))

    def test_app_settings_support_english_and_simplified_chinese(self) -> None:
        self.assertEqual(main.AppSettings().ui_language, "en")
        self.assertEqual(main.AppSettings(ui_language="zh-CN").ui_language, "zh-CN")
        with self.assertRaises(ValidationError):
            main.AppSettings(ui_language="zh-TW")

    def test_installer_language_is_consumed_once_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            with patch.object(main, "SETTINGS_PATH", settings_path), patch.object(
                main, "_consume_installer_ui_language", return_value="zh-CN"
            ):
                settings = main._load_settings()
            self.assertEqual(settings.ui_language, "zh-CN")
            self.assertEqual(json.loads(settings_path.read_text(encoding="utf-8"))["ui_language"], "zh-CN")

            with patch.object(main, "SETTINGS_PATH", settings_path), patch.object(
                main, "_consume_installer_ui_language", return_value=None
            ):
                self.assertEqual(main._load_settings().ui_language, "zh-CN")

    def test_main_and_editor_load_the_shared_localization_layer(self) -> None:
        main_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        editor_html = (ROOT / "static" / "editor.html").read_text(encoding="utf-8")
        self.assertLess(main_html.index("/assets/i18n.js"), main_html.index("/assets/app.js"))
        self.assertLess(editor_html.index("/assets/i18n.js"), editor_html.index("/assets/editor.js"))
        self.assertIn('id="settingUiLanguageInput"', main_html)
        self.assertIn('<option value="en" data-i18n-skip>English</option>', main_html)
        self.assertIn('<option value="zh-CN" data-i18n-skip>中文</option>', main_html)

    def test_editor_exposes_inline_subtitle_style_controls(self) -> None:
        editor_html = (ROOT / "static" / "editor.html").read_text(encoding="utf-8")
        editor_js = (ROOT / "static" / "editor.js").read_text(encoding="utf-8")
        native_preview = (ROOT / "subtitleyc" / "qt_desktop.py").read_text(encoding="utf-8")

        for control_id in ("boldStyleButton", "italicStyleButton", "underlineStyleButton", "textColorInput", "clearStyleButton"):
            self.assertIn(f'id="{control_id}"', editor_html)
        self.assertIn('id="editorTooltip"', editor_html)
        for shortcut in ("Ctrl+B", "Ctrl+I", "Ctrl+U", "Ctrl+S", "Ctrl+O", "Ctrl+R", "Space", "Left Arrow", "Right Arrow", "Delete"):
            self.assertIn(f'data-shortcut="{shortcut}"', editor_html)
        self.assertNotIn('title="Bold (Ctrl+B)"', editor_html)
        self.assertIn("subtitleMarkupRuns", editor_js)
        self.assertIn("setupEditorTooltips", editor_js)
        self.assertIn("subtitle_runs", editor_js)
        self.assertIn("QTextDocument", native_preview)

    def test_simplified_chinese_covers_main_editor_and_dynamic_states(self) -> None:
        source = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
        for english, chinese in (
            ("Settings", "设置"),
            ("Download Video", "下载视频"),
            ("SubtitleYC Editor", "SubtitleYC 编辑器"),
            ("Previous Projects", "以前的项目"),
            ("Save Changes", "保存更改"),
            ("No active jobs", "没有活动任务"),
        ):
            self.assertIn(f'"{english}": "{chinese}"', source)

    def test_installer_prompts_for_language_and_hands_it_to_the_app(self) -> None:
        script = (ROOT / "installer" / "SubtitleYC.iss").read_text(encoding="utf-8")
        chinese = (ROOT / "installer" / "ChineseSimplified.isl").read_text(encoding="utf-8")
        self.assertIn("ShowLanguageDialog=yes", script)
        self.assertIn('Name: "english"', script)
        self.assertIn('Name: "chinesesimplified"', script)
        self.assertIn('Name: "english"; MessagesFile: "compiler:Default.isl"', script)
        self.assertIn("LanguageName=中文", chinese)
        self.assertIn('Root: HKLM', script)
        self.assertIn('ValueName: "InstallerUILanguage"', script)
        self.assertIn('ValueName: "InstallerVersion"', script)
        self.assertIn('ValueData: "{language}"', script)
        self.assertIn("SelectLanguageLabel=选择安装时使用的语言。", chinese)


if __name__ == "__main__":
    unittest.main()
