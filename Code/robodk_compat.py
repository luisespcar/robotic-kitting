"""Optional RoboDK import compatibility layer.

Generated from the original monolithic Main.py/StateMachine.py so the
project can be modified by responsibility without changing behavior.
"""

from __future__ import annotations

# =========================================================

try:
    from robodk.robolink import Robolink, ITEM_TYPE_FRAME, ITEM_TYPE_OBJECT, ITEM_TYPE_TARGET
    from robodk.robomath import Pose_2_TxyzRxyz, TxyzRxyz_2_Pose, rotx, roty, rotz
except ImportError:
    try:
        from robolink import Robolink, ITEM_TYPE_FRAME, ITEM_TYPE_OBJECT, ITEM_TYPE_TARGET
        from robodk import Pose_2_TxyzRxyz, TxyzRxyz_2_Pose, rotx, roty, rotz
    except ImportError:
        Robolink = None
        ITEM_TYPE_FRAME = None
        ITEM_TYPE_OBJECT = None
        ITEM_TYPE_TARGET = None
        Pose_2_TxyzRxyz = TxyzRxyz_2_Pose = None
