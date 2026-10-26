"""Share menu: helper protocol tested against a mock org.kde.purpose module.
Run: python -m unittest discover -s tests"""

import os
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend import share  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")


class ShareHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="onegallery-share-test-")
        runtime = os.path.join(cls.tmp, "qml")
        with open(runtime, "w") as f:
            f.write(f"#!/bin/sh\nexec '{sys.executable}' '{os.path.join(FIXTURES, 'fake_qml.py')}' \"$@\"\n")
        os.chmod(runtime, os.stat(runtime).st_mode | stat.S_IEXEC)
        cls.saved = {k: os.environ.get(k) for k in ("ONEGALLERY_QML", "ONEGALLERY_QML_IMPORT_PATH")}
        os.environ["ONEGALLERY_QML"] = runtime
        os.environ["ONEGALLERY_QML_IMPORT_PATH"] = os.path.join(FIXTURES, "mock_purpose")
        cls.files = []
        for name in ("a.jpg", "b.jpg"):
            path = os.path.join(cls.tmp, name)
            open(path, "wb").close()
            cls.files.append(path)

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def run_helper(self, plugin_id):
        cmd = share.helper_command("run", "image/jpeg", plugin_id, self.files)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=share.helper_env())
        events = share.parse_events(result.stderr + result.stdout)
        return result.returncode, events

    def test_available(self):
        self.assertTrue(share.available())

    def test_list_targets(self):
        targets = share.list_targets(self.files, "image/jpeg")
        self.assertEqual([t["id"] for t in targets], ["clipboardplugin", "kdeconnectplugin", "imgurplugin"])
        self.assertEqual(targets[1]["name"], "Send to Device...")
        self.assertEqual(targets[2]["icon"], "edit-paste")

    def test_run_success_with_url(self):
        code, events = self.run_helper("imgurplugin")
        finished = [e for e in events if e["event"] == "finished"][0]
        self.assertEqual(code, 0)
        self.assertEqual(finished["output"]["files"], 2)  # both files handed over
        message, url = share.describe_result(finished)
        self.assertEqual(url, "https://i.imgur.com/abc.png")
        self.assertIn("Link copied", message)

    def test_run_error(self):
        code, events = self.run_helper("kdeconnectplugin")
        finished = [e for e in events if e["event"] == "finished"][0]
        self.assertEqual(code, 1)
        message, url = share.describe_result(finished)
        self.assertIn("No device connected", message)
        self.assertEqual(url, "")

    def test_unknown_target(self):
        code, events = self.run_helper("nosuchplugin")
        self.assertEqual(code, 1)
        self.assertIn("not available", events[0]["message"])

    def test_helpers(self):
        self.assertTrue(share.is_clipboard("clipboardplugin"))
        self.assertFalse(share.is_clipboard("imgurplugin"))
        self.assertEqual(share.common_mime(self.files), "image/jpeg")


if __name__ == "__main__":
    unittest.main()
