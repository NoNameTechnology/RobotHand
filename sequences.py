import json
import os
import time
import logging
from typing import Dict, List, Any, Optional
from config import config

logger = logging.getLogger(__name__)

def load_poses(file_path="poses.json") -> Dict[str, Any]:
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                poses = json.load(f)
            logger.info("Poses loaded successfully.")
            return poses
        except Exception as e:
            logger.error(f"Error loading poses: {e}")
    return {}

def save_poses(poses: Dict[str, Any], file_path="poses.json") -> bool:
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(poses, f, indent=2)
        logger.info("Poses saved successfully.")
        return True
    except Exception as e:
        logger.error(f"Error saving poses: {e}")
        return False

def load_sequences(file_path="sequences.json") -> Dict[str, Any]:
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                seqs = json.load(f)
            logger.info("Sequences loaded successfully.")
            return seqs
        except Exception as e:
            logger.error(f"Error loading sequences: {e}")
    return {}

def save_sequences(sequences: Dict[str, Any], file_path="sequences.json") -> bool:
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(sequences, f, indent=2)
        logger.info("Sequences saved successfully.")
        return True
    except Exception as e:
        logger.error(f"Error saving sequences: {e}")
        return False


class SequencePlayer:
    def __init__(self, root, robot_state, hardware_manager, 
                 apply_state_callback, update_status_callback, 
                 highlight_step_callback, done_callback):
        self.root = root
        self.state = robot_state
        self.hardware = hardware_manager
        
        self.apply_state = apply_state_callback
        self.update_status = update_status_callback
        self.highlight_step = highlight_step_callback
        self.on_done = done_callback
        
        self.is_playing = False
        self.frames: List[Dict[str, Any]] = []
        self.current_step = 0

    def start(self, frames: List[Dict[str, Any]]):
        if not self.hardware.is_connected or not frames:
            return
        if self.is_playing:
            return
            
        self.is_playing = True
        self.frames = frames
        self.current_step = 0
        self.update_status("Status: Initializing...")
        self.root.after(0, self._play_step, 0)

    def stop(self):
        if self.is_playing:
            self.is_playing = False
            self.update_status("Status: Stopped")
            self.on_done()

    def _play_step(self, step_index):
        if not self.is_playing or not self.hardware.is_connected:
            self.stop()
            return
            
        if step_index >= len(self.frames):
            self.is_playing = False
            self.update_status("Status: Ready")
            self.on_done()
            return

        self.current_step = step_index
        self.highlight_step(step_index)
        
        frame = self.frames[step_index]
        self.apply_state(frame["state"])
        
        w_type = frame.get("wait_type", "Time")
        w_val = frame.get("wait_val", 1000)

        if w_type == "Time":
            self._wait_time_loop(step_index, w_val)
        elif w_type == "Grasp":
            active_ids = [int(i) for i in frame["state"]["pose"].keys()]
            start_t = time.time()
            self._check_grasp(step_index, active_ids, w_val, start_t)

    def _wait_time_loop(self, step_index, remaining_ms):
        if not self.is_playing or not self.hardware.is_connected:
            self.stop()
            return
            
        if remaining_ms <= 0:
            self._play_step(step_index + 1)
        else:
            self.update_status(f"Time: {remaining_ms/1000.0:.1f}s")
            self.root.after(100, self._wait_time_loop, step_index, remaining_ms - 100)

    def _check_grasp(self, step_index, active_ids, timeout_ms, start_t):
        if not self.is_playing or not self.hardware.is_connected:
            self.stop()
            return
            
        elapsed = (time.time() - start_t) * 1000
        rem = max(0, timeout_ms - elapsed)
        self.update_status(f"Grasp: Waiting for contact ({rem/1000.0:.1f}s Timeout)")
        
        if elapsed > timeout_ms:
            self._play_step(step_index + 1)
            return
            
        # Check contact state using detect_contact logic
        all_contact = True
        for dxl_id in active_ids:
            # We'll use detect_contact helper
            if self._detect_contact_helper(dxl_id) != "contact":
                all_contact = False
                break
                
        if all_contact and active_ids:
            self.update_status("Grasp: Contact detected! ✓")
            self.root.after(100, self._play_step, step_index + 1)
        else:
            self.root.after(50, self._check_grasp, step_index, active_ids, timeout_ms, start_t)

    def _detect_contact_helper(self, dxl_id: int) -> str:
        """Copied contact logic using state attributes"""
        motor = self.state.motors[dxl_id]
        limit = motor.current_limit
        if limit == 0:
            return "none"
            
        # Calculate moving average from history
        history = motor.graph_history
        window = history[-config.avg_window:]
        avg_current = sum(abs(c) for c in window) / len(window)
        
        rate = 0
        if len(history) >= 3:
            vals = [abs(history[-1]), abs(history[-2]), abs(history[-3])]
            rate = vals[0] - vals[2]
            
        contact_by_threshold = avg_current > (limit * config.threshold_pct) and avg_current > 50
        contact_by_spike = rate > config.spike_threshold_ma and avg_current > 30
        
        if contact_by_threshold or contact_by_spike:
            return "contact"
        elif avg_current > (limit * 0.5) and avg_current > 30:
            return "approaching"
        else:
            return "none"
