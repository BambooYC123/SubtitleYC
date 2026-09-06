import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from subtitleyc.qt_desktop import QtDesktopWindow, QMessageBox


class CloseGuardTests(unittest.TestCase):
    def run_guard(self, choice, save_result="saved", dirty=True):
        window = SimpleNamespace(_close_pending=False, shell_language="en", tabs=Mock())
        page = Mock()

        def run(script, callback):
            if script.startswith("JSON.stringify"):
                callback(json.dumps({"dirty": dirty, "busy": False}))
            elif script == "window.subtitleycCloseSaveResult":
                callback(save_result)
            else:
                callback(None)

        page.runJavaScript.side_effect = run
        view = Mock()
        view.page.return_value = page
        accepted = Mock()
        with patch("subtitleyc.qt_desktop.QMessageBox.warning", return_value=choice):
            QtDesktopWindow._confirm_close(window, [view], accepted)
        self.assertFalse(window._close_pending)
        window.tabs.setEnabled.assert_called_with(True)
        return accepted

    def test_cancel_keeps_window_open(self):
        self.run_guard(QMessageBox.StandardButton.Cancel).assert_not_called()

    def test_discard_closes(self):
        self.run_guard(QMessageBox.StandardButton.Discard).assert_called_once()

    def test_save_closes_only_after_success(self):
        self.run_guard(QMessageBox.StandardButton.Save).assert_called_once()
        self.run_guard(QMessageBox.StandardButton.Save, "disk full").assert_not_called()
        self.run_guard(QMessageBox.StandardButton.Save, "changed").assert_not_called()

    def test_clean_view_closes_without_saving(self):
        self.run_guard(QMessageBox.StandardButton.Cancel, dirty=False).assert_called_once()
