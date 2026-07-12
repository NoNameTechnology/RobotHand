import json
import os
import logging
from typing import Dict, Optional, Tuple
from config import config

logger = logging.getLogger(__name__)

def calculate_reboot_offset(raw_pos: int, calib_zero: int) -> int:
    """Calculates the reboot offset to align raw motor position closest to calibration zero."""
    N = round((calib_zero - raw_pos) / 4096.0)
    return int(N * 4096)

def load_calibration(file_path="calibration.json") -> Tuple[Dict[int, Optional[int]], Dict[int, Optional[int]]]:
    calib_zero = {dxl_id: None for dxl_id in config.motor_ids}
    calib_limit = {dxl_id: None for dxl_id in config.motor_ids}
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded_zero = {int(k): v for k, v in data.get("calib_zero", {}).items()}
            loaded_limit = {int(k): v for k, v in data.get("calib_limit", {}).items()}
            
            for dxl_id in config.motor_ids:
                if dxl_id in loaded_zero:
                    calib_zero[dxl_id] = loaded_zero[dxl_id]
                if dxl_id in loaded_limit:
                    calib_limit[dxl_id] = loaded_limit[dxl_id]
            logger.info("Calibration loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading calibration: {e}")
            
    return calib_zero, calib_limit

def save_calibration(calib_zero: Dict[int, Optional[int]], calib_limit: Dict[int, Optional[int]], file_path="calibration.json") -> bool:
    data = {
        "calib_zero": calib_zero,
        "calib_limit": calib_limit
    }
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Calibration saved successfully.")
        return True
    except Exception as e:
        logger.error(f"Error saving calibration: {e}")
        return False

def load_motor_names(file_path="motor_names.json") -> Dict[int, str]:
    motor_names = {dxl_id: f"Motor {dxl_id}" for dxl_id in config.motor_ids}
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for dxl_id in config.motor_ids:
                key = str(dxl_id)
                if key in data:
                    motor_names[dxl_id] = data[key]
            logger.info("Motor names loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading motor names: {e}")
    return motor_names

def save_motor_names(motor_names: Dict[int, str], file_path="motor_names.json") -> bool:
    data = {str(k): v for k, v in motor_names.items()}
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Motor names saved successfully.")
        return True
    except Exception as e:
        logger.error(f"Error saving motor names: {e}")
        return False
