import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from subtitleyc import main


ROOT = Path(__file__).resolve().parents[1]


class LocalizationTests(unittest.TestCase):
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
        self.assertIn('<option value="zh-CN">Simplified Chinese</option>', main_html)

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
        self.assertIn('Root: HKLM', script)
        self.assertIn('ValueName: "InstallerUILanguage"', script)
        self.assertIn('ValueName: "InstallerVersion"', script)
        self.assertIn('ValueData: "{language}"', script)
        self.assertIn("SelectLanguageLabel=选择安装时使用的语言。", chinese)


if __name__ == "__main__":
    unittest.main()
