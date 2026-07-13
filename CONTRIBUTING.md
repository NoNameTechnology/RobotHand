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

2. **Run tests:** 
   Before making changes, ensure the base application passes all unit tests. This ensures your local environment is set up correctly:
   ```bash
   python -m unittest test_app.py
   ```

3. **Run the app:**
   ```bash
   python main.py
   ```

## 🛠️ How to Contribute

### 1. Reporting Bugs
If you find a bug, please create an Issue in the repository and include:
- Your operating system and Python version.
- The `config.json` settings (especially baudrate and port).
- A clear description of the bug and steps to reproduce it.
- If it's a hardware issue, note the LED status of the Dynamixel motors.

### 2. Suggesting Enhancements
We are always open to new features, especially regarding:
- Advanced Sequence generation algorithms or logic
- New predefined grasping templates
- UI/UX improvements
Please open an Issue first to discuss your idea before investing time into writing code.

### 3. Pull Requests
When you are ready to submit code:
1. Fork the repository and create a new branch (`feature/your-feature-name` or `fix/bug-name`).
2. Write clean, readable code. **Crucial:** Maintain the MVC architecture. Keep UI logic out of `hardware.py` and hardware polling out of `ui.py`!
3. Add or update unit tests in `test_app.py` for any new logic you introduce.
4. Run the full test suite locally.
5. Open a Pull Request and describe exactly what changes you made, how you tested them, and why they are necessary.

## 🧠 Architecture Quick-Reference
If you are modifying the core components, keep these boundaries in mind:
- **`models.py`**: Thread-safe state classes. Do not put execution logic here, just data storage and synchronization locks.
- **`ui.py`**: Tkinter frontend. Only reads from the thread-safe `state` and sends user commands via defined callbacks.
- **`hardware.py`**: Runs in a dedicated background thread. Reads/writes to the serial bus asynchronously and pushes sensor data back to the `state`.
- **`main.py`**: The central controller that initializes queues, threads, and binds the UI to the Hardware manager.

Thank you for helping make RobotHand better!
