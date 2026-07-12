import queue
import threading
import time
import logging
from typing import Dict, List, Optional, Any

# pyrefly: ignore [missing-import]
from dynamixel_sdk import PortHandler, PacketHandler, COMM_SUCCESS, GroupSyncRead  # type: ignore
from config import (
    config, ADDR_OPERATING_MODE, ADDR_TORQUE_ENABLE, ADDR_HARDWARE_ERROR_STATUS,
    ADDR_GOAL_CURRENT, ADDR_GOAL_VELOCITY, ADDR_PROFILE_VELOCITY, ADDR_GOAL_POSITION,
    ADDR_PRESENT_CURRENT, ADDR_PRESENT_POSITION, ADDR_PRESENT_TEMPERATURE,
    OP_MODE_VELOCITY, OP_MODE_CURRENT_BASED_POSITION
)
from models import RobotState

logger = logging.getLogger(__name__)

class HardwareManager:
    def __init__(self, robot_state: RobotState):
        self.state = robot_state
        self.cmd_queue = queue.Queue()
        self.telemetry_queue = queue.Queue()
        
        self.portHandler = PortHandler(config.port)
        self.packetHandler = PacketHandler(2.0)
        
        self.is_connected = False
        self.running = False
        self.worker_thread: Optional[threading.Thread] = None
        
        self.groupSyncReadPosCurr = None
        self.groupSyncReadTemp = None
        self.groupSyncReadError = None

    def start(self):
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        logger.info("Hardware manager worker thread started.")

    def stop(self):
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=1.0)
        self.disconnect_port()
        logger.info("Hardware manager stopped.")

    def enqueue_command(self, cmd: dict):
        self.cmd_queue.put(cmd)

    def connect_port(self) -> bool:
        if self.is_connected:
            return True
        try:
            logger.info(f"Opening port {config.port}...")
            if not self.portHandler.openPort():
                raise ConnectionError("Port open failed.")
            logger.info(f"Setting baudrate to {config.baudrate}...")
            if not self.portHandler.setBaudRate(config.baudrate):
                raise ConnectionError("Baudrate negotiation failed.")
            
            # Setup GroupSyncReads
            self.groupSyncReadPosCurr = GroupSyncRead(self.portHandler, self.packetHandler, ADDR_PRESENT_CURRENT, 10)
            self.groupSyncReadTemp = GroupSyncRead(self.portHandler, self.packetHandler, ADDR_PRESENT_TEMPERATURE, 1)
            self.groupSyncReadError = GroupSyncRead(self.portHandler, self.packetHandler, ADDR_HARDWARE_ERROR_STATUS, 1)
            
            for dxl_id in config.motor_ids:
                self.groupSyncReadPosCurr.addParam(dxl_id)
                self.groupSyncReadTemp.addParam(dxl_id)
                self.groupSyncReadError.addParam(dxl_id)
                
            self.is_connected = True
            logger.info("Connection to Dynamixel port established.")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    def disconnect_port(self):
        if not self.is_connected:
            return
        
        # Shut down torque and zero speeds for safety before disconnect
        for dxl_id in config.motor_ids:
            motor = self.state.motors[dxl_id]
            if motor.is_endless:
                self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_VELOCITY, 0)
            self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
            motor.set_torque(False)
            
        self.portHandler.closePort()
        self.is_connected = False
        logger.info("Disconnected port and torque disabled on all motors.")

    def _worker(self):
        while self.running:
            # 1. Drain command queue and execute as a batch
            batch = []
            try:
                while True:
                    cmd = self.cmd_queue.get(block=False)
                    batch.append(cmd)
            except queue.Empty:
                pass
            
            if batch:
                self._execute_batch(batch)
            
            # 2. Telemetry polling if connected
            if self.is_connected:
                self._poll_telemetry()
                
            time.sleep(1.0 / config.telemetry_poll_hz)

    def _execute_batch(self, batch: List[dict]):
        for cmd in batch:
            cmd_type = cmd.get("type")
            try:
                if cmd_type == "connect":
                    success = self.connect_port()
                    if success:
                        # Configure initial mode based on RobotState
                        for dxl_id in config.motor_ids:
                            motor = self.state.motors[dxl_id]
                            # Turn torque off to configure modes
                            self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
                            mode_val = OP_MODE_VELOCITY if motor.is_endless else OP_MODE_CURRENT_BASED_POSITION
                            self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_OPERATING_MODE, mode_val)
                            self.packetHandler.write2ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_CURRENT, motor.current_limit)
                        self.telemetry_queue.put({"type": "connection_status", "connected": True})
                    else:
                        self.telemetry_queue.put({"type": "connection_status", "connected": False, "error": "Could not open port or set baudrate."})
                
                elif cmd_type == "disconnect":
                    self.disconnect_port()
                    self.telemetry_queue.put({"type": "connection_status", "connected": False})
                    
                elif cmd_type == "torque":
                    dxl_id = cmd["motor_id"]
                    enable = 1 if cmd["enable"] else 0
                    self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, enable)
                    self.state.motors[dxl_id].set_torque(cmd["enable"])
                    
                elif cmd_type == "torque_all":
                    enable = cmd["enable"]
                    for dxl_id in config.motor_ids:
                        self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 1 if enable else 0)
                        self.state.motors[dxl_id].set_torque(enable)
                        
                elif cmd_type == "mode":
                    dxl_id = cmd["motor_id"]
                    is_endless = cmd["is_endless"]
                    # Torque must be disabled to change mode
                    was_torque_on = self.state.motors[dxl_id].torque_enabled
                    if was_torque_on:
                        self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
                    
                    mode_val = OP_MODE_VELOCITY if is_endless else OP_MODE_CURRENT_BASED_POSITION
                    self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_OPERATING_MODE, mode_val)
                    self.state.motors[dxl_id].set_mode(is_endless)
                    
                    if was_torque_on:
                        self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 1)
                        
                elif cmd_type == "goal_position":
                    dxl_id = cmd["motor_id"]
                    pos = cmd["value"]
                    offset = self.state.motors[dxl_id].reboot_offset
                    raw_pos = int(pos - offset)
                    self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_POSITION, raw_pos & 0xFFFFFFFF)
                    self.state.motors[dxl_id].set_goal_position(pos)
                    
                elif cmd_type == "goal_velocity":
                    dxl_id = cmd["motor_id"]
                    vel = cmd["value"]
                    self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_VELOCITY, vel & 0xFFFFFFFF)
                    
                elif cmd_type == "goal_current":
                    dxl_id = cmd["motor_id"]
                    curr = cmd["value"]
                    self.packetHandler.write2ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_CURRENT, curr)
                    self.state.motors[dxl_id].set_current_limit(curr)
                    
                elif cmd_type == "profile_velocity":
                    dxl_id = cmd["motor_id"]
                    vel = cmd["value"]
                    self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_PROFILE_VELOCITY, vel)
                    
                elif cmd_type == "profile_velocity_all":
                    vel = cmd["value"]
                    for dxl_id in config.motor_ids:
                        self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_PROFILE_VELOCITY, vel)
                        
                elif cmd_type == "reboot":
                    dxl_id = cmd["motor_id"]
                    self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
                    self.state.motors[dxl_id].set_torque(False)
                    res, err = self.packetHandler.reboot(self.portHandler, dxl_id)
                    if res == COMM_SUCCESS:
                        logger.info(f"Motor {dxl_id} rebooted successfully.")
                        time.sleep(0.5)
                        # Restore settings
                        motor = self.state.motors[dxl_id]
                        mode_val = OP_MODE_VELOCITY if motor.is_endless else OP_MODE_CURRENT_BASED_POSITION
                        self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_OPERATING_MODE, mode_val)
                        self.packetHandler.write2ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_CURRENT, motor.current_limit)
                        self.telemetry_queue.put({"type": "reboot_success", "motor_id": dxl_id})
                    else:
                        logger.error(f"Reboot motor {dxl_id} failed: {err}")
                        self.telemetry_queue.put({"type": "reboot_failed", "motor_id": dxl_id})
                        
                elif cmd_type == "scan":
                    found_ids = []
                    for test_id in range(21):
                        model, res, err = self.packetHandler.ping(self.portHandler, test_id)
                        if res == COMM_SUCCESS:
                            found_ids.append(test_id)
                    self.telemetry_queue.put({"type": "scan_result", "found": found_ids})
                    
            except Exception as e:
                logger.error(f"Error executing command {cmd_type}: {e}")

    def _poll_telemetry(self):
        telemetry_update = {}
        
        # 1. Present Position + Current (SyncRead)
        res_pos_curr = self.groupSyncReadPosCurr.txRxPacket()
        
        # 2. Present Temperature (SyncRead)
        res_temp = self.groupSyncReadTemp.txRxPacket()
        
        # 3. Hardware Error Status (SyncRead)
        res_err = self.groupSyncReadError.txRxPacket()
        
        for dxl_id in config.motor_ids:
            motor = self.state.motors[dxl_id]
            offset = motor.reboot_offset
            
            pos = 0
            if res_pos_curr == COMM_SUCCESS:
                raw_pos = self.groupSyncReadPosCurr.getData(dxl_id, ADDR_PRESENT_POSITION, 4)
                if raw_pos > 2147483647:
                    raw_pos -= 4294967296
                pos = raw_pos + offset
                motor.set_position(pos)
            else:
                pos = motor.present_position # fall back to last known
                
            curr = 0
            if res_pos_curr == COMM_SUCCESS:
                raw_curr = self.groupSyncReadPosCurr.getData(dxl_id, ADDR_PRESENT_CURRENT, 2)
                if raw_curr > 32767:
                    raw_curr -= 65536
                curr = raw_curr
            
            temp = 0
            if res_temp == COMM_SUCCESS:
                temp = self.groupSyncReadTemp.getData(dxl_id, ADDR_PRESENT_TEMPERATURE, 1)
                
            hw_err = 0
            if res_err == COMM_SUCCESS:
                hw_err = self.groupSyncReadError.getData(dxl_id, ADDR_HARDWARE_ERROR_STATUS, 1)
                if hw_err > 0 and motor.torque_enabled:
                    # Motor automatically disables torque on HW error
                    motor.set_torque(False)
            
            # Apply update to state
            motor.update_telemetry(pos, curr, temp, hw_err)
            
            telemetry_update[dxl_id] = {
                "pos": pos,
                "current": curr,
                "temp": temp,
                "error": hw_err,
                "ack": (res_pos_curr == COMM_SUCCESS)
            }
            
        self.telemetry_queue.put({"type": "telemetry", "data": telemetry_update})
