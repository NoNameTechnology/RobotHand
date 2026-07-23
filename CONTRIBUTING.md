# Contributing to RobotHand

First off, thank you for considering contributing to RobotHand! This project was originally developed for the "Soft!-robotic Hands" project (SoSe 2026), and we welcome contributions from the community to improve and expand its capabilities.

## 🇬🇧 English Speakers Welcome
While the main `README.md` is written in German, the application itself is designed to be accessible to international contributors:
- **UI:** The entire user interface is in English (industry standard). 
- **Tooltips:** Hovering over elements in the UI will show detailed explanations in German to assist students in the local lab.
- **Codebase:** Variables, function names, docstrings, and comments in the source code are entirely in English to facilitate international collaboration.

## 🚀 Quick Start for Contributors

To get the development environment running:

1. **Set up virtual environment & install dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/Mac:
   # source .venv/bin/activate
   
   pip install -r requirements.txt
   ```

2. **Run the app:**
   ```bash
   python motor_control.py
   ```

## 🛠️ How to Contribute

### 1. Reporting Bugs
If you find a bug, please create an Issue in the repository and include:
- Your operating system and Python version.
- A clear description of the bug and steps to reproduce it.
- If it's a hardware issue, note the LED status of the Dynamixel motors (e.g., solid red, flashing red).

### 2. Suggesting Enhancements
We are always open to new features, especially regarding:
- Advanced Sequence generation algorithms or logic
- New predefined grasping templates
- UI/UX improvements
Please open an Issue first to discuss your idea before investing time into writing code.

### 3. Pull Requests
When you are ready to submit code:
1. Fork the repository and create a new branch (`feature/your-feature-name` or `fix/bug-name`).
2. Write clean, readable code.
3. Test your changes locally with the actual hardware connected.
4. Open a Pull Request and describe exactly what changes you made, how you tested them, and why they are necessary.

## 🧠 Architecture Quick-Reference
The application is currently designed as a monolithic Python script (`motor_control.py`) to keep the deployment simple for students. If you are modifying the core components, keep these synchronization rules in mind:

- **Asynchronous Polling Loop:** The hardware telemetry runs on a `Tkinter.after()` loop (`async_telemetry_scanner`). There is no multi-threading.
- **The `serial_mutex` & Watchdog:** Because the U2D2 USB-Adapter and Dynamixel Protocol cannot handle concurrent reads/writes simultaneously, **every** function that communicates with the hardware must acquire the `self.serial_mutex`. A built-in watchdog automatically auto-releases the mutex if it is held for more than 10 consecutive telemetry cycles (~1 second), preventing permanent UI freezes from unhandled exceptions.
- **`try...finally` Blocks:** Always wrap your serial communication logic in a `try...finally` block to ensure `self.serial_mutex = False` is executed even if a serial error or exception is thrown.
- **Rate-Limiting Tkinter Events:** Tkinter UI elements like `<Scale>` fire events rapidly. Never send serial commands directly on every tick. Use debounce mechanisms (like `_pending_slider_targets`, `_slider_send_jobs`, or `_transmit_master_sync`) to throttle serial updates.
- **Pose vs. Sequence Current Limits:** When executing direct pose moves via `go_to_selected_pose()`, always override stored limits with active live GUI slider values so that previous soft-grip operations do not permanently restrict motor current. Sequence playback manages step-specific current limits independently.

Thank you for helping make RobotHand better!
