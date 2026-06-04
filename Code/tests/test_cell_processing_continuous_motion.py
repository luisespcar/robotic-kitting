import unittest

from station_mixins.cell_processing_mixin import CellProcessingMixin


def _battery(color="red", polarity_ok=True):
    return {
        "battery_present": True,
        "battery_color": color,
        "polarity_ok": polarity_ok,
    }


class _CellProcessingHarness(CellProcessingMixin):
    def __init__(self, battery_states, direct_transfer=False):
        self.active_box_slot = 1
        self.boxes = {
            1: {
                "present": True,
                "lid_collected": True,
                "initial_cells_captured": True,
                "color": "red",
                "state": "open_waiting_cells",
                "cells": [None, None, None, None],
            }
        }
        self.slot_state = {
            "box_present": True,
            "confirmed_open": True,
            "battery_slots": {
                f"battery_slot_{idx}": state
                for idx, state in enumerate(battery_states, start=1)
            },
        }
        self.rotation_calls = []
        self.transfer_calls = []
        self.direct_transfer = direct_transfer

    def camera_active_open_box(self, results):
        return 1, self.slot_state

    def active_open_box_vision_confirmed(self, box_slot, slot_state):
        return True

    def update_active_box_color_from_open_vision(self, results):
        return True

    def stop_cycle_if_needed(self, context):
        return False

    def known_or_detected_cell(self, box_slot, cell_num, color, polarity_ok):
        return {"id": f"S{cell_num:02d}", "color": color, "polarity_ok": polarity_ok}

    def mark_cell_in_box(self, box_slot, cell_num, cell, **updates):
        stored = dict(cell)
        stored.update(updates)
        self.boxes[box_slot]["cells"][cell_num - 1] = stored

    def set_box_cell(self, box_slot, cell_num, cell):
        self.boxes[box_slot]["cells"][cell_num - 1] = cell

    def rot_cell(self, cell_num, box_slot, via_place_cell=True):
        self.rotation_calls.append((cell_num, via_place_cell))
        return True

    def transfer_wrong_color_cell(self, source_box_slot, source_cell_num, *args, via_place_cell=True, **kwargs):
        self.transfer_calls.append((source_cell_num, via_place_cell))
        return True, self.direct_transfer

    def fill_operational_boxes_from_rack(self, results, **kwargs):
        return False

    def box_complete(self, box_slot):
        return False


class CellProcessingContinuousMotionTests(unittest.TestCase):
    def test_next_action_in_same_box_skips_place_cell_waypoint(self):
        logic = _CellProcessingHarness([
            _battery(polarity_ok=False),
            _battery(polarity_ok=True),
            _battery(polarity_ok=False),
            _battery(polarity_ok=True),
        ])

        logic.process_active_box_cells({})

        self.assertEqual(logic.rotation_calls, [(1, True), (3, False)])

    def test_direct_box_transfer_keeps_continuous_path(self):
        logic = _CellProcessingHarness([
            _battery(polarity_ok=False),
            _battery(color="blue", polarity_ok=True),
            _battery(polarity_ok=False),
            _battery(polarity_ok=True),
        ], direct_transfer=True)

        logic.process_active_box_cells({})

        self.assertEqual(logic.rotation_calls, [(1, True), (3, False)])
        self.assertEqual(logic.transfer_calls, [(2, False)])

    def test_rack_transfer_requires_place_cell_before_next_box_pick(self):
        logic = _CellProcessingHarness([
            _battery(polarity_ok=False),
            _battery(color="blue", polarity_ok=True),
            _battery(polarity_ok=False),
            _battery(polarity_ok=True),
        ], direct_transfer=False)

        logic.process_active_box_cells({})

        self.assertEqual(logic.rotation_calls, [(1, True), (3, True)])
        self.assertEqual(logic.transfer_calls, [(2, False)])


if __name__ == "__main__":
    unittest.main()
