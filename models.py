from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional
from config import config

@dataclass
class MotorState:
    motor_id: int
    name: str = ""
    present_position: int = 0
    present_current: int = 0
    present_temperature: int = 0
    hardware_error: int = 0
    torque_enabled: bool = False
    is_endless: bool = True
    soft_grip_enabled: bool = False
    soft_grip_frozen: bool = False
    sync_enabled: bool = True
    calib_zero: Optional[int] = None
    calib_limit: Optional[int] = None
    reboot_offset: int = 0
    
    # Graphs history
    graph_history: List[int] = field(default_factory=lambda: [0]*50, repr=False)
    limit_history: List[int] = field(default_factory=lambda: [1750]*50, repr=False)
    
    # Current UI limit value
    current_limit: int = 1750
    # Position slider value
    goal_position: int = 0
    
    _lock: Lock = field(default_factory=Lock, repr=False, init=False)

    def __post_init__(self):
        if not self.name:
            self.name = f"Motor {self.motor_id}"

    def update_telemetry(self, pos: int, current: int, temp: int, hw_error: int):
        with self._lock:
            self.present_position = pos
            self.present_current = current
            self.present_temperature = temp
            self.hardware_error = hw_error
            
            # Update history
            self.graph_history.pop(0)
            self.graph_history.append(current)
            self.limit_history.pop(0)
            self.limit_history.append(self.current_limit)

    def set_position(self, pos: int):
        with self._lock:
            self.present_position = pos

    def set_goal_position(self, pos: int):
        with self._lock:
            self.goal_position = pos

    def set_torque(self, enabled: bool):
        with self._lock:
            self.torque_enabled = enabled

    def set_mode(self, is_endless: bool):
        with self._lock:
            self.is_endless = is_endless

    def set_soft_grip(self, enabled: bool):
        with self._lock:
            self.soft_grip_enabled = enabled

    def set_soft_grip_frozen(self, frozen: bool):
        with self._lock:
            self.soft_grip_frozen = frozen

    def set_sync(self, enabled: bool):
        with self._lock:
            self.sync_enabled = enabled

    def set_current_limit(self, limit: int):
        with self._lock:
            self.current_limit = limit

    def set_calibration(self, zero: Optional[int], limit: Optional[int]):
        with self._lock:
            self.calib_zero = zero
            self.calib_limit = limit

    def set_reboot_offset(self, offset: int):
        with self._lock:
            self.reboot_offset = offset

    def get_state_dict(self):
        with self._lock:
            return {
                "id": self.motor_id,
                "name": self.name,
                "present_position": self.present_position,
                "present_current": self.present_current,
                "present_temperature": self.present_temperature,
                "hardware_error": self.hardware_error,
                "torque_enabled": self.torque_enabled,
                "is_endless": self.is_endless,
                "soft_grip_enabled": self.soft_grip_enabled,
                "soft_grip_frozen": self.soft_grip_frozen,
                "sync_enabled": self.sync_enabled,
                "calib_zero": self.calib_zero,
                "calib_limit": self.calib_limit,
                "reboot_offset": self.reboot_offset,
                "current_limit": self.current_limit,
                "goal_position": self.goal_position
            }


class CommandHistory:
    def __init__(self, max_size=50):
        self.stack = []
        self.max_size = max_size
        self._lock = Lock()

    def push(self, cmd: dict):
        # cmd = {'type': 'write_position', 'motor_id': 0, 'old_value': 500, 'new_value': 510}
        with self._lock:
            self.stack.append(cmd)
            if len(self.stack) > self.max_size:
                self.stack.pop(0)

    def undo(self) -> Optional[dict]:
        with self._lock:
            if self.stack:
                return self.stack.pop()
            return None


class RobotState:
    def __init__(self, motor_ids: List[int]):
        self.motors: Dict[int, MotorState] = {mid: MotorState(mid) for mid in motor_ids}
        self.soft_grip_global = False
        self.history = CommandHistory(max_size=50)
        self._lock = Lock()

    def set_soft_grip_global(self, enabled: bool):
        with self._lock:
            self.soft_grip_global = enabled

    def get_soft_grip_global(self) -> bool:
        with self._lock:
            return self.soft_grip_global
