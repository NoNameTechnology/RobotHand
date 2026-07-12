import os
import json
import time
import queue
import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from config import config, DEFAULT_GRASP_TYPES, OP_MODE_VELOCITY, OP_MODE_CURRENT_BASED_POSITION
from models import RobotState
from hardware import HardwareManager
from calibration import load_calibration, save_calibration, load_motor_names, save_motor_names, calculate_reboot_offset
from sequences import load_poses, save_poses, load_sequences, save_sequences, SequencePlayer
from ui import RobotHandUI

class DynamixelSquadApp:
    def __init__(self, root):
        self.root = root
        
        # Load configurations and set initial state
        self.motor_names = load_motor_names()
        self.calib_zero, self.calib_limit = load_calibration()
        self.saved_poses = load_poses()
        self.saved_sequences = load_sequences()
        self.sequence_frames = []
        self.seq_unsaved_changes = False
        
        # Geometry and Layout values
        self.is_dark_mode = True
        self._load_window_layout()
        
        # Instantiate State models
        self.state = RobotState(config.motor_ids)
        # Seed values to models
        for dxl_id in config.motor_ids:
            motor = self.state.motors[dxl_id]
            motor.name = self.motor_names.get(dxl_id, f"Motor {dxl_id}")
            motor.set_calibration(self.calib_zero.get(dxl_id), self.calib_limit.get(dxl_id))
            if motor.calib_zero is not None and motor.calib_limit is not None:
                motor.set_mode(False) # Default to position mode if calibrated
            else:
                motor.set_mode(True)  # Default to endless if uncalibrated
                
        # Instantiate Hardware manager
        self.hardware = HardwareManager(self.state)
        self.hardware.start()
        
        # Instantiate UI
        self.ui = RobotHandUI(self.root, self)
        
        # Instantiate Sequence Player
        self.player = SequencePlayer(
            root=self.root,
            robot_state=self.state,
            hardware_manager=self.hardware,
            apply_state_callback=self.apply_state,
            update_status_callback=self.update_sequence_status,
            highlight_step_callback=self.highlight_sequence_step,
            done_callback=self.on_sequence_done
        )
        
        # Sync slider defaults into UI and bind slider start values
        self.slider_start_values = {}
        self._sync_ui_states()
        
        # Start GUI polling timer for telemetry
        self.root.after(50, self._update_ui_from_telemetry)
        
        self.root.protocol("WM_DELETE_WINDOW", self.safe_quit)
        logger.info("Application initialized.")

    def _sync_ui_states(self):
        self.ui.update_pose_combobox()
        self.ui.update_sequence_combobox()
        
        # Bind slider press releases to capture drag action states for undo history
        for dxl_id, slider in self.ui.ui_indiv_sliders.items():
            slider.bind("<Button-1>", lambda event, id=dxl_id: self.record_slider_start(id), add="+")
            
        for dxl_id in config.motor_ids:
            motor = self.state.motors[dxl_id]
            self.ui.sync_vars[dxl_id].set(motor.sync_enabled)
            self.ui.torque_vars[dxl_id].set(motor.torque_enabled)
            self.ui.mode_vars[dxl_id].set(motor.is_endless)
            self.ui.soft_grip_vars[dxl_id].set(motor.soft_grip_enabled)
            self.ui.current_vars[dxl_id].set(motor.current_limit)
            self.check_calibration_status(dxl_id)
            
        self.ui.root.title(f"Dynamixel XL330-M288 Hand-Controller ({config.port} @ {config.baudrate})")

    # --- UNDO HISTORY HANDLERS ---
    def record_slider_start(self, dxl_id: int):
        self.slider_start_values[dxl_id] = self.ui.slider_vars[dxl_id].get()

    def perform_undo(self):
        cmd = self.state.history.undo()
        if not cmd:
            messagebox.showinfo("Undo", "No actions to undo.")
            return
            
        dxl_id = cmd["motor_id"]
        old_val = cmd["old_value"]
        
        # Revert value in UI and send command to hardware
        self.ui.slider_vars[dxl_id].set(old_val)
        if self.state.motors[dxl_id].is_endless:
            self.hardware.enqueue_command({"type": "goal_velocity", "motor_id": dxl_id, "value": old_val})
        else:
            self.hardware.enqueue_command({"type": "goal_position", "motor_id": dxl_id, "value": old_val})
            
        logger.info(f"Undo action performed: motor {dxl_id} reverted to {old_val}.")

    # --- CALIBRATION HANDLERS ---
    def handle_calibration_click(self, dxl_id: int, point_type: str):
        if not self.hardware.is_connected:
            return
            
        motor = self.state.motors[dxl_id]
        target_pos = None
        is_set = False
        
        if point_type == "zero" and motor.calib_zero is not None:
            is_set = True
            target_pos = motor.calib_zero
        elif point_type == "limit" and motor.calib_limit is not None:
            is_set = True
            target_pos = motor.calib_limit
            
        if is_set:
            # Move to calibration position
            if not self.ensure_torque_enabled([dxl_id]):
                return
            if motor.torque_enabled and not motor.is_endless:
                self.hardware.enqueue_command({"type": "goal_position", "motor_id": dxl_id, "value": target_pos})
                self.ui.slider_vars[dxl_id].set(target_pos)
                motor.set_soft_grip_frozen(False)
            return

        # Fetch raw position and set calibration
        pos = motor.present_position
        if point_type == "zero":
            motor.set_reboot_offset(0)
            motor.set_calibration(pos, motor.calib_limit)
            self.calib_zero[dxl_id] = pos
            self.ui.ui_btn_zero[dxl_id].config(text=f"Z: {pos}")
        elif point_type == "limit":
            motor.set_calibration(motor.calib_zero, pos)
            self.calib_limit[dxl_id] = pos
            self.ui.ui_btn_limit[dxl_id].config(text=f"L: {pos}")
            
        self.check_calibration_status(dxl_id)
        save_calibration(self.calib_zero, self.calib_limit)

    def delete_calibration(self, dxl_id: int, point_type: str):
        motor = self.state.motors[dxl_id]
        if point_type == "zero":
            motor.set_calibration(None, motor.calib_limit)
            self.calib_zero[dxl_id] = None
            self.ui.ui_btn_zero[dxl_id].config(text="Set Zero")
        elif point_type == "limit":
            motor.set_calibration(motor.calib_zero, None)
            self.calib_limit[dxl_id] = None
            self.ui.ui_btn_limit[dxl_id].config(text="Set Limit")
            
        self.check_calibration_status(dxl_id)
        save_calibration(self.calib_zero, self.calib_limit)

    def check_calibration_status(self, dxl_id: int):
        motor = self.state.motors[dxl_id]
        is_fully_calibrated = (motor.calib_zero is not None and motor.calib_limit is not None)
        
        if is_fully_calibrated:
            if motor.is_endless:
                self.ui.mode_vars[dxl_id].set(False)
                if self.hardware.is_connected:
                    self.on_mode_toggle(dxl_id)
            
            min_val = min(motor.calib_zero, motor.calib_limit)
            max_val = max(motor.calib_zero, motor.calib_limit)
            self.ui.ui_indiv_sliders[dxl_id].config(state=tk.NORMAL, from_=min_val, to=max_val)
        else:
            if not motor.is_endless:
                self.ui.mode_vars[dxl_id].set(True)
                if self.hardware.is_connected:
                    self.on_mode_toggle(dxl_id)
                    
            if not motor.is_endless or not self.hardware.is_connected:
                self.ui.ui_indiv_sliders[dxl_id].config(state=tk.DISABLED)
            else:
                self.ui.ui_indiv_sliders[dxl_id].config(state=tk.NORMAL, from_=config.velocity_min, to=config.velocity_max)
                self.ui.slider_vars[dxl_id].set(0)

    def calculate_reboot_offset_align(self, dxl_id: int):
        motor = self.state.motors[dxl_id]
        if motor.calib_zero is not None:
            raw_pos = motor.present_position - motor.reboot_offset
            offset = calculate_reboot_offset(raw_pos, motor.calib_zero)
            motor.set_reboot_offset(offset)
            logger.info(f"Reboot alignment offset for motor {dxl_id} calculated: {offset} ticks.")
        self.check_calibration_status(dxl_id)

    # --- POSE & SEQUENCE LIBRARY HANDLERS ---
    def save_single_pose(self):
        name = self.ui.pose_name_var.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Please enter a name for the pose!")
            return
        
        pose = {}
        limits = {}
        velocities = {}
        for dxl_id in config.motor_ids:
            motor = self.state.motors[dxl_id]
            if not motor.is_endless and motor.calib_zero is not None:
                pose[dxl_id] = self.ui.slider_vars[dxl_id].get()
                limits[dxl_id] = self.ui.current_vars[dxl_id].get()
                velocities[dxl_id] = self.ui.master_vel_var.get()
                
        state_dict = {
            "pose": pose,
            "limits": limits,
            "velocities": velocities,
            "soft_grip_global": self.state.soft_grip_global,
            "soft_grip_motors": {str(did): self.state.motors[did].soft_grip_enabled for did in config.motor_ids}
        }
        
        self.saved_poses[name] = state_dict
        if save_poses(self.saved_poses):
            self.ui.update_pose_combobox()
            self.ui.cb_poses.set(name)
            messagebox.showinfo("Success", f"Pose '{name}' saved!")

    def delete_selected_pose(self):
        name = self.ui.cb_poses.get()
        if not name or name not in self.saved_poses:
            return
        if messagebox.askyesno("Delete", f"Do you really want to delete the pose '{name}'?"):
            del self.saved_poses[name]
            save_poses(self.saved_poses)
            self.ui.cb_poses.set("")
            self.ui.update_pose_combobox()

    def go_to_selected_pose(self):
        name = self.ui.cb_poses.get()
        if name in self.saved_poses and self.hardware.is_connected:
            active_ids = [did for did in config.motor_ids if self.ui.ui_sync_checkboxes[did].instate(['selected'])]
            if not self.ensure_torque_enabled(active_ids):
                return
            self.apply_state(self.saved_poses[name])

    def apply_state(self, state):
        pose = state.get("pose", {})
        limits = state.get("limits", {})
        velocities = state.get("velocities", {})
        
        # Soft-Grip Global
        sg_global = state.get("soft_grip_global", False)
        self.state.set_soft_grip_global(sg_global)
        self.ui.soft_grip_global.set(sg_global)
        self._update_soft_grip_global_button()
        
        sg_motors = state.get("soft_grip_motors", {})
        
        for dxl_id in config.motor_ids:
            motor = self.state.motors[dxl_id]
            dxl_str = str(dxl_id)
            
            # Resolve Soft-Grip for motor
            val = sg_motors.get(dxl_str, "default")
            if val == "default":
                resolved_sg = self.ui.seq_default_sg_vars[dxl_id].get()
            else:
                resolved_sg = True if val is True or val == "True" else False
                
            motor.set_soft_grip(resolved_sg)
            self.ui.soft_grip_vars[dxl_id].set(resolved_sg)
            motor.set_soft_grip_frozen(False) # Reset freeze status on applying new pose
            
        for dxl_id_str, target_pos in pose.items():
            dxl_id = int(dxl_id_str)
            motor = self.state.motors[dxl_id]
            if not motor.is_endless and motor.torque_enabled:
                # Apply current limit
                if dxl_id_str in limits:
                    limit_val = limits[dxl_id_str]
                    if limit_val == "default" or limit_val == "default_ma":
                        limit = self.ui.seq_default_ma_vars[dxl_id].get()
                    else:
                        limit = int(limit_val)
                else:
                    limit = self.ui.seq_default_ma_vars[dxl_id].get()
                    
                self.ui.current_vars[dxl_id].set(limit)
                self.ui.current_labels[dxl_id].config(text=str(limit))
                self.hardware.enqueue_command({"type": "goal_current", "motor_id": dxl_id, "value": limit})
                
                # Apply velocity profiles
                vel_pct = velocities.get(dxl_id_str, velocities.get(dxl_id, 100))
                hardware_vel = int((vel_pct / 100.0) * 300) if vel_pct < 100 else 0
                if hardware_vel == 0 and vel_pct < 100: 
                    hardware_vel = 1
                self.hardware.enqueue_command({"type": "profile_velocity", "motor_id": dxl_id, "value": hardware_vel})

                # Apply target goal position
                self.ui.slider_vars[dxl_id].set(target_pos)
                self.hardware.enqueue_command({"type": "goal_position", "motor_id": dxl_id, "value": target_pos})

    def get_wait_settings(self):
        try:
            val = int(self.ui.wait_val_var.get())
        except ValueError:
            val = 1000
        return self.ui.wait_type_var.get(), val

    def add_pose_to_sequence(self):
        name = self.ui.cb_poses.get()
        if name in self.saved_poses:
            import copy
            state = copy.deepcopy(self.saved_poses[name])
            state["limits"] = {str(did): "default" for did in config.motor_ids}
            state["soft_grip_motors"] = {str(did): "default" for did in config.motor_ids}
            w_type, w_val = self.get_wait_settings()
            frame_data = {"name": name, "state": state, "wait_type": w_type, "wait_val": w_val}
            self.sequence_frames.append(frame_data)
            self.mark_seq_unsaved()
            self.ui.refresh_sequence_listbox()

    def append_current_pose_to_sequence(self):
        import copy
        pose = {}
        limits = {}
        velocities = {}
        for dxl_id in config.motor_ids:
            motor = self.state.motors[dxl_id]
            if not motor.is_endless and motor.calib_zero is not None:
                pose[dxl_id] = self.ui.slider_vars[dxl_id].get()
                limits[dxl_id] = self.ui.current_vars[dxl_id].get()
                velocities[dxl_id] = self.ui.master_vel_var.get()
                
        state_dict = {
            "pose": pose,
            "limits": {str(did): "default" for did in config.motor_ids},
            "velocities": velocities,
            "soft_grip_global": self.state.soft_grip_global,
            "soft_grip_motors": {str(did): "default" for did in config.motor_ids}
        }
        w_type, w_val = self.get_wait_settings()
        frame_data = {"name": "Custom", "state": state_dict, "wait_type": w_type, "wait_val": w_val}
        self.sequence_frames.append(frame_data)
        self.mark_seq_unsaved()
        self.ui.refresh_sequence_listbox()

    def seq_move_up(self):
        idx = self.ui.seq_listbox.curselection()
        if not idx or idx[0] == 0: 
            return
        i = idx[0]
        self.sequence_frames[i], self.sequence_frames[i-1] = self.sequence_frames[i-1], self.sequence_frames[i]
        self.mark_seq_unsaved()
        self.ui.refresh_sequence_listbox()
        self.ui.seq_listbox.selection_set(i-1)

    def seq_move_down(self):
        idx = self.ui.seq_listbox.curselection()
        if not idx or idx[0] == len(self.sequence_frames)-1: 
            return
        i = idx[0]
        self.sequence_frames[i], self.sequence_frames[i+1] = self.sequence_frames[i+1], self.sequence_frames[i]
        self.mark_seq_unsaved()
        self.ui.refresh_sequence_listbox()
        self.ui.seq_listbox.selection_set(i+1)

    def seq_delete_step(self):
        idx = self.ui.seq_listbox.curselection()
        if not idx: 
            return
        del self.sequence_frames[idx[0]]
        self.mark_seq_unsaved()
        self.ui.refresh_sequence_listbox()

    def seq_clear_all(self):
        if not self.check_unsaved_sequence_changes():
            return
        self.sequence_frames.clear()
        self.ui.refresh_sequence_listbox()
        self.seq_unsaved_changes = False

    def ctx_delete_step(self, idx):
        if 0 <= idx < len(self.sequence_frames):
            del self.sequence_frames[idx]
            self.mark_seq_unsaved()
            self.ui.refresh_sequence_listbox()

    def ctx_duplicate_step(self, idx):
        if 0 <= idx < len(self.sequence_frames):
            import copy
            dup = copy.deepcopy(self.sequence_frames[idx])
            dup["name"] = dup.get("name", "Step") + " (Copy)"
            self.sequence_frames.insert(idx + 1, dup)
            self.mark_seq_unsaved()
            self.ui.refresh_sequence_listbox()
            self.ui.seq_listbox.selection_clear(0, tk.END)
            self.ui.seq_listbox.selection_set(idx + 1)

    def mark_seq_unsaved(self):
        self.seq_unsaved_changes = True

    def save_sequence_to_file(self):
        name = self.ui.seq_name_var.get().strip()
        if not name or not self.sequence_frames:
            messagebox.showwarning("Warning", "Invalid name or sequence is empty!")
            return
        self.saved_sequences[name] = {
            "frames": self.sequence_frames,
            "default_sg": {str(did): var.get() for did, var in self.ui.seq_default_sg_vars.items()},
            "default_ma": {str(did): var.get() for did, var in self.ui.seq_default_ma_vars.items()}
        }
        if save_sequences(self.saved_sequences):
            self.ui.update_sequence_combobox()
            self.ui.cb_sequences.set(name)
            self.seq_unsaved_changes = False
            messagebox.showinfo("Success", f"Sequence '{name}' saved!")

    def delete_selected_seq(self):
        name = self.ui.cb_sequences.get()
        if not name or name not in self.saved_sequences:
            return
        if messagebox.askyesno("Delete", f"Do you really want to delete sequence '{name}'?"):
            del self.saved_sequences[name]
            save_sequences(self.saved_sequences)
            self.ui.cb_sequences.set("")
            self.ui.update_sequence_combobox()

    def check_unsaved_sequence_changes(self) -> bool:
        if not self.seq_unsaved_changes or not self.sequence_frames:
            return True
            
        dialog = tk.Toplevel(self.root)
        dialog.title("Ungespeicherte Änderungen")
        dialog.geometry("400x180")
        dialog.resizable(False, False)
        dialog.configure(bg=self.ui.BG_COLOR)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry(f"+{self.root.winfo_x() + 100}+{self.root.winfo_y() + 100}")
        
        lbl_msg = tk.Label(dialog, text="You have unsaved changes in the sequence.\nWould you like to save them now?",
                           bg=self.ui.BG_COLOR, fg=self.ui.FG_COLOR, font=("Segoe UI", 10))
        lbl_msg.pack(pady=(15, 10))
        
        name_row = tk.Frame(dialog, bg=self.ui.BG_COLOR)
        name_row.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(name_row, text="Name:", bg=self.ui.BG_COLOR, fg=self.ui.SUBTEXT, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        
        default_name = self.ui.seq_name_var.get().strip() or "MySequence"
        name_var = tk.StringVar(value=default_name)
        ent_name = ttk.Entry(name_row, textvariable=name_var, font=("Segoe UI", 9))
        ent_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        btn_frame = tk.Frame(dialog, bg=self.ui.BG_COLOR)
        btn_frame.pack(pady=15)
        
        result = tk.StringVar(value="cancel")
        
        def on_save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Warning", "Please enter a name!", parent=dialog)
                return
            
            self.ui.seq_name_var.set(name)
            self.saved_sequences[name] = {
                "frames": self.sequence_frames,
                "default_sg": {str(did): var.get() for did, var in self.ui.seq_default_sg_vars.items()},
                "default_ma": {str(did): var.get() for did, var in self.ui.seq_default_ma_vars.items()}
            }
            if save_sequences(self.saved_sequences):
                self.ui.update_sequence_combobox()
                self.ui.cb_sequences.set(name)
                self.seq_unsaved_changes = False
                result.set("save")
                dialog.destroy()
                
        def on_discard():
            self.seq_unsaved_changes = False
            result.set("discard")
            dialog.destroy()
            
        def on_cancel():
            result.set("cancel")
            dialog.destroy()
            
        btn_save = ttk.Button(btn_frame, text="Save", command=on_save, style="Success.TButton", width=11)
        btn_save.pack(side=tk.LEFT, padx=5)
        btn_discard = ttk.Button(btn_frame, text="Discard", command=on_discard, style="Danger.TButton", width=11)
        btn_discard.pack(side=tk.LEFT, padx=5)
        btn_cancel = ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=11)
        btn_cancel.pack(side=tk.LEFT, padx=5)
        
        dialog.wait_window()
        return result.get() in ("save", "discard")

    def load_selected_sequence(self):
        name = self.ui.cb_sequences.get()
        if name in self.saved_sequences:
            seq_data = self.saved_sequences[name]
            for var in self.ui.seq_default_sg_vars.values():
                var.set(False)
            for var in self.ui.seq_default_ma_vars.values():
                var.set(1750)
            
            if isinstance(seq_data, dict):
                raw_frames = seq_data.get("frames", [])
                defaults_sg = seq_data.get("default_sg", {})
                for k, v in defaults_sg.items():
                    did = int(k)
                    if did in self.ui.seq_default_sg_vars:
                        self.ui.seq_default_sg_vars[did].set(v)
                defaults_ma = seq_data.get("default_ma", {})
                for k, v in defaults_ma.items():
                    did = int(k)
                    if did in self.ui.seq_default_ma_vars:
                        self.ui.seq_default_ma_vars[did].set(int(v))
            else:
                raw_frames = seq_data

            frames = []
            for f in raw_frames:
                if "pose" in f and "state" not in f:
                    frames.append({
                        "name": "Legacy", 
                        "state": {"pose": f["pose"], "limits": {}},
                        "wait_type": "Time",
                        "wait_val": f.get("delay", 1000)
                    })
                else:
                    frames.append(f)
            self.sequence_frames = frames
            self.ui.seq_name_var.set(name)
            self.ui.refresh_sequence_listbox()
            self.seq_unsaved_changes = False

    def play_sequence(self):
        if not self.hardware.is_connected or len(self.sequence_frames) == 0: 
            return
        if self.player.is_playing: 
            return
            
        active_ids = [did for did in config.motor_ids if self.ui.ui_sync_checkboxes[did].instate(['selected'])]
        if not self.ensure_torque_enabled(active_ids): 
            return
            
        self.ui.btn_play_seq.config(state=tk.DISABLED, text="▶ Playing...")
        self.ui.seq_listbox.selection_clear(0, tk.END)
        self.player.start(self.sequence_frames)

    # --- CALLBACKS MANDATED BY SEQUENCE PLAYER ---
    def update_sequence_status(self, msg: str):
        self.ui.lbl_seq_status.config(text=msg)

    def highlight_sequence_step(self, idx: int):
        self.ui.seq_listbox.selection_clear(0, tk.END)
        self.ui.seq_listbox.selection_set(idx)
        self.ui.seq_listbox.see(idx)

    def on_sequence_done(self):
        self.ui.btn_play_seq.config(state=tk.NORMAL, text=f"▶ Start ({len(self.sequence_frames)})")
        self.ui.lbl_seq_status.config(text="Status: Ready")
        self.ui.seq_listbox.selection_clear(0, tk.END)

    # --- SOFT-GRIP AND HARDWARE OBSERVERS ---
    def toggle_soft_grip_global(self):
        val = not self.state.get_soft_grip_global()
        self.state.set_soft_grip_global(val)
        self._update_soft_grip_global_button()
        if not val:
            for dxl_id in config.motor_ids:
                self.state.motors[dxl_id].set_soft_grip_frozen(False)

    def _update_soft_grip_global_button(self):
        if self.state.get_soft_grip_global():
            self.ui.btn_soft_grip_global.config(text="🤏 Soft-Grip: ON", style="ToggleOn.TButton")
        else:
            self.ui.btn_soft_grip_global.config(text="🤏 Soft-Grip: OFF", style="Toggle.TButton")

    def on_soft_grip_motor_toggle(self, dxl_id: int):
        motor = self.state.motors[dxl_id]
        motor.set_soft_grip(self.ui.soft_grip_vars[dxl_id].get())
        if not motor.soft_grip_enabled:
            motor.set_soft_grip_frozen(False)

    def get_contact_state(self, dxl_id: int) -> str:
        motor = self.state.motors[dxl_id]
        limit = motor.current_limit
        if limit == 0:
            return "none"
            
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

    def process_soft_grip(self):
        for dxl_id in config.motor_ids:
            motor = self.state.motors[dxl_id]
            is_sg = motor.soft_grip_enabled or self.state.get_soft_grip_global()
            
            if not is_sg or not motor.torque_enabled or motor.is_endless:
                continue
                
            if motor.soft_grip_frozen:
                continue
                
            contact = self.get_contact_state(dxl_id)
            if contact == "contact":
                pos = motor.present_position
                self.hardware.enqueue_command({"type": "goal_position", "motor_id": dxl_id, "value": pos})
                self.ui.slider_vars[dxl_id].set(pos)
                motor.set_soft_grip_frozen(True)

    # --- UI TELEMETRY POLL & QUEUE LOOP ---
    def _update_ui_from_telemetry(self):
        try:
            while True:
                msg = self.hardware.telemetry_queue.get(block=False)
                msg_type = msg.get("type")
                
                if msg_type == "connection_status":
                    connected = msg["connected"]
                    if connected:
                        self.ui.lbl_status.config(text="⬤ ONLINE", foreground=self.ui.ACCENT_GREEN)
                        self.ui.btn_connect.config(text="Disconnect")
                        self.ui.master_slider.config(state=tk.NORMAL)
                        self.ui.master_vel_slider.config(state=tk.NORMAL)
                        self.ui.btn_home.config(state=tk.NORMAL)
                        self.ui.btn_save_pose.config(state=tk.NORMAL)
                        self.ui.btn_play_seq.config(state=tk.NORMAL)
                        
                        for dxl_id in config.motor_ids:
                            self.ui.ui_torque_checkboxes[dxl_id].config(state=tk.NORMAL)
                            self.ui.ui_mode_checkboxes[dxl_id].config(state=tk.NORMAL)
                            self.ui.ui_btn_zero[dxl_id].config(state=tk.NORMAL)
                            self.ui.ui_btn_limit[dxl_id].config(state=tk.NORMAL)
                            self.ui.ui_current_sliders[dxl_id].config(state=tk.NORMAL)
                            self.calculate_reboot_offset_align(dxl_id)
                            
                        # Set default max vel
                        self.on_master_vel_move(100)
                    else:
                        self.ui.lbl_status.config(text="⬤ OFFLINE", foreground=self.ui.ACCENT_RED)
                        self.ui.btn_connect.config(text=f"Connect ({config.port})")
                        self.ui.master_slider.config(state=tk.DISABLED)
                        self.ui.master_vel_slider.config(state=tk.DISABLED)
                        self.ui.btn_home.config(state=tk.DISABLED)
                        self.ui.btn_save_pose.config(state=tk.DISABLED)
                        self.ui.btn_play_seq.config(state=tk.DISABLED)
                        for dxl_id in config.motor_ids:
                            self.ui.ui_torque_checkboxes[dxl_id].config(state=tk.DISABLED)
                            self.ui.ui_mode_checkboxes[dxl_id].config(state=tk.DISABLED)
                            self.ui.ui_btn_zero[dxl_id].config(state=tk.DISABLED)
                            self.ui.ui_btn_limit[dxl_id].config(state=tk.DISABLED)
                            self.ui.ui_current_sliders[dxl_id].config(state=tk.DISABLED)
                        if "error" in msg:
                            messagebox.showerror("Connection Failed", msg["error"])
                            
                elif msg_type == "reboot_success":
                    dxl_id = msg["motor_id"]
                    self.ui.error_labels[dxl_id].config(text="✓", fg=self.ui.ACCENT_GREEN)
                    self.calculate_reboot_offset_align(dxl_id)
                elif msg_type == "reboot_failed":
                    dxl_id = msg["motor_id"]
                    messagebox.showerror("Reboot Failed", f"Motor {dxl_id} reboot failed.")
                    
                elif msg_type == "scan_result":
                    found = msg["found"]
                    if found:
                        ids_str = ", ".join(str(i) for i in found)
                        messagebox.showinfo("Scan Result", f"Found motors:\n\nIDs: {ids_str}\n\n"
                                            f"Currently configured: {config.motor_ids}\n\n"
                                            f"If the IDs do not match, adjust config.json.")
                    else:
                        messagebox.showwarning("Scan Result", "No motors found!\n\n"
                                               "Check cables, power supply, and COM port.")
                                               
                elif msg_type == "telemetry":
                    tel_data = msg["data"]
                    warning_messages = []
                    
                    for dxl_id, data in tel_data.items():
                        motor = self.state.motors[dxl_id]
                        pos = data["pos"]
                        curr = data["current"]
                        temp = data["temp"]
                        err = data["error"]
                        ack = data["ack"]
                        
                        if ack:
                            if not motor.is_endless:
                                self.ui.readout_labels[dxl_id].config(text=f"Pos: {pos}", fg=self.ui.FG_COLOR)
                                if not motor.torque_enabled and motor.calib_zero is not None:
                                    self.ui.slider_vars[dxl_id].set(pos)
                            
                            self.ui.temp_labels[dxl_id].config(text=f"🌡 {temp}°C")
                            if temp > config.temp_warn:
                                self.ui.temp_labels[dxl_id].config(fg=self.ui.ACCENT_RED)
                                warning_messages.append(f"⚠ {motor.name}: {temp}°C!")
                            elif temp > 45:
                                self.ui.temp_labels[dxl_id].config(fg=self.ui.ACCENT_YELLOW)
                            else:
                                self.ui.temp_labels[dxl_id].config(fg=self.ui.ACCENT_GREEN)
                                
                            if err > 0:
                                self.ui.error_labels[dxl_id].config(text="⚠", fg=self.ui.ACCENT_RED)
                                warning_messages.append(f"⚠ {motor.name}: HW-Error {err}")
                            else:
                                self.ui.error_labels[dxl_id].config(text="✓", fg=self.ui.ACCENT_GREEN)
                        else:
                            self.ui.readout_labels[dxl_id].config(text="[ NO ACK ]", fg=self.ui.ACCENT_PEACH)
                            self.ui.temp_labels[dxl_id].config(text="🌡 --°C", fg=self.ui.SUBTEXT)
                            
                    # Update soft-grip frozen/approaching indicator states in UI
                    for dxl_id in config.motor_ids:
                        contact = self.get_contact_state(dxl_id)
                        if contact == "contact":
                            self.ui.contact_labels[dxl_id].config(text="● Contact!", fg=self.ui.ACCENT_GREEN)
                        elif contact == "approaching":
                            self.ui.contact_labels[dxl_id].config(text="● Approaching", fg=self.ui.ACCENT_YELLOW)
                        else:
                            self.ui.contact_labels[dxl_id].config(text="● No Contact", fg=self.ui.SUBTEXT)
                            
                    # Trigger soft grip checks
                    if not self.player.is_playing:
                        self.process_soft_grip()
                        
                    # Trigger warnings layout
                    if warning_messages:
                        self.ui.lbl_warning.config(text="  ".join(warning_messages))
                        self.ui.warning_frame.pack(fill=tk.X, pady=(5, 0))
                    else:
                        self.ui.warning_frame.pack_forget()
                        
                    # Redraw Canvas graph
                    self.ui.draw_graph_throttled()
                    
        except queue.Empty:
            pass
            
        self.root.after(50, self._update_ui_from_telemetry)

    # --- UI INTERACTION HANDLERS ---
    def toggle_connection(self):
        if not self.hardware.is_connected:
            self.hardware.enqueue_command({"type": "connect"})
        else:
            self.hardware.enqueue_command({"type": "disconnect"})

    def auto_scan_motors(self):
        if not self.hardware.is_connected:
            messagebox.showwarning("Not Connected", "Please connect first, then scan.")
            return
        self.hardware.enqueue_command({"type": "scan"})

    def on_torque_check(self, dxl_id: int):
        enable = self.ui.torque_vars[dxl_id].get()
        self.hardware.enqueue_command({"type": "torque", "motor_id": dxl_id, "enable": enable})

    def on_mode_toggle(self, dxl_id: int):
        is_endless = self.ui.mode_vars[dxl_id].get()
        self.hardware.enqueue_command({"type": "mode", "motor_id": dxl_id, "is_endless": is_endless})
        
        motor = self.state.motors[dxl_id]
        if is_endless:
            self.ui.ui_indiv_sliders[dxl_id].config(state=tk.NORMAL, from_=config.velocity_min, to=config.velocity_max)
            self.ui.slider_vars[dxl_id].set(0)
        else:
            if motor.calib_zero is not None and motor.calib_limit is not None:
                min_val = min(motor.calib_zero, motor.calib_limit)
                max_val = max(motor.calib_zero, motor.calib_limit)
                self.ui.ui_indiv_sliders[dxl_id].config(state=tk.NORMAL, from_=min_val, to=max_val)
            else:
                self.ui.ui_indiv_sliders[dxl_id].config(state=tk.DISABLED)

    def on_slider_release(self, event, dxl_id: int):
        motor = self.state.motors[dxl_id]
        if not self.hardware.is_connected or not motor.torque_enabled: 
            return
        if motor.is_endless:
            # Revert speed slider to 0 on release (joystick behaviour)
            self.ui.slider_vars[dxl_id].set(0)
            self.on_indiv_slider_move(dxl_id, 0)
        else:
            # For position drags, record undo command state on mouse release
            old_val = self.slider_start_values.get(dxl_id)
            new_val = self.ui.slider_vars[dxl_id].get()
            if old_val is not None and old_val != new_val:
                self.state.history.push({
                    "type": "slider",
                    "motor_id": dxl_id,
                    "old_value": old_val,
                    "new_value": new_val
                })
                logger.info(f"Command history push: slider ID {dxl_id} moved {old_val} -> {new_val}.")

    def on_current_slider_release(self, event, dxl_id: int):
        if not self.hardware.is_connected: 
            return
        val = self.ui.current_vars[dxl_id].get()
        self.on_current_slider_move(dxl_id, val)

    def on_current_slider_move(self, dxl_id: int, val: Any):
        if not self.hardware.is_connected: 
            return
        target = int(float(val))
        self.ui.current_labels[dxl_id].config(text=str(target))
        self.hardware.enqueue_command({"type": "goal_current", "motor_id": dxl_id, "value": target})

    def on_indiv_slider_move(self, dxl_id: int, val: Any):
        motor = self.state.motors[dxl_id]
        if not self.hardware.is_connected or not motor.torque_enabled or self.player.is_playing: 
            return
            
        motor.set_soft_grip_frozen(False)
        target = int(float(val))
        
        if motor.is_endless:
            self.hardware.enqueue_command({"type": "goal_velocity", "motor_id": dxl_id, "value": target})
            self.ui.readout_labels[dxl_id].config(text=f"Spd: {target}")
        else:
            self.hardware.enqueue_command({"type": "goal_position", "motor_id": dxl_id, "value": target})

    def on_master_slider_move(self, val: Any):
        percent = float(val) / 100.0
        if not self.hardware.is_connected or self.player.is_playing: 
            return
            
        self.ui.lbl_master_pos.config(text=f"{float(val):.1f} %")

        for dxl_id in config.motor_ids:
            motor = self.state.motors[dxl_id]
            if (motor.sync_enabled and not motor.is_endless 
                    and motor.calib_zero is not None and motor.calib_limit is not None):
                target_pos = int(motor.calib_zero + (motor.calib_limit - motor.calib_zero) * percent)
                self.ui.slider_vars[dxl_id].set(target_pos)
                motor.set_soft_grip_frozen(False)
                
                if motor.torque_enabled:
                    self.hardware.enqueue_command({"type": "goal_position", "motor_id": dxl_id, "value": target_pos})

    def on_master_vel_move(self, val: Any):
        if not self.hardware.is_connected: 
            return
        percent = int(float(val))
        self.ui.master_vel_var.set(percent)
        
        if percent >= 100:
            hardware_vel = 0
            self.ui.lbl_master_vel.config(text="Vel: 100 % (Max)")
        else:
            hardware_vel = int((percent / 100.0) * 300)
            if hardware_vel == 0: 
                hardware_vel = 1
            self.ui.lbl_master_vel.config(text=f"Vel: {percent} %")

        self.hardware.enqueue_command({"type": "profile_velocity_all", "value": hardware_vel})

    def toggle_torque_all(self):
        if not self.hardware.is_connected: 
            return
        any_off = any(not self.state.motors[dxl_id].torque_enabled for dxl_id in config.motor_ids)
        self.hardware.enqueue_command({"type": "torque_all", "enable": any_off})
        for dxl_id in config.motor_ids:
            self.ui.torque_vars[dxl_id].set(any_off)

    def ensure_torque_enabled(self, dxl_ids: List[int]) -> bool:
        if not self.hardware.is_connected: 
            return False
            
        off_ids = [did for did in dxl_ids if not self.state.motors[did].torque_enabled]
        if not off_ids:
            return True
            
        names = [self.state.motors[did].name for did in off_ids]
        msg = "Torque is disabled for the following motors:\n\n"
        msg += "\n".join(f"- {n}" for n in names)
        msg += "\n\nDo you want to enable torque for these motors now to execute the movement?"
        
        if messagebox.askyesno("Enable Torque?", msg):
            for did in off_ids:
                self.ui.torque_vars[did].set(True)
                self.hardware.enqueue_command({"type": "torque", "motor_id": did, "enable": True})
            return True
        return False

    def reboot_motor(self, dxl_id: int):
        if not self.hardware.is_connected: 
            return
        if not messagebox.askyesno("Motor Reboot", f"Do you really want to reboot motor ID {dxl_id}?\n(This clears all current hardware errors)"):
            return
        self.hardware.enqueue_command({"type": "reboot", "motor_id": dxl_id})

    def go_home(self):
        if not self.hardware.is_connected: 
            return
        active_ids = [did for did in config.motor_ids if self.ui.ui_sync_checkboxes[did].instate(['selected'])]
        if not self.ensure_torque_enabled(active_ids): 
            return
        
        for dxl_id in config.motor_ids:
            motor = self.state.motors[dxl_id]
            if (not motor.is_endless and motor.torque_enabled
                    and motor.calib_zero is not None and motor.sync_enabled):
                self.ui.slider_vars[dxl_id].set(motor.calib_zero)
                motor.set_soft_grip_frozen(False)
                self.hardware.enqueue_command({"type": "goal_position", "motor_id": dxl_id, "value": motor.calib_zero})
                
        self.ui.master_slider_var.set(0.0)
        self.ui.lbl_master_pos.config(text="0.0 %")

    def emergency_stop(self):
        if not self.hardware.is_connected: 
            return
        self.player.stop()
        self.state.set_soft_grip_global(False)
        self.ui.soft_grip_global.set(False)
        self._update_soft_grip_global_button()
        
        # Immediate direct emergency command
        self.hardware.enqueue_command({"type": "torque_all", "enable": False})
        for dxl_id in config.motor_ids:
            self.state.motors[dxl_id].set_soft_grip(False)
            self.state.motors[dxl_id].set_soft_grip_frozen(False)
            self.ui.torque_vars[dxl_id].set(False)
            
        messagebox.showwarning("EMERGENCY STOP", "Alle Motoren wurden deaktiviert!")

    # --- STORAGE & QUIT HANDLERS ---
    def save_motor_names(self):
        for dxl_id in config.motor_ids:
            self.motor_names[dxl_id] = self.state.motors[dxl_id].name
        save_motor_names(self.motor_names)

    def _save_window_layout(self):
        try:
            geo = self.root.geometry()
            with open("window_layout.json", "w", encoding="utf-8") as f:
                json.dump({"geometry": geo, "dark_mode": self.is_dark_mode}, f)
        except Exception:
            pass

    def _load_window_layout(self):
        try:
            if os.path.exists("window_layout.json"):
                with open("window_layout.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                geo = data.get("geometry")
                if geo:
                    self.root.geometry(geo)
                self.is_dark_mode = data.get("dark_mode", True)
        except Exception:
            pass

    def safe_quit(self):
        if not self.check_unsaved_sequence_changes():
            return
            
        if messagebox.askyesno("Exit", "Do you really want to exit the program?"):
            self._save_window_layout()
            self.hardware.stop()
            self.root.quit()


def main():
    root = tk.Tk()
    app = DynamixelSquadApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
