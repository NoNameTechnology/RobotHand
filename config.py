import json
import os

# EEPROM / RAM Addresses (XL330-M288)
ADDR_OPERATING_MODE = 11     
ADDR_TORQUE_ENABLE = 64
ADDR_HARDWARE_ERROR_STATUS = 70
ADDR_GOAL_CURRENT = 102
ADDR_GOAL_VELOCITY = 104     
ADDR_PROFILE_VELOCITY = 112  
ADDR_GOAL_POSITION = 116
ADDR_PRESENT_CURRENT = 126
ADDR_PRESENT_POSITION = 132
ADDR_PRESENT_TEMPERATURE = 146

# Operating Modes
OP_MODE_VELOCITY = 1      # Wheel Mode (Endlos)
OP_MODE_POSITION = 3      # Joint Mode (Standard, 1 Umdrehung)
OP_MODE_CURRENT_BASED_POSITION = 5  # Soft-Robotic Mode (Position + Current Limit)

DEFAULT_GRASP_TYPES = ["Edge-Grasp", "Top-Grasp", "Wall-Grasp"]

class Config:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.load()

    def load(self):
        if not os.path.exists(self.config_path):
            # Fallback defaults if config.json is missing
            self.port = "COM10"
            self.baudrate = 115200
            self.timeout_ms = 500
            self.motor_ids = [0, 1, 2, 3, 4]
            self.motor_count = 5
            self.velocity_min = -300
            self.velocity_max = 300
            self.current_max = 1750
            self.temp_warn = 55
            self.temp_critical = 65
            self.avg_window = 5
            self.threshold_pct = 0.8
            self.spike_threshold_ma = 100
            self.graph_refresh_hz = 10
            self.telemetry_poll_hz = 20
            self.window_default_geometry = "1250x1080"
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        hw = data.get("hardware", {})
        self.port = hw.get("port", "COM10")
        self.baudrate = hw.get("baudrate", 115200)
        self.timeout_ms = hw.get("timeout_ms", 500)

        motors = data.get("motors", {})
        self.motor_ids = motors.get("ids", [0, 1, 2, 3, 4])
        self.motor_count = motors.get("count", 5)

        limits = data.get("limits", {})
        self.velocity_min = limits.get("velocity_min", -300)
        self.velocity_max = limits.get("velocity_max", 300)
        self.current_max = limits.get("current_max", 1750)
        self.temp_warn = limits.get("temp_warn", 55)
        self.temp_critical = limits.get("temp_critical", 65)

        cd = data.get("contact_detection", {})
        self.avg_window = cd.get("avg_window", 5)
        self.threshold_pct = cd.get("threshold_pct", 0.8)
        self.spike_threshold_ma = cd.get("spike_threshold_ma", 100)

        ui = data.get("ui", {})
        self.graph_refresh_hz = ui.get("graph_refresh_hz", 10)
        self.telemetry_poll_hz = ui.get("telemetry_poll_hz", 20)
        self.window_default_geometry = ui.get("window_default_geometry", "1250x1080")

# Global configuration instance
config = Config()
