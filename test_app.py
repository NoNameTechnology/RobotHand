import unittest
import os
import json
from models import MotorState, RobotState, CommandHistory
from calibration import calculate_reboot_offset
from sequences import load_poses, save_poses, load_sequences, save_sequences

class TestModels(unittest.TestCase):
    def test_motor_state_properties(self):
        motor = MotorState(0, name="Thumb")
        self.assertEqual(motor.motor_id, 0)
        self.assertEqual(motor.name, "Thumb")
        
        # Test telemetry update
        motor.update_telemetry(100, 200, 45, 0)
        self.assertEqual(motor.present_position, 100)
        self.assertEqual(motor.present_current, 200)
        self.assertEqual(motor.present_temperature, 45)
        self.assertEqual(motor.hardware_error, 0)
        
        motor.set_goal_position(500)
        self.assertEqual(motor.goal_position, 500)
        
        motor.set_torque(True)
        self.assertTrue(motor.torque_enabled)

    def test_command_history(self):
        history = CommandHistory(max_size=3)
        history.push({"id": 1})
        history.push({"id": 2})
        history.push({"id": 3})
        history.push({"id": 4})  # Drops {"id": 1} due to max_size=3
        
        self.assertEqual(len(history.stack), 3)
        self.assertEqual(history.undo(), {"id": 4})
        self.assertEqual(history.undo(), {"id": 3})
        self.assertEqual(history.undo(), {"id": 2})
        self.assertIsNone(history.undo())

class TestCalibration(unittest.TestCase):
    def test_reboot_offset_calculation(self):
        # Scenario 1: calib_zero = 4096, raw_pos = 100 -> round(3996/4096)=1 -> offset 4096
        offset = calculate_reboot_offset(raw_pos=100, calib_zero=4096)
        self.assertEqual(offset, 4096)

        # Scenario 2: calib_zero = 2000, raw_pos = 6100 -> round(-4100/4096)=-1 -> offset -4096
        offset2 = calculate_reboot_offset(raw_pos=6100, calib_zero=2000)
        self.assertEqual(offset2, -4096)
        
        # Scenario 3: calib_zero = 4096, raw_pos = 4000 -> round(96/4096)=0 -> offset 0
        offset3 = calculate_reboot_offset(raw_pos=4000, calib_zero=4096)
        self.assertEqual(offset3, 0)

class TestSequences(unittest.TestCase):
    def setUp(self):
        self.test_poses_file = "test_poses.json"
        self.test_seqs_file = "test_sequences.json"

    def tearDown(self):
        if os.path.exists(self.test_poses_file):
            os.remove(self.test_poses_file)
        if os.path.exists(self.test_seqs_file):
            os.remove(self.test_seqs_file)

    def test_save_load_poses(self):
        poses = {
            "Grasp": {
                "pose": {"1": 1000, "2": 2000},
                "limits": {"1": 1500, "2": 1500},
                "velocities": {"1": 50, "2": 50}
            }
        }
        success = save_poses(poses, self.test_poses_file)
        self.assertTrue(success)
        
        loaded = load_poses(self.test_poses_file)
        self.assertEqual(loaded, poses)

    def test_save_load_sequences(self):
        seqs = {
            "Routine": {
                "frames": [
                    {"name": "Grasp", "wait_type": "Time", "wait_val": 1000}
                ]
            }
        }
        success = save_sequences(seqs, self.test_seqs_file)
        self.assertTrue(success)
        
        loaded = load_sequences(self.test_seqs_file)
        self.assertEqual(loaded, seqs)

if __name__ == "__main__":
    unittest.main()
