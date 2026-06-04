import unittest

from station_mixins.robodk_motion_mixin import RoboDKMotionMixin


class BridgeGripperTimingTests(unittest.TestCase):
    def test_bridge_close_and_open_receive_extra_settle_time(self):
        self.assertEqual(RoboDKMotionMixin.gripper_program_settle_s("gripperclosebridge"), 3.5)
        self.assertEqual(RoboDKMotionMixin.gripper_program_settle_s("bridgeopen"), 3.5)

    def test_other_gripper_programs_keep_default_settle_time(self):
        self.assertEqual(RoboDKMotionMixin.gripper_program_settle_s("grippercellclose"), 3.0)
        self.assertEqual(RoboDKMotionMixin.gripper_program_settle_s("gripperlidclose"), 3.0)


if __name__ == "__main__":
    unittest.main()
