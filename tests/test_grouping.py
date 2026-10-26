"""Grid grouping by zoom level: days, months, years.  Run: python -m unittest discover -s tests"""

import os
import sys
import tempfile
import unittest
from datetime import date

os.environ.setdefault("ONEGALLERY_HOME", os.path.join(tempfile.mkdtemp(prefix="onegallery-group-test-"), "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from backend.models import PhotoModel  # noqa: E402
from backend.models import group_for_columns  # noqa: E402

app = QCoreApplication.instance() or QCoreApplication([])

TODAY = date.today()
DAYS = [date(TODAY.year, 10, 8), date(TODAY.year, 10, 8), date(TODAY.year, 10, 7),
        date(TODAY.year, 9, 28), date(TODAY.year, 8, 23), date(TODAY.year - 1, 12, 31),
        date(TODAY.year - 1, 5, 2)]


def items():
    out = []
    for i, d in enumerate(DAYS):
        # id, path, taken, mtime, w, h, size, available, favorite, video, duration, day
        out.append([i + 1, f"/p/{i}.jpg", 0, 0.0, 10, 10, 100, 1, 0, 0, 0.0, d.toordinal()])
    return out


def sections(model):
    return [model.data(model.index(r), PhotoModel.SectionRole) for r in range(model.rowCount())]


def labels(model):
    seen = []
    for s in sections(model):
        if not seen or seen[-1] != s:
            seen.append(s)
    return [model.dayLabel(s) for s in seen]


class GroupingTests(unittest.TestCase):
    def setUp(self):
        self.model = PhotoModel(columns=4, kind="none", auto_load=False)
        self.model._apply(self.model._generation, items())

    def test_levels(self):
        self.assertEqual([group_for_columns(c) for c in (2, 6, 7, 9, 10, 12)],
                         ["day", "day", "month", "month", "year", "year"])

    def test_days(self):
        self.assertEqual(self.model.groupBy, "day")
        self.assertEqual(len(labels(self.model)), 6)   # Oct 8, Oct 7, Sep 28, Aug 23, Dec 31, May 2

    def test_months(self):
        self.model.columns = 8
        self.assertEqual(self.model.groupBy, "month")
        last = TODAY.year - 1
        self.assertEqual(labels(self.model), ["October", "September", "August",
                                              f"December {last}", f"May {last}"])
        # one row holds all three October pictures, across their two days
        self.assertEqual(self.model.data(self.model.index(0), PhotoModel.ItemsRole).__len__(), 3)

    def test_years(self):
        self.model.columns = 11
        self.assertEqual(labels(self.model), [str(TODAY.year), str(TODAY.year - 1)])
        self.assertEqual(self.model.monthLabelForRow(0), str(TODAY.year))

    def test_select_whole_group(self):
        self.model.columns = 8
        oct_section = sections(self.model)[0]
        self.model.toggleDay(oct_section)
        self.assertEqual(sorted(self.model.selectedIds()), [1, 2, 3])
        self.assertTrue(self.model.isDaySelected(oct_section))
        self.model.columns = 12
        self.model.clearSelection()
        self.model.toggleDay(f"y{TODAY.year}")
        self.assertEqual(len(self.model.selectedIds()), 5)

    def test_back_to_days(self):
        self.model.columns = 12
        self.model.columns = 3
        self.assertEqual(self.model.groupBy, "day")
        self.assertEqual(len(labels(self.model)), 6)


if __name__ == "__main__":
    unittest.main()
