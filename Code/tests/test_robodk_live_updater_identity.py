import unittest

from app_config import RACK_SLOT_IDS
from robodk_live_updater import RoboDKLiveUpdater


class _StationMemory:
    def __init__(self):
        self.boxes = {
            1: {"initial_cells_captured": False, "cells": [None, None, None, None]},
            2: {"initial_cells_captured": False, "cells": [None, None, None, None]},
            3: {"initial_cells_captured": False, "cells": [None, None, None, None]},
        }


class RoboDKLiveUpdaterIdentityTests(unittest.TestCase):
    def setUp(self):
        self.updater = RoboDKLiveUpdater.__new__(RoboDKLiveUpdater)
        self.updater.slots = {
            slot_id: self.updater.new_slot_state()
            for slot_id in RACK_SLOT_IDS
        }
        self.updater.station_logic = _StationMemory()
        self.visibility_calls = []
        self.pose_calls = []
        self.updater.set_visible = lambda name, visible: self.visibility_calls.append((name, visible))
        self.updater.set_pose_by_polarity = lambda name, polarity: self.pose_calls.append((name, polarity))

    @staticmethod
    def _cell(cell_id, color, polarity_ok):
        return {"id": cell_id, "color": color, "polarity_ok": polarity_ok}

    def _open_box_once(self, box_slot, cells):
        box = self.updater.station_logic.boxes[box_slot]
        box["initial_cells_captured"] = True
        box["cells"] = cells
        return self.updater.initialize_cells_once(f"rack_slot_{box_slot}")

    @staticmethod
    def _base_cell_calls(calls, object_ids):
        return [call for call in calls if call[0] in object_ids]

    def test_each_open_box_initializes_its_four_visual_cells_only_once(self):
        first_capture = [
            self._cell("S01", "red", True),
            self._cell("S02", "green", False),
            self._cell("S03", "blue", True),
            self._cell("S04", "red", False),
        ]
        self.assertTrue(self._open_box_once(1, first_capture))
        first_pose_calls = list(self.pose_calls)

        changed_memory = [
            self._cell("S01", "blue", False),
            self._cell("S02", "blue", True),
            self._cell("S03", "red", False),
            self._cell("S04", "green", True),
        ]
        self.updater.station_logic.boxes[1]["cells"] = changed_memory
        self.assertTrue(self.updater.initialize_cells_once("rack_slot_1"))

        self.assertEqual(first_pose_calls, self.pose_calls)
        self.assertIn(("S01", True), first_pose_calls)
        self.assertIn(("S02", False), first_pose_calls)

    def test_opening_second_box_does_not_touch_first_box_cells(self):
        self.assertTrue(self._open_box_once(1, [
            self._cell("S01", "red", True),
            self._cell("S02", "red", True),
            self._cell("S03", "red", True),
            self._cell("S04", "red", True),
        ]))
        first_box_calls = self._base_cell_calls(self.pose_calls, {"S01", "S02", "S03", "S04"})

        self.assertTrue(self._open_box_once(2, [
            self._cell("S05", "blue", False),
            self._cell("S06", "blue", False),
            self._cell("S07", "blue", False),
            self._cell("S08", "blue", False),
        ]))

        self.assertEqual(
            first_box_calls,
            self._base_cell_calls(self.pose_calls, {"S01", "S02", "S03", "S04"}),
        )
        self.assertIn(("S05", False), self.pose_calls)


if __name__ == "__main__":
    unittest.main()
