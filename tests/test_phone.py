"""Phone sync (KDE Connect).  Run: python -m unittest discover -s tests

kdeconnectd is replaced by a fake busctl that answers with the JSON busctl prints, and the
phone's storage by a folder laid out like an Android phone mounted over SFTP.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

TMP = tempfile.mkdtemp(prefix="onegallery-phone-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer, Signal  # noqa: E402

from backend import db, phone  # noqa: E402
from backend.settings import Settings  # noqa: E402

DEVICE = "a1b2c3d4_e5f6"


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def write(path, data=b"x" * 2000, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    if mtime:
        os.utime(path, (mtime, mtime))


class FakeBus:
    """Answers busctl calls like kdeconnectd does. mount_point: the phone's "storage"."""

    def __init__(self, mount_point, reachable=True, plugins=("kdeconnect_sftp", "kdeconnect_ping"),
                 directories=None):
        self.mount_point = mount_point
        self.reachable = reachable
        self.plugins = list(plugins)
        self.directories = directories
        self.running = True
        self.mounted = False
        self.calls = []

    def __call__(self, args, timeout=30):
        method = args[4]
        self.calls.append(method)
        if method == "NameHasOwner":
            return json.dumps({"type": "b", "data": [self.running]})
        reply = {
            "devices": ("as", [DEVICE]),
            "GetAll": ("a{sv}", {"name": {"type": "s", "data": "Pixel 8"},
                                 "type": {"type": "s", "data": "phone"},
                                 "isReachable": {"type": "b", "data": self.reachable}}),
            "loadedPlugins": ("as", self.plugins),
            "isMounted": ("b", self.mounted),
            "mountPoint": ("s", self.mount_point),
            "getDirectories": ("a{sv}", self.directories if self.directories is not None else {
                os.path.join(self.mount_point, "storage/emulated/0"): {"type": "s", "data": "All files"}}),
        }
        if method == "mountAndWait":
            self.mounted = True
            return json.dumps({"type": "b", "data": [True]})
        if method == "unmount":
            self.mounted = False
            return ""
        kind, value = reply[method]
        return json.dumps({"type": kind, "data": [value]})


class PhoneTestCase(unittest.TestCase):
    def setUp(self):
        db.init()
        db.connect().execute("DELETE FROM phone_imports")
        db.connect().commit()
        self.root = tempfile.mkdtemp(dir=TMP)
        self.mount = os.path.join(self.root, "mnt", DEVICE)
        self.storage = os.path.join(self.mount, "storage", "emulated", "0")
        self.dest = os.path.join(self.root, "Pictures", "Phone", "Pixel 8")
        t = time.time() - 3600
        write(f"{self.storage}/DCIM/Camera/IMG_0001.jpg", mtime=t)
        write(f"{self.storage}/DCIM/Camera/VID_0002.mp4", mtime=t + 1)
        write(f"{self.storage}/DCIM/Camera/.trashed-1700000000-IMG_0000.jpg")
        write(f"{self.storage}/DCIM/.thumbnails/123.jpg")
        write(f"{self.storage}/DCIM/Camera/notes.txt")
        write(f"{self.storage}/DCIM/Screenshots/Screenshot_1.png", mtime=t + 2)
        write(f"{self.storage}/Pictures/Screenshots/Screenshot_2.png", mtime=t + 3)
        write(f"{self.storage}/Download/meme.jpg")
        self.bus_fake = FakeBus(self.mount)
        self.bus = phone.KdeConnect(run=self.bus_fake)

    def sync(self, mode="all", screenshots=True):
        return phone.sync_device(self.bus, DEVICE, self.dest, mode, screenshots)

    def imported(self):
        out = []
        for d, _dirs, files in os.walk(self.dest):
            out += [os.path.relpath(os.path.join(d, f), self.dest) for f in files]
        return sorted(out)


class TestKdeConnect(PhoneTestCase):
    def test_lists_phones(self):
        self.assertEqual(self.bus.phones(), [
            {"id": DEVICE, "name": "Pixel 8", "type": "phone", "reachable": True, "browsable": True}])

    def test_not_running_is_not_started(self):
        self.bus_fake.running = False
        self.assertIsNone(self.bus.phones())
        self.assertEqual(self.bus_fake.calls, ["NameHasOwner"])

    def test_browse_plugin_off(self):
        self.bus_fake.plugins = ["kdeconnect_ping"]
        self.assertFalse(self.bus.phones()[0]["browsable"])

    def test_dict_as_pairs(self):
        self.assertEqual(phone._as_dict([["a", 1], ["b", 2]]), {"a": 1, "b": 2})


class TestSync(PhoneTestCase):
    def test_imports_camera_and_screenshots(self):
        stats = self.sync()
        self.assertEqual(stats["imported"], 4)
        self.assertEqual(stats["total"], 4)
        self.assertEqual(self.imported(), [
            "Camera/IMG_0001.jpg", "Camera/VID_0002.mp4",
            "Screenshots/Screenshot_1.png", "Screenshots/Screenshot_2.png"])
        # dates kept, so the pictures sort where they were taken
        self.assertEqual(int(os.path.getmtime(f"{self.dest}/Camera/IMG_0001.jpg")),
                         int(os.path.getmtime(f"{self.storage}/DCIM/Camera/IMG_0001.jpg")))
        # mounted for the sync, unmounted again
        self.assertIn("mountAndWait", self.bus_fake.calls)
        self.assertFalse(self.bus_fake.mounted)

    def test_leaves_an_open_mount_alone(self):
        self.bus_fake.mounted = True
        self.sync()
        self.assertNotIn("mountAndWait", self.bus_fake.calls)
        self.assertNotIn("unmount", self.bus_fake.calls)

    def test_without_screenshots(self):
        self.sync(screenshots=False)
        self.assertEqual(self.imported(), ["Camera/IMG_0001.jpg", "Camera/VID_0002.mp4"])

    def test_only_new_files_next_time(self):
        self.sync()
        os.remove(f"{self.dest}/Camera/IMG_0001.jpg")     # deleted on the computer
        write(f"{self.storage}/DCIM/Camera/IMG_0003.jpg")  # new on the phone
        stats = self.sync()
        self.assertEqual(stats["imported"], 1)
        self.assertNotIn("Camera/IMG_0001.jpg", self.imported())
        self.assertIn("Camera/IMG_0003.jpg", self.imported())

    def test_only_new_ones(self):
        stats = self.sync(mode="new")
        self.assertEqual((stats["imported"], stats["total"]), (0, 4))
        self.assertEqual(self.imported(), [])
        write(f"{self.storage}/DCIM/Camera/IMG_0009.jpg")
        self.assertEqual(self.sync()["imported"], 1)
        self.assertEqual(self.imported(), ["Camera/IMG_0009.jpg"])

    def test_name_taken_by_another_file(self):
        write(f"{self.dest}/Camera/IMG_0001.jpg", b"other")
        self.sync()
        self.assertIn("Camera/IMG_0001 (1).jpg", self.imported())
        with open(f"{self.dest}/Camera/IMG_0001.jpg", "rb") as f:
            self.assertEqual(f.read(), b"other")

    def test_same_file_already_there(self):
        write(f"{self.dest}/Camera/IMG_0001.jpg")
        stats = self.sync()
        self.assertEqual(stats["imported"], 3)
        self.assertNotIn("Camera/IMG_0001 (1).jpg", self.imported())

    def test_no_partial_files_left(self):
        self.sync()
        self.assertFalse([f for f in self.imported() if "onegallery-part" in f])

    def test_offered_folder_inside_dcim(self):
        self.bus_fake.directories = {
            os.path.join(self.storage, "DCIM/Camera"): {"type": "s", "data": "Camera pictures"}}
        self.assertEqual(phone.find_storage_roots(self.bus.storage_dirs(DEVICE)), [self.storage])

    def test_sd_card(self):
        write(f"{self.mount}/storage/1234-ABCD/DCIM/Camera/IMG_SD.jpg")
        self.bus_fake.directories = {
            os.path.join(self.mount, "storage/1234-ABCD"): {"type": "s", "data": "SD card"}}
        self.sync()
        self.assertIn("Camera/IMG_SD.jpg", self.imported())

    def test_no_dcim(self):
        shutil.rmtree(f"{self.storage}/DCIM")
        with self.assertRaises(phone.SyncError):
            self.sync()
        self.assertFalse(self.bus_fake.mounted)

    def test_phone_goes_away(self):
        for n in range(8):
            write(f"{self.storage}/DCIM/Camera/IMG_1{n}.jpg")
        real_copy = phone.copy_item
        copied = []

        def flaky(item, dest_dir):
            if len(copied) >= 2:
                raise OSError(107, "Transport endpoint is not connected")
            copied.append(item)
            return real_copy(item, dest_dir)

        phone.copy_item = flaky
        try:
            with self.assertRaises(phone.SyncError):
                self.sync()
        finally:
            phone.copy_item = real_copy
        # what was copied is remembered; the rest comes next time
        self.assertEqual(len(phone.imported_keys(DEVICE)), 2)
        self.assertEqual(self.sync()["imported"], 10)

    def test_folder_name(self):
        self.assertEqual(phone.safe_folder_name('Lochan\'s "S24"/Ultra'), "Lochan's _S24__Ultra")
        self.assertEqual(phone.safe_folder_name(" .. "), "Phone")


class FakeGallery(QObject):
    toast = Signal(str)

    def __init__(self):
        super().__init__()
        self.added, self.rescanned, self.messages = [], [], []
        self.toast.connect(self.messages.append)

    def addFolder(self, path):
        self.added.append(path)
        return ""

    def rescan_roots(self, roots):
        self.rescanned.append(roots)


class TestController(PhoneTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        super().setUp()
        self._base = phone.phone_base_dir
        phone.phone_base_dir = lambda: os.path.dirname(self.dest)
        self.settings = Settings()
        for device_id in list(self.settings.phones()):
            self.settings.remove_phone(device_id)
        self.gallery = FakeGallery()
        self.sync_ctl = phone.PhoneSync(self.gallery, self.settings, bus=self.bus)
        self.wait(lambda: self.sync_ctl.available)

    def tearDown(self):
        self.sync_ctl.shutdown()
        phone.phone_base_dir = self._base

    def wait(self, condition, timeout=5):
        end = time.time() + timeout
        while not condition() and time.time() < end:
            loop = QEventLoop()
            QTimer.singleShot(20, loop.quit)
            loop.exec()
        self.assertTrue(condition(), "timed out")

    def test_set_up_and_sync(self):
        self.sync_ctl.refresh()
        self.wait(lambda: self.sync_ctl.devices)
        row = self.sync_ctl.devices[0]
        self.assertFalse(row["setUp"])
        self.assertTrue(row["reachable"])
        self.sync_ctl.setUp(DEVICE, "all")
        self.wait(lambda: self.settings.phone(DEVICE) is not None)
        self.assertEqual(len(self.imported()), 4)
        self.assertEqual(self.gallery.added, [os.path.dirname(self.dest)])  # not in the library yet
        self.assertIn("Imported 4 new photos and videos from Pixel 8", self.gallery.messages[-1])
        row = self.sync_ctl.devices[0]
        self.assertTrue(row["setUp"] and row["auto"])
        self.assertEqual(row["count"], 4)

    def test_failed_first_sync_is_not_set_up(self):
        shutil.rmtree(f"{self.storage}/DCIM")
        self.sync_ctl.refresh()
        self.wait(lambda: self.sync_ctl.devices)
        self.sync_ctl.setUp(DEVICE, "new")
        self.wait(lambda: self.gallery.messages)
        self.assertIsNone(self.settings.phone(DEVICE))
        self.assertIn("No camera folder", self.gallery.messages[-1])

    def test_forget(self):
        self.sync_ctl.refresh()
        self.wait(lambda: self.sync_ctl.devices)
        self.sync_ctl.setUp(DEVICE, "new")
        self.wait(lambda: self.settings.phone(DEVICE) is not None)
        self.sync_ctl.forget(DEVICE)
        self.assertIsNone(self.settings.phone(DEVICE))
        self.wait(lambda: not phone.imported_keys(DEVICE))

    def test_kde_connect_missing(self):
        def broken(args, timeout=30):
            raise phone.BusError("The name org.kde.kdeconnect was not provided by any .service files")
        ctl = phone.PhoneSync(self.gallery, self.settings, bus=phone.KdeConnect(run=broken))
        ctl.refresh()
        self.wait(lambda: not ctl._looking)
        self.assertFalse(ctl.available)
        self.assertEqual(ctl.devices, [])
        ctl.shutdown()


if __name__ == "__main__":
    unittest.main()
