import time
import json
import os
import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
from collections import deque
# pyrefly: ignore [missing-import]
from dynamixel_sdk import PortHandler, PacketHandler, COMM_SUCCESS, GroupSyncWrite, GroupSyncRead # Official Robotis SDK

COM_PORT = "COM10"
BAUDRATE = 115200
MOTOR_IDS = [0, 1, 2, 3, 4]

# EEPROM / RAM Addresses (XL330-M288)
ADDR_OPERATING_MODE = 11     
ADDR_TORQUE_ENABLE = 64
ADDR_HARDWARE_ERROR_STATUS = 70
ADDR_GOAL_CURRENT = 102
ADDR_GOAL_VELOCITY = 104     
ADDR_PROFILE_VELOCITY = 112  
ADDR_PROFILE_ACCELERATION = 108
ADDR_GOAL_POSITION = 116
ADDR_PRESENT_CURRENT = 126
ADDR_PRESENT_POSITION = 132
ADDR_PRESENT_TEMPERATURE = 146

# Operating Modes
OP_MODE_VELOCITY = 1      # Wheel Mode (Endlos)
OP_MODE_POSITION = 3      # Joint Mode (Standard, 1 Umdrehung)
OP_MODE_CURRENT_BASED_POSITION = 5  # Soft-Robotic Mode (Position + Current Limit)

# Limits & Defaults
MIN_VEL_LIMIT = -300  # Rückwärts max
MAX_VEL_LIMIT = 300   # Vorwärts max
SEQUENCE_DELAY_MS = 1000 

# Contact Detection Settings
CONTACT_AVG_WINDOW = 5       # Gleitender Durchschnitt über N Werte
CONTACT_THRESHOLD_PCT = 0.8  # 80% des Limits = Kontakt
CONTACT_SPIKE_THRESHOLD = 100  # mA Änderung über 3 Ticks = Spike-Erkennung

# Temperature Thresholds (°C)
TEMP_OK = 45
TEMP_WARN = 55

# Default Grasp Types (immer verfügbar)
DEFAULT_GRASP_TYPES = ["Edge-Grasp", "Top-Grasp", "Wall-Grasp"]


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 20
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                         background="#333333", foreground="#ffffff", relief='solid', borderwidth=1,
                         font=("Segoe UI", 9, "normal"))
        label.pack(ipadx=4, ipady=4)

    def leave(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

def create_tooltip(widget, text):
    ToolTip(widget, text)


class DynamixelSquadApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Dynamixel XL330-M288 Hand-Controller ({COM_PORT} @ {BAUDRATE})")
        self.root.geometry("1250x1080")
        self.root.minsize(1100, 900)
        
        # Theme state
        self.is_dark_mode = True

        self.portHandler = PortHandler(COM_PORT)
        self.packetHandler = PacketHandler(2.0)
        
        self.is_connected = False
        self.serial_mutex = False
        self._mutex_busy_cycles = 0  # Watchdog: counts consecutive telemetry ticks where the bus lock was held
        self.last_master_val = 0.0
        # Slider callbacks can arrive much faster than a Dynamixel bus can
        # acknowledge position writes.  Keep only the newest request per motor
        # and transmit it at a bounded rate instead of flooding the bus.
        self._pending_slider_targets = {}
        self._slider_send_jobs = {}
        self._last_slider_targets = {}
        self._slider_send_interval_ms = 25

        # State Variables
        self.torque_vars = {}
        self.mode_vars = {} 
        self.sync_vars = {} 
        self.slider_vars = {}
        self.current_vars = {}
        self.graph_history = {dxl_id: deque([0]*50, maxlen=50) for dxl_id in MOTOR_IDS}
        self.limit_history = {dxl_id: deque([600]*50, maxlen=50) for dxl_id in MOTOR_IDS}
        self.present_positions = {dxl_id: 0 for dxl_id in MOTOR_IDS}
        
        # Group Sync Read objects
        self.sync_read_pos = GroupSyncRead(self.portHandler, self.packetHandler, ADDR_PRESENT_POSITION, 4)
        self.sync_read_curr = GroupSyncRead(self.portHandler, self.packetHandler, ADDR_PRESENT_CURRENT, 2)
        self.sync_read_temp = GroupSyncRead(self.portHandler, self.packetHandler, ADDR_PRESENT_TEMPERATURE, 1)
        self.sync_read_err = GroupSyncRead(self.portHandler, self.packetHandler, ADDR_HARDWARE_ERROR_STATUS, 1)
        
        for dxl_id in MOTOR_IDS:
            self.sync_read_pos.addParam(dxl_id)
            self.sync_read_curr.addParam(dxl_id)
            self.sync_read_temp.addParam(dxl_id)
            self.sync_read_err.addParam(dxl_id)
            
        # Group Sync Write objects
        self.sync_write_pos = GroupSyncWrite(self.portHandler, self.packetHandler, ADDR_GOAL_POSITION, 4)
        self.sync_write_current = GroupSyncWrite(self.portHandler, self.packetHandler, ADDR_GOAL_CURRENT, 2)
        self.sync_write_profile_vel = GroupSyncWrite(self.portHandler, self.packetHandler, ADDR_PROFILE_VELOCITY, 4)
        
        # Calibration Limits
        self.calib_zero = {dxl_id: None for dxl_id in MOTOR_IDS}
        self.calib_limit = {dxl_id: None for dxl_id in MOTOR_IDS}
        self.last_deleted_zero = {}
        self.last_deleted_limit = {}
  
        # Motor Names (Feature 9)
        self.motor_names = {dxl_id: f"Motor {dxl_id}" for dxl_id in MOTOR_IDS}
        
        self.motor_colors = ["#f38ba8", "#a6e3a1", "#89b4fa", "#f9e2af", "#cba6f7"]
        
        # Soft-Grip (Feature 6)
        self.soft_grip_global = tk.BooleanVar(value=False)
        self.soft_grip_vars = {}
        self.soft_grip_frozen = {dxl_id: False for dxl_id in MOTOR_IDS}
        
        # Contact Detection (Feature 3)
        self.contact_states = {dxl_id: "none" for dxl_id in MOTOR_IDS}
  
        # UI Elements
        self.ui_torque_checkboxes = {}
        self.motor_cards = {}
        self.reboot_offsets = {dxl_id: 0 for dxl_id in MOTOR_IDS}
        self.seq_default_sg_vars = {dxl_id: tk.BooleanVar(value=False) for dxl_id in MOTOR_IDS}
        self.seq_default_ma_vars = {dxl_id: tk.IntVar(value=600) for dxl_id in MOTOR_IDS}
        self.seq_unsaved_changes = False
        self.ui_mode_checkboxes = {} 
        self.ui_sync_checkboxes = {}
        self.ui_soft_grip_checkboxes = {}
        self.ui_indiv_sliders = {}
        self.ui_current_sliders = {}
        self.readout_labels = {}
        self.current_labels = {}
        self.ui_btn_zero = {}
        self.ui_btn_limit = {}
        self.graph_lines = {}
        self.graph_indicators = {}
        
        # Motor Name UI (Feature 9)
        self.motor_name_frames = {}
        self.motor_name_labels = {}
        
        # Status UI (Feature 4)
        self.contact_labels = {}
        self.temp_labels = {}
        self.error_labels = {}
        
        self.master_slider_var = tk.DoubleVar(value=0.0)
        self.master_vel_var = tk.IntVar(value=100)
        
        self.sequence_frames = [] 
        self.saved_sequences = {}
        self.saved_poses = {}
        self.is_playing = False

        self._build_ui()
        self.load_motor_names()
        self.load_calibration()
        self.load_sequences_from_file()
        self.load_poses_from_file()
        self._load_window_geometry()
        self.root.protocol("WM_DELETE_WINDOW", self.safe_quit)

    def _build_ui(self):
        # --- THEME & STYLING ---
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except:
            pass
            
        self.BG_COLOR = "#1e1e2e"
        self.FG_COLOR = "#cdd6f4"
        self.ACCENT_BLUE = "#89b4fa"
        self.ACCENT_GREEN = "#a6e3a1"
        self.ACCENT_RED = "#f38ba8"
        self.ACCENT_YELLOW = "#f9e2af"
        self.ACCENT_PEACH = "#fab387"
        self.PANEL_BG = "#313244"
        self.SURFACE_BG = "#45475a"
        self.SUBTEXT = "#a6adc8"
        
        self.root.configure(bg=self.BG_COLOR)
        
        self.style.configure(".", background=self.BG_COLOR, foreground=self.FG_COLOR, font=("Segoe UI", 10))
        self.style.configure("TLabel", background=self.BG_COLOR, foreground=self.FG_COLOR)
        self.style.configure("Panel.TLabel", background=self.PANEL_BG, foreground=self.FG_COLOR)
        self.style.configure("Panel.TFrame", background=self.PANEL_BG)
        self.style.configure("Surface.TFrame", background=self.SURFACE_BG)
        self.style.configure("TFrame", background=self.BG_COLOR)
        
        self.style.configure("TLabelframe", background=self.PANEL_BG, foreground=self.ACCENT_BLUE,
                             borderwidth=1, font=("Segoe UI", 10, "bold"))
        self.style.configure("TLabelframe.Label", background=self.PANEL_BG, foreground=self.ACCENT_BLUE)
        
        self.style.configure("TButton", background=self.SURFACE_BG, foreground=self.FG_COLOR,
                             borderwidth=0, padding=4, font=("Segoe UI", 9))
        self.style.map("TButton", background=[("active", self.ACCENT_BLUE)],
                       foreground=[("active", "#1e1e2e")])
        
        self.style.configure("Primary.TButton", background=self.ACCENT_BLUE, foreground="#1e1e2e",
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Primary.TButton", background=[("active", "#74c7ec")])
        
        self.style.configure("Danger.TButton", background=self.ACCENT_RED, foreground="#1e1e2e",
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Danger.TButton", background=[("active", "#eba0ac")])
        
        self.style.configure("Success.TButton", background=self.ACCENT_GREEN, foreground="#1e1e2e",
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Success.TButton", background=[("active", "#94e2d5")])
        
        self.style.configure("Toggle.TButton", background=self.SURFACE_BG, foreground=self.SUBTEXT,
                             font=("Segoe UI", 9))
        self.style.configure("ToggleOn.TButton", background=self.ACCENT_GREEN, foreground="#1e1e2e",
                             font=("Segoe UI", 9, "bold"))
        
        self.style.configure("TCheckbutton", background=self.BG_COLOR, foreground=self.FG_COLOR)
        self.style.map("TCheckbutton", background=[("active", self.BG_COLOR)],
                       indicatorcolor=[("selected", self.ACCENT_BLUE)])
        self.style.configure("Panel.TCheckbutton", background=self.PANEL_BG, foreground=self.FG_COLOR)
        self.style.map("Panel.TCheckbutton", background=[("active", self.PANEL_BG)],
                       indicatorcolor=[("selected", self.ACCENT_BLUE)])
        self.style.configure("Horizontal.TScale", background=self.BG_COLOR, troughcolor=self.SURFACE_BG)
        self.style.configure("Panel.Horizontal.TScale", background=self.PANEL_BG, troughcolor=self.SURFACE_BG)
        
        # Entry & Combobox styles (to fix unreadable text)
        self.style.configure("TEntry", fieldbackground=self.SURFACE_BG, foreground=self.FG_COLOR, insertcolor=self.FG_COLOR)
        self.style.map("TEntry", selectbackground=[("focus", self.ACCENT_BLUE)], selectforeground=[("focus", "#1e1e2e")])
        self.style.configure("TCombobox", fieldbackground=self.SURFACE_BG, foreground=self.FG_COLOR, background=self.SURFACE_BG)
        self.style.map("TCombobox", fieldbackground=[("readonly", self.SURFACE_BG)], 
                       selectbackground=[("readonly", self.ACCENT_BLUE)], selectforeground=[("readonly", "#1e1e2e")])
        
        # --- MAIN HORIZONTAL SPLIT (2/3 left, 1/3 right) ---
        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self.BG_COLOR,
                               sashwidth=4, sashrelief=tk.FLAT, bd=0)
        self.paned.pack(fill=tk.BOTH, expand=True)
        
        # ===== LEFT PANEL (2/3) — Scrollable =====
        self.left_outer = tk.Frame(self.paned, bg=self.BG_COLOR)
        
        self.canvas_left = tk.Canvas(self.left_outer, bg=self.BG_COLOR, highlightthickness=0)
        self.canvas_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        left_frame = ttk.Frame(self.canvas_left, padding="10")
        left_canvas_window = self.canvas_left.create_window((0, 0), window=left_frame, anchor="nw")
        
        def on_left_configure(event):
            self.canvas_left.configure(scrollregion=self.canvas_left.bbox("all"))
        left_frame.bind("<Configure>", on_left_configure)
        
        def on_left_canvas_configure(event):
            self.canvas_left.itemconfig(left_canvas_window, width=event.width)
        self.canvas_left.bind("<Configure>", on_left_canvas_configure)
        
        def on_mousewheel(event):
            bbox = self.canvas_left.bbox("all")
            if bbox and bbox[3] > self.canvas_left.winfo_height():
                self.canvas_left.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas_left.bind_all("<MouseWheel>", on_mousewheel)
        
        # ===== RIGHT PANEL (1/3) =====
        self.right_frame = tk.Frame(self.paned, bg=self.BG_COLOR, padx=5, pady=10)

        self.paned.add(self.left_outer, minsize=500, stretch="always")
        self.paned.add(self.right_frame, minsize=300, stretch="always")
        
        # Set initial sash position after window is mapped
        def set_sash_position(event=None):
            total_width = self.root.winfo_width()
            if total_width > 100:
                self.paned.sash_place(0, int(total_width * 0.66), 0)
                self.root.unbind("<Map>")
        self.root.bind("<Map>", set_sash_position)

        # =====================================================
        # LEFT SIDE
        # =====================================================

        # ----- 1. STATUS PANEL -----
        conn_frame = ttk.LabelFrame(left_frame, text=" System Status ", padding="10")
        conn_frame.pack(fill=tk.X, pady=(0, 8))

        status_row1 = ttk.Frame(conn_frame)
        status_row1.pack(fill=tk.X)

        self.btn_connect = ttk.Button(status_row1, text=f"Connect ({COM_PORT})",
                                      command=self.toggle_connection, style="Primary.TButton")
        self.btn_connect.pack(side=tk.LEFT, padx=5)
        create_tooltip(self.btn_connect, "Verbindet sich mit den Motoren auf dem gewählten COM-Port.")

        self.lbl_status = ttk.Label(status_row1, text="⬤ OFFLINE", foreground=self.ACCENT_RED,
                                    font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(side=tk.LEFT, padx=15)
        
        # Global Soft-Grip Toggle
        self.btn_soft_grip_global = ttk.Button(status_row1, text="🤏 Soft-Grip: AUS",
                                                command=self.toggle_soft_grip_global, style="Toggle.TButton")
        self.btn_soft_grip_global.pack(side=tk.LEFT, padx=15)
        create_tooltip(self.btn_soft_grip_global,
                       "Aktiviert Soft-Grip für ALLE Motoren.\nBei Kontakt hält der Motor automatisch an.")
        
        self.btn_quit = ttk.Button(status_row1, text="❌ Beenden",
                                   command=self.safe_quit, style="Danger.TButton")
        self.btn_quit.pack(side=tk.RIGHT, padx=5)
        create_tooltip(self.btn_quit, "Schließt das Programm sicher und schaltet Motoren ab.")

        self.btn_estop = ttk.Button(status_row1, text="🚨 EMERGENCY STOP 🚨",
                                    command=self.emergency_stop, style="Danger.TButton")
        self.btn_estop.pack(side=tk.RIGHT, padx=5)
        create_tooltip(self.btn_estop, "Schaltet sofort den Strom für alle Motoren ab (Torque OFF).")
        
        self.btn_torque_all = ttk.Button(status_row1, text="Torque ALL",
                                         command=self.toggle_torque_all, style="Primary.TButton")
        self.btn_torque_all.pack(side=tk.RIGHT, padx=15)
        create_tooltip(self.btn_torque_all, "Schaltet das Drehmoment aller Motoren an oder aus.")
        
        # Second status row for utility buttons
        status_row2 = ttk.Frame(conn_frame)
        status_row2.pack(fill=tk.X, pady=(4, 0))
        
        self.btn_scan = ttk.Button(status_row2, text="Scan Motoren",
                                   command=self.auto_scan_motors, style="TButton")
        self.btn_scan.pack(side=tk.LEFT, padx=5)
        create_tooltip(self.btn_scan, "Scannt den Bus nach vorhandenen Motoren (ID 0-20).")

        self.btn_theme = ttk.Button(status_row2, text="Light Mode",
                                    command=self.toggle_theme, style="TButton")
        self.btn_theme.pack(side=tk.LEFT, padx=5)
        create_tooltip(self.btn_theme, "Wechselt zwischen Dark Mode und Light Mode.")
        
        # Warning Banner (hidden by default)
        self.warning_frame = tk.Frame(conn_frame, bg=self.ACCENT_YELLOW, height=0)
        self.warning_frame.pack(fill=tk.X, pady=(5, 0))
        self.warning_frame.pack_forget()
        
        self.lbl_warning = tk.Label(self.warning_frame, text="", bg=self.ACCENT_YELLOW,
                                    fg="#1e1e2e", font=("Segoe UI", 9, "bold"), anchor="w")
        self.lbl_warning.pack(fill=tk.X, padx=10, pady=4)



        master_frame = ttk.LabelFrame(left_frame, text=" Master Broadcast (Wirkt auf 'Sync' Motoren) ",
                                      padding="10")
        master_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(master_frame, text="Master Position (%):").grid(row=0, column=0, sticky="w", padx=5)
        
        self.master_slider = ttk.Scale(
            master_frame, from_=-100, to=100, variable=self.master_slider_var,
            orient="horizontal", command=self.on_master_slider_move, state=tk.DISABLED
        )
        self.master_slider.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        self.master_slider.bind("<ButtonRelease-1>", self.on_master_slider_release)
        create_tooltip(self.master_slider, "Steuert gleichzeitig alle Motoren, bei denen 'Sync' aktiviert ist.")
        master_frame.columnconfigure(1, weight=1)
        
        self.lbl_master_pos = ttk.Label(master_frame, text="0.0 %", width=8)
        self.lbl_master_pos.grid(row=0, column=2, sticky="w", padx=5)
        create_tooltip(self.lbl_master_pos, "Aktueller Prozentwert des Master-Schiebereglers.")
 
        ttk.Label(master_frame, text="Master Profile Vel (%):").grid(row=1, column=0, sticky="w", padx=5)
        self.master_vel_slider = ttk.Scale(
            master_frame, from_=1, to=100, variable=self.master_vel_var,
            orient="horizontal", command=self.on_master_vel_move, state=tk.DISABLED
        )
        self.master_vel_slider.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        create_tooltip(self.master_vel_slider, "Regelt die Geschwindigkeit aller synchronisierten Bewegungen (1-100%).")
        
        self.lbl_master_vel = ttk.Label(master_frame, text="Vel: 100 % (Max)", width=15)
        self.lbl_master_vel.grid(row=1, column=2, sticky="w", padx=5)
        create_tooltip(self.lbl_master_vel, "Aktuell eingestellte Geschwindigkeit.")

        # ----- 5. INDIVIDUAL MOTOR CHANNELS (Compact Layout) -----
        indiv_frame = ttk.LabelFrame(left_frame, text=" Individual Motor Channels ", padding="10")
        indiv_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        motor_colors = self.motor_colors

        for idx, dxl_id in enumerate(MOTOR_IDS):
            # Motor Card
            motor_card = tk.Frame(indiv_frame, bg=self.PANEL_BG, highlightbackground=self.SURFACE_BG,
                                  highlightthickness=1)
            motor_card.pack(fill=tk.X, pady=3, padx=2)
            self.motor_cards[dxl_id] = motor_card
            
            # ---- ROW 1: Name + Checkboxes + Calibration + Status ----
            row1 = tk.Frame(motor_card, bg=self.PANEL_BG)
            row1.pack(fill=tk.X, padx=8, pady=(6, 2))
            
            # Motor Name (editable via double-click)
            accent_color = motor_colors[idx % len(motor_colors)]
            name_frame = tk.Frame(row1, bg=self.PANEL_BG)
            name_frame.pack(side=tk.LEFT)
            
            name_lbl = tk.Label(name_frame, text=self.motor_names[dxl_id],
                                bg=self.PANEL_BG, fg=accent_color,
                                font=("Segoe UI", 10, "bold"), anchor="w", cursor="hand2",
                                width=12)
            name_lbl.pack(fill=tk.BOTH, expand=True)
            name_lbl.bind("<Double-Button-1>", lambda e, did=dxl_id: self.start_name_edit(did))
            create_tooltip(name_lbl, "Doppelklick zum Umbenennen")
            
            self.motor_name_frames[dxl_id] = name_frame
            self.motor_name_labels[dxl_id] = name_lbl
            
            # ID Badge
            id_lbl = tk.Label(row1, text=f"#{dxl_id}", bg=self.SURFACE_BG, fg=self.SUBTEXT,
                              font=("Segoe UI", 8), padx=4, pady=1)
            id_lbl.pack(side=tk.LEFT, padx=(0, 6))
            create_tooltip(id_lbl, f"Dynamixel ID: {dxl_id}")
            
            # Checkboxes
            sync_v = tk.BooleanVar(value=True)
            self.sync_vars[dxl_id] = sync_v
            chk_sync = ttk.Checkbutton(row1, text="Sync", variable=sync_v, style="Panel.TCheckbutton")
            chk_sync.pack(side=tk.LEFT, padx=2)
            self.ui_sync_checkboxes[dxl_id] = chk_sync
            create_tooltip(chk_sync, "Aktiviert die Synchronisation. Dieser Motor folgt dem Master-Schieberegler.")

            t_var = tk.BooleanVar(value=False)
            self.torque_vars[dxl_id] = t_var
            chk_t = ttk.Checkbutton(
                row1, text="Torque", variable=t_var,
                command=lambda id=dxl_id: self.on_torque_check(id), state=tk.DISABLED,
                style="Panel.TCheckbutton"
            )
            chk_t.pack(side=tk.LEFT, padx=2)
            self.ui_torque_checkboxes[dxl_id] = chk_t
            create_tooltip(chk_t, "Aktiviert das Drehmoment. Wenn aus, ist der Motor stromlos und frei beweglich.")

            m_var = tk.BooleanVar(value=True)  # Default to Endlos until calibrated
            self.mode_vars[dxl_id] = m_var
            chk_m = ttk.Checkbutton(
                row1, text="Endlos", variable=m_var,
                command=lambda id=dxl_id: self.on_mode_toggle(id), state=tk.DISABLED,
                style="Panel.TCheckbutton"
            )
            chk_m.pack(side=tk.LEFT, padx=2)
            self.ui_mode_checkboxes[dxl_id] = chk_m
            create_tooltip(chk_m, "Wechselt zwischen Positionssteuerung und Endlos-Drehung.")
            
            sg_var = tk.BooleanVar(value=False)
            self.soft_grip_vars[dxl_id] = sg_var
            chk_sg = ttk.Checkbutton(
                row1, text="SG", variable=sg_var,
                command=lambda id=dxl_id: self.on_soft_grip_motor_toggle(id),
                style="Panel.TCheckbutton"
            )
            chk_sg.pack(side=tk.LEFT, padx=2)
            self.ui_soft_grip_checkboxes[dxl_id] = chk_sg
            create_tooltip(chk_sg, "Soft-Grip: Bei Kontakt hält der Motor automatisch an.")
            
            # Separator
            tk.Frame(row1, bg=self.SURFACE_BG, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=2)
            
            # Calibration Buttons
            btn_zero = ttk.Button(row1, text="Set Zero", width=10,
                                  command=lambda id=dxl_id: self.handle_calibration_click(id, "zero"),
                                  state=tk.DISABLED)
            btn_zero.bind("<Button-3>", lambda event, id=dxl_id: self.delete_calibration_menu(event, id, "zero"))
            btn_zero.pack(side=tk.LEFT, padx=2)
            self.ui_btn_zero[dxl_id] = btn_zero
            create_tooltip(btn_zero, "Links-Klick: Position setzen oder anfahren.\nRechts-Klick: Position löschen.")
            
            btn_limit = ttk.Button(row1, text="Set Limit", width=10,
                                   command=lambda id=dxl_id: self.handle_calibration_click(id, "limit"),
                                   state=tk.DISABLED)
            btn_limit.bind("<Button-3>", lambda event, id=dxl_id: self.delete_calibration_menu(event, id, "limit"))
            btn_limit.pack(side=tk.LEFT, padx=2)
            self.ui_btn_limit[dxl_id] = btn_limit
            create_tooltip(btn_limit, "Links-Klick: Position setzen oder anfahren.\nRechts-Klick: Position löschen.")
            
            # Status Info (right side of row 1)
            tk.Frame(row1, bg=self.SURFACE_BG, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=2)
            contact_lbl = tk.Label(row1, text="● Kein Kontakt", bg=self.PANEL_BG,
                                   fg=self.SUBTEXT, font=("Segoe UI", 9), width=14, anchor="w")
            contact_lbl.pack(side=tk.LEFT, padx=2)
            self.contact_labels[dxl_id] = contact_lbl
            create_tooltip(contact_lbl, "Zeigt den aktuellen physischen Kontaktstatus des Fingers an.")
 
            lbl_readout = tk.Label(row1, text="Pos: ------", bg=self.PANEL_BG,
                                   fg=self.FG_COLOR, font=("Segoe UI", 9), width=11, anchor="w")
            lbl_readout.pack(side=tk.LEFT, padx=2)
            self.readout_labels[dxl_id] = lbl_readout
            create_tooltip(lbl_readout, "Zeigt die aktuelle Ist-Position des Motors in Ticks an.")
            
            # Temperature + Error + Reboot (far right)
            temp_lbl = tk.Label(row1, text="🌡--°C", bg=self.PANEL_BG, fg=self.ACCENT_GREEN,
                                font=("Segoe UI", 9), width=6)
            temp_lbl.pack(side=tk.RIGHT, padx=2)
            self.temp_labels[dxl_id] = temp_lbl
            create_tooltip(temp_lbl, "Aktuelle Motortemperatur. Wird rot bei über 55°C (Kollisionsgefahr).")
            
            err_lbl = tk.Label(row1, text="✓", bg=self.PANEL_BG, fg=self.ACCENT_GREEN,
                               font=("Segoe UI", 9, "bold"), width=2)
            err_lbl.pack(side=tk.RIGHT, padx=2)
            self.error_labels[dxl_id] = err_lbl
            create_tooltip(err_lbl, "Hardware-Fehlerstatus des Motors. ✓ bedeutet alles in Ordnung.")

            btn_reboot = ttk.Button(row1, text="Reboot", width=6,
                                    command=lambda id=dxl_id: self.reboot_motor(id))
            btn_reboot.pack(side=tk.RIGHT, padx=2)
            create_tooltip(btn_reboot, "Startet den Motor neu, um Fehler (z.B. Overload) zu löschen.")

            # ---- ROW 2: Position Slider ----
            row2 = tk.Frame(motor_card, bg=self.PANEL_BG)
            row2.pack(fill=tk.X, padx=8, pady=(2, 2))
            
            # Position Slider
            tk.Label(row2, text="Pos:", bg=self.PANEL_BG, fg=self.SUBTEXT,
                     font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 2))
            
            s_var = tk.IntVar(value=0)
            self.slider_vars[dxl_id] = s_var
            slider = ttk.Scale(
                row2, from_=0, to=1, variable=s_var,
                orient="horizontal",
                command=lambda val, id=dxl_id: self.on_indiv_slider_move(id, val),
                state=tk.DISABLED, style="Panel.Horizontal.TScale"
            )
            slider.bind("<ButtonRelease-1>", lambda event, id=dxl_id: self.on_slider_release(event, id))
            slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self.ui_indiv_sliders[dxl_id] = slider
            create_tooltip(slider, "Bewegt den Finger zwischen Zero und Limit.")
            
            # ---- ROW 3: Current Limit Slider ----
            row3 = tk.Frame(motor_card, bg=self.PANEL_BG)
            row3.pack(fill=tk.X, padx=8, pady=(2, 6))
            
            # Current Limit Slider
            lbl_m = tk.Label(row3, text="mA:", bg=self.PANEL_BG, fg=self.SUBTEXT,
                             font=("Segoe UI", 8))
            lbl_m.pack(side=tk.LEFT, padx=(0, 2))
            create_tooltip(lbl_m, "Strombegrenzung für die Kontakterkennung (Greifkraft).")
            
            c_var = tk.IntVar(value=600)
            self.current_vars[dxl_id] = c_var
            curr_slider = ttk.Scale(
                row3, from_=0, to=1750, variable=c_var,
                orient="horizontal",
                command=lambda val, id=dxl_id: self.on_current_slider_move(id, val),
                state=tk.DISABLED, style="Panel.Horizontal.TScale"
            )
            curr_slider.bind("<ButtonRelease-1>",
                             lambda event, id=dxl_id: self.on_current_slider_release(event, id))
            curr_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self.ui_current_sliders[dxl_id] = curr_slider
            create_tooltip(curr_slider, "Strombegrenzung für die Kontakterkennung (Greifkraft).")
            
            lbl_curr = tk.Label(row3, text="600", bg=self.PANEL_BG, fg=self.FG_COLOR,
                                font=("Segoe UI", 8), width=5, anchor="e")
            lbl_curr.pack(side=tk.LEFT, padx=2)
            self.current_labels[dxl_id] = lbl_curr
            create_tooltip(lbl_curr, "Aktuell eingestellte maximale Stromstärke (mA).")

        # =====================================================
        # RIGHT SIDE
        # ========        # ----- POSEN BIBLIOTHEK -----
        poses_frame = ttk.LabelFrame(self.right_frame, text=" Posen Bibliothek ", padding="8")
        poses_frame.pack(fill=tk.X, pady=(0, 8))
        
        row_p1 = ttk.Frame(poses_frame)
        row_p1.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(row_p1, text="Name:").pack(side=tk.LEFT, padx=1)
        self.pose_name_var = tk.StringVar(value="Hand Open")
        entry_pose_name = ttk.Entry(row_p1, textvariable=self.pose_name_var, width=18)
        entry_pose_name.pack(side=tk.LEFT, padx=1)
        create_tooltip(entry_pose_name, "Gib hier den Namen ein, unter dem die aktuelle Pose gespeichert werden soll.")
        self.btn_save_pose = ttk.Button(row_p1, text="💾", width=3, command=self.save_single_pose)
        self.btn_save_pose.pack(side=tk.LEFT, padx=1)
        create_tooltip(self.btn_save_pose, "Speichert die aktuellen Positionen aller synchronisierten Motoren als neue Pose.")
        
        ttk.Separator(row_p1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        self.cb_poses = ttk.Combobox(row_p1, state="readonly", width=18)
        self.cb_poses.pack(side=tk.LEFT, padx=1)
        create_tooltip(self.cb_poses, "Auswahl einer gespeicherten Pose.")
        btn_go_pose = ttk.Button(row_p1, text="▶ Go", width=6, command=self.go_to_selected_pose)
        btn_go_pose.pack(side=tk.LEFT, padx=1)
        create_tooltip(btn_go_pose, "Fährt alle synchronisierten Motoren sofort in diese Pose.")
        btn_add_seq = ttk.Button(row_p1, text="+ Ablauf", width=9, command=self.add_pose_to_sequence)
        btn_add_seq.pack(side=tk.LEFT, padx=1)
        create_tooltip(btn_add_seq, "Fügt diese Pose als neuen Schritt an das Ende des Ablaufs an.")
        btn_del_pose = ttk.Button(row_p1, text="🗑", width=3, command=self._delete_selected_pose, style="Danger.TButton")
        btn_del_pose.pack(side=tk.LEFT, padx=1)
        create_tooltip(btn_del_pose, "Löscht die aktuell ausgewählte Pose.")
 
 
        # ----- SEQUENZ EDITOR -----
        seq_frame = ttk.LabelFrame(self.right_frame, text=" Ablaufsteuerung ", padding="8")
        seq_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        
        # Controls row
        seq_ctrl = ttk.Frame(seq_frame)
        seq_ctrl.pack(fill=tk.X, pady=(0, 5))
        
        self.wait_type_var = tk.StringVar(value="Time")
        
        ttk.Label(seq_ctrl, text="ms:").pack(side=tk.LEFT, padx=1)
        self.wait_val_var = tk.StringVar(value="1000")
        entry_wait = ttk.Entry(seq_ctrl, textvariable=self.wait_val_var, width=5)
        entry_wait.pack(side=tk.LEFT, padx=1)
        create_tooltip(entry_wait, "Wartezeit in Millisekunden für den neuen Schritt.")
        
        ttk.Separator(seq_ctrl, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        btn_append = ttk.Button(seq_ctrl, text="+ Pose", width=8,
                                command=self.append_current_pose_to_sequence)
        btn_append.pack(side=tk.LEFT, padx=1)
        create_tooltip(btn_append, "Hängt die JETZT eingestellten Slider-Werte als neuen Schritt an.")
        
        self.btn_home = ttk.Button(seq_ctrl, text="⌂ Zero", width=6, command=self.go_home)
        self.btn_home.pack(side=tk.LEFT, padx=1)
        create_tooltip(self.btn_home, "Fährt alle aktiven Motoren auf ihre Zero-Position zurück.")
        
        btn_sg_settings = ttk.Button(seq_ctrl, text="⚙ SG-Std", width=9, command=self.open_seq_sg_settings)
        btn_sg_settings.pack(side=tk.LEFT, padx=1)
        create_tooltip(btn_sg_settings, "Öffnet ein Fenster, um die standardmäßigen Soft-Grip Haken und Kräfte für den Ablauf festzulegen.")
        
        # Listbox (expands vertically on right side)
        list_container = ttk.Frame(seq_frame)
        list_container.pack(fill=tk.BOTH, expand=True, pady=3)
        
        self.seq_listbox = tk.Listbox(list_container, bg=self.SURFACE_BG, fg=self.FG_COLOR,
                                      borderwidth=0, selectbackground=self.ACCENT_BLUE,
                                      selectforeground="#1e1e2e", font=("Segoe UI", 9))
        self.seq_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self.seq_listbox.bind("<Button-3>", self.seq_listbox_context_menu)
        create_tooltip(self.seq_listbox, "Liste der Ablaufschritte. Rechtsklick zum Bearbeiten, Duplizieren oder Löschen.")
        
        list_btn_frame = ttk.Frame(list_container)
        list_btn_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        btn_up = ttk.Button(list_btn_frame, text="▲", width=3, command=self.seq_move_up)
        btn_up.pack(fill=tk.X, pady=1)
        create_tooltip(btn_up, "Verschiebt den ausgewählten Schritt nach oben.")
        
        btn_down = ttk.Button(list_btn_frame, text="▼", width=3, command=self.seq_move_down)
        btn_down.pack(fill=tk.X, pady=1)
        create_tooltip(btn_down, "Verschiebt den ausgewählten Schritt nach unten.")
        
        btn_del = ttk.Button(list_btn_frame, text="✕", width=3, command=self.seq_delete_step)
        btn_del.pack(fill=tk.X, pady=1)
        create_tooltip(btn_del, "Löscht den ausgewählten Schritt.")
        btn_clear = ttk.Button(list_btn_frame, text="⌀", width=3, command=self.seq_clear_all)
        btn_clear.pack(fill=tk.X, pady=1)
        create_tooltip(btn_clear, "Leert die gesamte Liste der Ablaufschritte.")
        
        # Play + Save/Load row
        # Row 1 for Play control and Status
        seq_play_row1 = ttk.Frame(seq_frame)
        seq_play_row1.pack(fill=tk.X, pady=(5, 2))
        
        self.btn_play_seq = ttk.Button(seq_play_row1, text="▶ Start (0)", width=10,
                                       command=self.play_sequence, style="Primary.TButton")
        self.btn_play_seq.pack(side=tk.LEFT, padx=1)
        create_tooltip(self.btn_play_seq, "Startet das Abspielen des aktuellen Ablaufs.")
        
        self.lbl_seq_status = ttk.Label(seq_play_row1, text="Bereit", width=25,
                                        font=("Segoe UI", 9, "bold"), foreground=self.ACCENT_GREEN)
        self.lbl_seq_status.pack(side=tk.LEFT, padx=5)
        create_tooltip(self.lbl_seq_status, "Zeigt den aktuellen Ausführungsstatus des Ablaufs.")
        
        # Row 2 for Save/Load
        seq_play_row2 = ttk.Frame(seq_frame)
        seq_play_row2.pack(fill=tk.X, pady=(2, 0))
        
        lbl_name = ttk.Label(seq_play_row2, text="Name:")
        lbl_name.pack(side=tk.LEFT, padx=1)
        create_tooltip(lbl_name, "Name unter dem der Ablauf gespeichert werden soll.")
        
        self.seq_name_var = tk.StringVar(value="MeinAblauf")
        entry_seq_name = ttk.Entry(seq_play_row2, textvariable=self.seq_name_var, width=12)
        entry_seq_name.pack(side=tk.LEFT, padx=1)
        create_tooltip(entry_seq_name, "Gib einen Namen ein, um den Ablauf zu speichern.")
        
        btn_save_seq = ttk.Button(seq_play_row2, text="💾", width=3, command=self.save_sequence_to_file)
        btn_save_seq.pack(side=tk.LEFT, padx=1)
        create_tooltip(btn_save_seq, "Speichert den aktuellen Ablauf unter dem angegebenen Namen.")
        
        ttk.Separator(seq_play_row2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        self.cb_sequences = ttk.Combobox(seq_play_row2, state="readonly", width=12)
        self.cb_sequences.pack(side=tk.LEFT, padx=1)
        create_tooltip(self.cb_sequences, "Auswahl eines gespeicherten Ablaufs.")
        btn_load_seq = ttk.Button(seq_play_row2, text="📂 Laden", width=9, command=self.load_selected_sequence)
        btn_load_seq.pack(side=tk.LEFT, padx=1)
        create_tooltip(btn_load_seq, "Lädt den ausgewählten Ablauf in die Liste.")
        btn_del_seq = ttk.Button(seq_play_row2, text="🗑", width=3, command=self._delete_selected_seq, style="Danger.TButton")
        btn_del_seq.pack(side=tk.LEFT, padx=1)
        create_tooltip(btn_del_seq, "Löscht den aktuell im Dropdown ausgewählten Ablauf.")

        # ----- LIVE STROM GRAPH -----
        graph_frame = ttk.LabelFrame(self.root, text=" Live Strom (Kontakterkennung) ", padding="8")
        graph_frame.pack(side=tk.BOTTOM, fill=tk.X, expand=False, pady=(5, 5), padx=10, before=self.paned)
        
        self.canvas = tk.Canvas(graph_frame, bg="#11111b", height=300, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        legend_frame = ttk.Frame(graph_frame)
        legend_frame.pack(fill=tk.X, pady=5)
        
        for i, dxl_id in enumerate(MOTOR_IDS):
            c = motor_colors[i % len(motor_colors)]
            ind = tk.Label(legend_frame, text=self.motor_names.get(dxl_id, f"ID {dxl_id:02d}"),
                           bg=self.PANEL_BG, fg=c, font=("Segoe UI", 8, "bold"), padx=4, pady=1)
            ind.pack(side=tk.LEFT, padx=3)
            self.graph_indicators[dxl_id] = {"label": ind, "color": c}
            
        btn_export = ttk.Button(legend_frame, text="💾 Graph Exportieren", command=self.export_graph_menu, width=18)
        btn_export.pack(side=tk.RIGHT, padx=5)
        create_tooltip(btn_export, "Exportiert die Graphendaten als CSV oder als Bild (PNG).")

    # =================================================================
    # --- MOTOR NAMING (Feature 9) ---
    # =================================================================

    def load_motor_names(self):
        if os.path.exists("motor_names.json"):
            try:
                with open("motor_names.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                for dxl_id in MOTOR_IDS:
                    key = str(dxl_id)
                    if key in data:
                        self.motor_names[dxl_id] = data[key]
                        if dxl_id in self.motor_name_labels:
                            self.motor_name_labels[dxl_id].config(text=data[key])
                # Update graph legend labels too
                for dxl_id in MOTOR_IDS:
                    if dxl_id in self.graph_indicators:
                        self.graph_indicators[dxl_id]["label"].config(text=self.motor_names[dxl_id])
                print("Motor-Namen geladen.")
            except Exception as e:
                print(f"Fehler beim Laden der Motor-Namen: {e}")

    def save_motor_names(self):
        try:
            data = {str(k): v for k, v in self.motor_names.items()}
            with open("motor_names.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Fehler beim Speichern der Motor-Namen: {e}")

    def start_name_edit(self, dxl_id):
        """Doppelklick auf den Motor-Namen → Entry-Widget zum Bearbeiten"""
        self.motor_name_labels[dxl_id].pack_forget()
        
        entry = tk.Entry(self.motor_name_frames[dxl_id], bg=self.SURFACE_BG, fg=self.FG_COLOR,
                         insertbackground=self.FG_COLOR, font=("Segoe UI", 10, "bold"),
                         relief="flat", borderwidth=2)
        entry.insert(0, self.motor_names[dxl_id])
        entry.pack(fill=tk.BOTH, expand=True)
        entry.select_range(0, tk.END)
        entry.focus_set()
        
        entry.bind("<Return>", lambda e: self.finish_name_edit(dxl_id, entry))
        entry.bind("<Escape>", lambda e: self.cancel_name_edit(dxl_id, entry))
        entry.bind("<FocusOut>", lambda e: self.finish_name_edit(dxl_id, entry))

    def finish_name_edit(self, dxl_id, entry):
        """Bestätigt die Namensänderung"""
        new_name = entry.get().strip()
        if new_name:
            self.motor_names[dxl_id] = new_name
            self.motor_name_labels[dxl_id].config(text=new_name)
            # Update graph legend
            if dxl_id in self.graph_indicators:
                self.graph_indicators[dxl_id]["label"].config(text=new_name)
            self.save_motor_names()
        
        entry.destroy()
        self.motor_name_labels[dxl_id].pack(fill=tk.BOTH, expand=True)

    def cancel_name_edit(self, dxl_id, entry):
        """Bricht die Namensänderung ab"""
        entry.destroy()
        self.motor_name_labels[dxl_id].pack(fill=tk.BOTH, expand=True)




    # =================================================================
    # --- KONTAKTERKENNUNG (Feature 3) ---
    # =================================================================

    def detect_contact(self, dxl_id):
        """
        Robuste Kontakterkennung mit gleitendem Durchschnitt und Flanken-Erkennung.
        Returns: 'none', 'approaching', 'contact'
        """
        history = self.graph_history[dxl_id]
        limit = self.current_vars[dxl_id].get()
        
        if limit == 0:
            return "none"
        
        # Gleitender Durchschnitt über die letzten N Werte
        window = list(history)[-CONTACT_AVG_WINDOW:]
        avg_current = sum(abs(c) for c in window) / len(window)
        
        # Anstiegsflanken-Erkennung (Rate of Change über 3 Datenpunkte)
        rate = 0
        if len(history) >= 3:
            vals = [abs(history[-1]), abs(history[-2]), abs(history[-3])]
            rate = vals[0] - vals[2]  # Änderung über 3 Ticks
        
        # Kombinierte Kontakt-Bedingungen
        contact_by_threshold = avg_current > (limit * CONTACT_THRESHOLD_PCT) and avg_current > 50
        contact_by_spike = rate > CONTACT_SPIKE_THRESHOLD and avg_current > 30
        
        if contact_by_threshold or contact_by_spike:
            return "contact"
        elif avg_current > (limit * 0.5) and avg_current > 30:
            return "approaching"
        else:
            return "none"

    def update_contact_indicators(self):
        """Aktualisiert die Kontakt-Indikatoren in der GUI"""
        for dxl_id in MOTOR_IDS:
            state = self.detect_contact(dxl_id)
            self.contact_states[dxl_id] = state
            
            if state == "contact":
                self.contact_labels[dxl_id].config(text="● Kontakt!", fg=self.ACCENT_GREEN)
            elif state == "approaching":
                self.contact_labels[dxl_id].config(text="● Annäherung", fg=self.ACCENT_YELLOW)
            else:
                self.contact_labels[dxl_id].config(text="● Kein Kontakt", fg=self.SUBTEXT)

    # =================================================================
    # --- SOFT-GRIP (Feature 6) ---
    # =================================================================

    def toggle_soft_grip_global(self):
        """Toggled den globalen Soft-Grip Modus"""
        new_val = not self.soft_grip_global.get()
        self.soft_grip_global.set(new_val)
        self._update_soft_grip_global_button()
        
        if not new_val:
            # Alle Frozen-States zurücksetzen
            for dxl_id in MOTOR_IDS:
                self.soft_grip_frozen[dxl_id] = False

    def _update_soft_grip_global_button(self):
        if self.soft_grip_global.get():
            self.btn_soft_grip_global.config(text="🤏 Soft-Grip: AN", style="ToggleOn.TButton")
        else:
            self.btn_soft_grip_global.config(text="🤏 Soft-Grip: AUS", style="Toggle.TButton")

    def on_soft_grip_motor_toggle(self, dxl_id):
        """Toggled Soft-Grip für einen einzelnen Motor"""
        if not self.soft_grip_vars[dxl_id].get():
            self.soft_grip_frozen[dxl_id] = False

    def process_soft_grip(self):
        """Wird im Telemetrie-Loop aufgerufen. Friert Motoren bei Kontakt ein."""
        for dxl_id in MOTOR_IDS:
            # Prüfe ob Soft-Grip aktiv ist (global ODER per Motor)
            is_sg = self.soft_grip_vars[dxl_id].get() or self.soft_grip_global.get()
            
            if not is_sg or not self.torque_vars[dxl_id].get() or self.mode_vars[dxl_id].get():
                continue
            
            if self.soft_grip_frozen[dxl_id]:
                continue  # Bereits eingefroren, nichts tun
            
            contact = self.detect_contact(dxl_id)
            
            if contact == "contact":
                # Einfrieren: Goal Position = Present Position
                pos = self.present_positions.get(dxl_id, 0)
                self.write_goal_position(dxl_id, pos)
                self.slider_vars[dxl_id].set(pos)
                self.soft_grip_frozen[dxl_id] = True

    # =================================================================
    # --- KALIBRIERUNG ---
    # =================================================================

    def handle_calibration_click(self, dxl_id, point_type):
        if not self.is_connected: return
        
        is_set = False
        target_pos = None
        if point_type == "zero" and self.calib_zero[dxl_id] is not None:
            is_set = True
            target_pos = self.calib_zero[dxl_id]
        elif point_type == "limit" and self.calib_limit[dxl_id] is not None:
            is_set = True
            target_pos = self.calib_limit[dxl_id]

        if is_set:
            # Move to position
            if not self.ensure_torque_enabled([dxl_id]): return
            if self.torque_vars[dxl_id].get() and not self.mode_vars[dxl_id].get():
                self.serial_mutex = True
                try:
                    self.write_goal_position(dxl_id, target_pos)
                    self.slider_vars[dxl_id].set(target_pos)
                    self.soft_grip_frozen[dxl_id] = False
                except Exception as e:
                    print(f"Fehler beim Anfahren der Kalibrierposition (ID {dxl_id}): {e}")
                finally:
                    self.serial_mutex = False
            return

        self.serial_mutex = True
        try:
            pos, res, _ = self.read_present_position(dxl_id)
        except Exception as e:
            print(f"Fehler beim Lesen der Position (ID {dxl_id}): {e}")
            return
        finally:
            self.serial_mutex = False
        
        if res != COMM_SUCCESS:
            print(f"Fehler beim Lesen der Position für ID {dxl_id}")
            return
            
        if point_type == "zero":
            self.reboot_offsets[dxl_id] = 0
            
            old_zero = self.calib_zero[dxl_id]
            if old_zero is None:
                old_zero = self.last_deleted_zero.get(dxl_id)
            old_limit = self.calib_limit[dxl_id]
            if old_limit is None:
                old_limit = self.last_deleted_limit.get(dxl_id)
                
            self.calib_zero[dxl_id] = pos
            self.ui_btn_zero[dxl_id].config(text=f"Z: {pos}")
            
            if old_zero is not None and old_limit is not None:
                shift = pos - old_zero
                new_limit = old_limit + shift
                self.calib_limit[dxl_id] = new_limit
                self.ui_btn_limit[dxl_id].config(text=f"L: {new_limit}")
                self.apply_calibration_shift(dxl_id, shift)
                
        elif point_type == "limit":
            old_zero = self.calib_zero[dxl_id]
            if old_zero is None:
                old_zero = self.last_deleted_zero.get(dxl_id)
            old_limit = self.calib_limit[dxl_id]
            if old_limit is None:
                old_limit = self.last_deleted_limit.get(dxl_id)
                
            self.calib_limit[dxl_id] = pos
            self.ui_btn_limit[dxl_id].config(text=f"L: {pos}")
            
            if old_zero is not None and old_limit is not None:
                shift = pos - old_limit
                new_zero = old_zero + shift
                self.calib_zero[dxl_id] = new_zero
                self.ui_btn_zero[dxl_id].config(text=f"Z: {new_zero}")
                self.apply_calibration_shift(dxl_id, shift)
            
        self.check_calibration_status(dxl_id)
        self.save_calibration(silent=True)

    def delete_calibration_menu(self, event, dxl_id, point_type):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Löschen", command=lambda: self.delete_calibration(dxl_id, point_type))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def delete_calibration(self, dxl_id, point_type):
        if point_type == "zero":
            if self.calib_zero[dxl_id] is not None:
                self.last_deleted_zero[dxl_id] = self.calib_zero[dxl_id]
            self.calib_zero[dxl_id] = None
            self.ui_btn_zero[dxl_id].config(text="Set Zero")
        elif point_type == "limit":
            if self.calib_limit[dxl_id] is not None:
                self.last_deleted_limit[dxl_id] = self.calib_limit[dxl_id]
            self.calib_limit[dxl_id] = None
            self.ui_btn_limit[dxl_id].config(text="Set Limit")
        self.check_calibration_status(dxl_id)
        self.save_calibration(silent=True)

    def apply_calibration_shift(self, dxl_id, shift):
        if shift == 0: return
        dxl_str = str(dxl_id)
        
        # 1. Shift saved poses
        for pose_name, pose_data in self.saved_poses.items():
            pose = pose_data.get("pose", {})
            if dxl_str in pose:
                pose[dxl_str] = int(pose[dxl_str] + shift)
        
        try:
            with open("poses.json", "w") as f:
                json.dump(self.saved_poses, f)
            print(f"Posen nach Kalibrierungsverschiebung ({shift} Ticks) gespeichert.")
        except Exception as e:
            print(f"Fehler beim Speichern der Posen nach Verschiebung: {e}")
            
        # 2. Shift currently loaded sequence frames
        for frame in self.sequence_frames:
            state = frame.get("state", {})
            pose = state.get("pose", {})
            if dxl_str in pose:
                pose[dxl_str] = int(pose[dxl_str] + shift)
                
        # 3. Shift saved sequences
        for seq_name, seq_data in self.saved_sequences.items():
            frames = seq_data.get("frames", [])
            for frame in frames:
                state = frame.get("state", {})
                pose = state.get("pose", {})
                if dxl_str in pose:
                    pose[dxl_str] = int(pose[dxl_str] + shift)
                    
        try:
            with open("sequences.json", "w") as f:
                json.dump(self.saved_sequences, f)
            print(f"Abläufe nach Kalibrierungsverschiebung ({shift} Ticks) gespeichert.")
        except Exception as e:
            print(f"Fehler beim Speichern der Abläufe nach Verschiebung: {e}")
            
        self.refresh_sequence_listbox()

    def read_present_position(self, dxl_id):
        pos, res, err = self.packetHandler.read4ByteTxRx(self.portHandler, dxl_id, ADDR_PRESENT_POSITION)
        if res == COMM_SUCCESS:
            if pos & 0x80000000:
                pos = pos - 0x100000000
            offset = self.reboot_offsets.get(dxl_id, 0)
            return pos + offset, res, err
        return pos, res, err

    def write_goal_position(self, dxl_id, pos):
        offset = self.reboot_offsets.get(dxl_id, 0)
        raw_pos = int(pos - offset)
        return self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_POSITION, raw_pos & 0xFFFFFFFF)

    def calculate_reboot_offset(self, dxl_id):
        if not self.is_connected:
            return
        # Temporarily read position without offset to get raw position
        pos, res, _ = self.packetHandler.read4ByteTxRx(self.portHandler, dxl_id, ADDR_PRESENT_POSITION)
        if res == COMM_SUCCESS:
            if pos & 0x80000000:
                pos = pos - 0x100000000
            if self.calib_zero.get(dxl_id) is not None:
                # Find the multiple of 4096 that maps pos closest to calib_zero
                N = round((self.calib_zero[dxl_id] - pos) / 4096.0)
                self.reboot_offsets[dxl_id] = int(N * 4096)
                print(f"[REBOOT ALIGN] Motor {dxl_id}: Raw={pos}, CalibZero={self.calib_zero[dxl_id]}, Offset={self.reboot_offsets[dxl_id]} ticks (N={N})")
            else:
                self.reboot_offsets[dxl_id] = 0
            
        self.check_calibration_status(dxl_id)
        self.save_calibration(silent=True)

    def check_calibration_status(self, dxl_id):
        c_zero = self.calib_zero[dxl_id]
        c_limit = self.calib_limit[dxl_id]
        
        is_fully_calibrated = (c_zero is not None and c_limit is not None)
        
        if is_fully_calibrated:
            if self.mode_vars[dxl_id].get(): 
                self.mode_vars[dxl_id].set(False)
                if self.is_connected:
                    self.on_mode_toggle(dxl_id) 

            if not self.mode_vars[dxl_id].get():
                min_val = min(c_zero, c_limit)
                max_val = max(c_zero, c_limit)
                self.ui_indiv_sliders[dxl_id].config(state=tk.NORMAL, from_=min_val, to=max_val)
            print(f"ID {dxl_id} kalibriert: Min {min_val}, Max {max_val}")
        else:
            if not self.mode_vars[dxl_id].get():
                self.mode_vars[dxl_id].set(True)
                if self.is_connected:
                    self.on_mode_toggle(dxl_id)
            
            # Disable only if not in endless mode, or if disconnected
            if not self.mode_vars[dxl_id].get() or not self.is_connected:
                self.ui_indiv_sliders[dxl_id].config(state=tk.DISABLED)
            else:
                self.ui_indiv_sliders[dxl_id].config(state=tk.NORMAL, from_=MIN_VEL_LIMIT, to=MAX_VEL_LIMIT)
                self.slider_vars[dxl_id].set(0)

    def reset_all_calibration_ui(self):
        if messagebox.askyesno("Reset All", "Möchtest du wirklich alle Kalibrierungen löschen?"):
            self.reset_all_calibration()
            self.save_calibration(silent=True)

    def reset_all_calibration(self):
        for dxl_id in MOTOR_IDS:
            self.calib_zero[dxl_id] = None
            self.calib_limit[dxl_id] = None
            self.ui_btn_zero[dxl_id].config(text="Set Zero")
            self.ui_btn_limit[dxl_id].config(text="Set Limit")
            self.check_calibration_status(dxl_id)

    def save_calibration(self, silent=False):
        data = {
            "calib_zero": self.calib_zero,
            "calib_limit": self.calib_limit
        }
        try:
            with open("calibration.json", "w") as f:
                json.dump(data, f)
            if not silent:
                messagebox.showinfo("Erfolg", "Kalibrierung erfolgreich gespeichert!")
        except Exception as e:
            if not silent:
                messagebox.showerror("Fehler", f"Konnte Kalibrierung nicht speichern:\n{e}")
            else:
                print(f"Konnte Kalibrierung nicht speichern: {e}")

    def load_calibration(self):
        if os.path.exists("calibration.json"):
            try:
                with open("calibration.json", "r") as f:
                    data = json.load(f)
                
                loaded_zero = {int(k): v for k, v in data.get("calib_zero", {}).items()}
                loaded_limit = {int(k): v for k, v in data.get("calib_limit", {}).items()}
                
                for dxl_id in MOTOR_IDS:
                    if dxl_id in loaded_zero:
                        self.calib_zero[dxl_id] = loaded_zero[dxl_id]
                        if loaded_zero[dxl_id] is not None:
                            self.ui_btn_zero[dxl_id].config(text=f"Z: {loaded_zero[dxl_id]}")
                    if dxl_id in loaded_limit:
                        self.calib_limit[dxl_id] = loaded_limit[dxl_id]
                        if loaded_limit[dxl_id] is not None:
                            self.ui_btn_limit[dxl_id].config(text=f"L: {loaded_limit[dxl_id]}")
                    
                    self.check_calibration_status(dxl_id)
                print("Kalibrierung geladen.")
            except Exception as e:
                print(f"Fehler beim Laden der Kalibrierung: {e}")

    # =================================================================
    # --- SEQUENZER & HOME LOGIK ---
    # =================================================================
    
    def go_home(self):
        if not self.is_connected: return
        active_ids = [did for did in MOTOR_IDS if self.ui_sync_checkboxes[did].instate(['selected'])]
        if not self.ensure_torque_enabled(active_ids): return
        
        self.is_programmatic_change = True
        self.serial_mutex = True
        try:
            self.sync_write_pos.clearParam()
            has_targets = False

            for dxl_id in MOTOR_IDS:
                zero_pos = self.calib_zero[dxl_id]
                if (not self.mode_vars[dxl_id].get() and self.torque_vars[dxl_id].get()
                        and zero_pos is not None and self.sync_vars[dxl_id].get()):
                    self.slider_vars[dxl_id].set(zero_pos)
                    self.soft_grip_frozen[dxl_id] = False  # Unfreeze bei Home

                    offset = self.reboot_offsets.get(dxl_id, 0)
                    raw_pos = int(zero_pos - offset) & 0xFFFFFFFF
                    param_pos = [
                        raw_pos & 0xFF,
                        (raw_pos >> 8) & 0xFF,
                        (raw_pos >> 16) & 0xFF,
                        (raw_pos >> 24) & 0xFF
                    ]
                    self.sync_write_pos.addParam(dxl_id, param_pos)
                    has_targets = True

            if has_targets:
                self.sync_write_pos.txPacket()

            self.master_slider_var.set(0.0)
            self.lbl_master_pos.config(text="0.0 %")
        except Exception as e:
            print(f"Fehler bei Home-Bewegung: {e}")
        finally:
            self.serial_mutex = False
            self.is_programmatic_change = False

    def load_poses_from_file(self):
        if os.path.exists("poses.json"):
            try:
                with open("poses.json", "r") as f:
                    self.saved_poses = json.load(f)
                self.update_pose_combobox()
            except Exception as e:
                print(f"Fehler beim Laden der Posen: {e}")

    def update_pose_combobox(self):
        names = list(self.saved_poses.keys())
        self.cb_poses['values'] = names
        if names and not self.cb_poses.get():
            self.cb_poses.set(names[0])



    def _delete_selected_pose(self):
        name = self.cb_poses.get()
        if not name or name not in self.saved_poses:
            return
        if messagebox.askyesno("Löschen", f"Möchtest du die Pose '{name}' wirklich löschen?"):
            del self.saved_poses[name]
            with open("poses.json", "w") as f:
                json.dump(self.saved_poses, f, indent=4)
            self.cb_poses.set("")
            self.update_pose_combobox()

    def get_current_state(self):
        """Erfasst den aktuellen Zustand für Posen (inkl. Soft-Grip)"""
        pose = {}
        limits = {}
        velocities = {}
        for dxl_id in MOTOR_IDS:
            if not self.mode_vars[dxl_id].get() and self.calib_zero[dxl_id] is not None:
                pose[dxl_id] = self.slider_vars[dxl_id].get()
                limits[dxl_id] = self.current_vars[dxl_id].get()
                velocities[dxl_id] = self.master_vel_var.get()
        
        return {
            "pose": pose,
            "limits": limits,
            "velocities": velocities,
            "soft_grip_global": self.soft_grip_global.get(),
            "soft_grip_motors": {str(dxl_id): self.soft_grip_vars[dxl_id].get() for dxl_id in MOTOR_IDS}
        }

    def save_single_pose(self):
        name = self.pose_name_var.get().strip()
        if not name:
            messagebox.showwarning("Warnung", "Bitte einen Namen für die Pose eingeben!")
            return
        try:
            self.saved_poses[name] = self.get_current_state()
            with open("poses.json", "w") as f:
                json.dump(self.saved_poses, f)
            self.update_pose_combobox()
            self.cb_poses.set(name)
            messagebox.showinfo("Erfolg", f"Pose '{name}' gespeichert!")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Posen nicht speichern:\n{e}")

    def go_to_selected_pose(self):
        name = self.cb_poses.get()
        if name in self.saved_poses and self.is_connected:
            active_ids = [did for did in MOTOR_IDS if self.ui_sync_checkboxes[did].instate(['selected'])]
            if not self.ensure_torque_enabled(active_ids): return
            self.apply_state(self.saved_poses[name])

    def apply_state(self, state):
        self.is_programmatic_change = True
        self.serial_mutex = True
        try:
            self._apply_state_locked(state)
        except Exception as e:
            print(f"Fehler beim Anwenden des Zustands: {e}")
        finally:
            self.serial_mutex = False
            self.is_programmatic_change = False

    def _apply_state_locked(self, state):
        pose = state.get("pose", {})
        limits = state.get("limits", {})
        velocities = state.get("velocities", {})
        
        # Soft-Grip Zustand wiederherstellen (Feature 6)
        sg_global = state.get("soft_grip_global", False)
        self.soft_grip_global.set(sg_global)
        self._update_soft_grip_global_button()
        
        sg_motors = state.get("soft_grip_motors", {})
        for dxl_id in MOTOR_IDS:
            dxl_id_str = str(dxl_id)
            val = sg_motors.get(dxl_id_str, "default")
            
            # Resolve actual Soft-Close state
            if val == "default":
                resolved_sg = self.seq_default_sg_vars[dxl_id].get()
            else:
                resolved_sg = True if val is True or val == "True" else False
                
            if dxl_id in self.soft_grip_vars:
                self.soft_grip_vars[dxl_id].set(resolved_sg)
                self.soft_grip_frozen[dxl_id] = False  # Unfreeze bei neuer Pose
        
        self.sync_write_current.clearParam()
        self.sync_write_profile_vel.clearParam()
        self.sync_write_pos.clearParam()
        
        has_curr = False
        has_vel = False
        has_pos = False
        
        for dxl_id_str, target_pos in pose.items():
            dxl_id = int(dxl_id_str)
            if not self.mode_vars[dxl_id].get() and self.torque_vars[dxl_id].get():
                if dxl_id_str in limits:
                    limit_val = limits[dxl_id_str]
                    if limit_val == "default" or limit_val == "default_ma":
                        limit = self.seq_default_ma_vars[dxl_id].get()
                    else:
                        limit = int(limit_val)
                else:
                    limit = self.seq_default_ma_vars[dxl_id].get()
                        
                self.current_vars[dxl_id].set(limit)
                self.current_labels[dxl_id].config(text=f"{limit}")
                
                param_curr = [
                    limit & 0xFF,
                    (limit >> 8) & 0xFF
                ]
                self.sync_write_current.addParam(dxl_id, param_curr)
                has_curr = True
                
                # Apply custom velocity for this step
                vel_pct = velocities.get(dxl_id_str, velocities.get(dxl_id, 100))
                hardware_vel = int((vel_pct / 100.0) * 300) if vel_pct < 100 else 0
                if hardware_vel == 0 and vel_pct < 100: hardware_vel = 1
                
                param_vel = [
                    hardware_vel & 0xFF,
                    (hardware_vel >> 8) & 0xFF,
                    (hardware_vel >> 16) & 0xFF,
                    (hardware_vel >> 24) & 0xFF
                ]
                self.sync_write_profile_vel.addParam(dxl_id, param_vel)
                has_vel = True

                self.slider_vars[dxl_id].set(target_pos)
                
                offset = self.reboot_offsets.get(dxl_id, 0)
                raw_pos = int(target_pos - offset) & 0xFFFFFFFF
                param_pos = [
                    raw_pos & 0xFF,
                    (raw_pos >> 8) & 0xFF,
                    (raw_pos >> 16) & 0xFF,
                    (raw_pos >> 24) & 0xFF
                ]
                self.sync_write_pos.addParam(dxl_id, param_pos)
                has_pos = True
                
        if has_curr:
            self.sync_write_current.txPacket()
        if has_vel:
            self.sync_write_profile_vel.txPacket()
        if has_pos:
            self.sync_write_pos.txPacket()

    def get_wait_settings(self):
        try:
            val = int(self.wait_val_var.get())
        except ValueError:
            val = 1000
        return self.wait_type_var.get(), val

    def add_pose_to_sequence(self):
        name = self.cb_poses.get()
        if name in self.saved_poses:
            import copy
            state = copy.deepcopy(self.saved_poses[name])
            state["limits"] = {str(did): "default" for did in MOTOR_IDS}
            state["soft_grip_motors"] = {str(did): "default" for did in MOTOR_IDS}
            w_type, w_val = self.get_wait_settings()
            frame_data = {"name": name, "state": state, "wait_type": w_type, "wait_val": w_val}
            self.sequence_frames.append(frame_data)
            self._mark_seq_unsaved()
            self.refresh_sequence_listbox()

    def append_current_pose_to_sequence(self):
        import copy
        state = copy.deepcopy(self.get_current_state())
        state["limits"] = {str(did): "default" for did in MOTOR_IDS}
        state["soft_grip_motors"] = {str(did): "default" for did in MOTOR_IDS}
        w_type, w_val = self.get_wait_settings()
        frame_data = {"name": "Custom", "state": state, "wait_type": w_type, "wait_val": w_val}
        self.sequence_frames.append(frame_data)
        self._mark_seq_unsaved()
        self.refresh_sequence_listbox()

    def refresh_sequence_listbox(self):
        self.seq_listbox.delete(0, tk.END)
        for i, frame in enumerate(self.sequence_frames):
            name = frame.get("name", "Step")
            wt = frame.get("wait_type", "Time")
            wv = frame.get("wait_val", 1000)
            sg = "🤏" if frame.get("state", {}).get("soft_grip_global", False) else ""
            self.seq_listbox.insert(tk.END, f"{i+1}. {name} ({wt}: {wv}ms) {sg}")
        self.btn_play_seq.config(text=f"▶ Start ({len(self.sequence_frames)})")

    def seq_move_up(self):
        idx = self.seq_listbox.curselection()
        if not idx or idx[0] == 0: return
        i = idx[0]
        self.sequence_frames[i], self.sequence_frames[i-1] = self.sequence_frames[i-1], self.sequence_frames[i]
        self._mark_seq_unsaved()
        self.refresh_sequence_listbox()
        self.seq_listbox.selection_set(i-1)

    def seq_move_down(self):
        idx = self.seq_listbox.curselection()
        if not idx or idx[0] == len(self.sequence_frames)-1: return
        i = idx[0]
        self.sequence_frames[i], self.sequence_frames[i+1] = self.sequence_frames[i+1], self.sequence_frames[i]
        self._mark_seq_unsaved()
        self.refresh_sequence_listbox()
        self.seq_listbox.selection_set(i+1)

    def seq_delete_step(self):
        idx = self.seq_listbox.curselection()
        if not idx: return
        del self.sequence_frames[idx[0]]
        self._mark_seq_unsaved()
        self.refresh_sequence_listbox()

    def seq_clear_all(self):
        if not self.check_unsaved_sequence_changes():
            return
        self.sequence_frames.clear()
        self.refresh_sequence_listbox()
        self.seq_unsaved_changes = False

    def seq_listbox_context_menu(self, event):
        idx = self.seq_listbox.nearest(event.y)
        if idx < 0 or idx >= len(self.sequence_frames):
            return
        self.seq_listbox.selection_clear(0, tk.END)
        self.seq_listbox.selection_set(idx)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Bearbeiten", command=lambda: self.open_step_editor(idx))
        menu.add_command(label="Duplizieren", command=lambda: self._ctx_duplicate_step(idx))
        menu.add_separator()
        menu.add_command(label="Löschen", command=lambda: self._ctx_delete_step(idx))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _ctx_delete_step(self, idx):
        if 0 <= idx < len(self.sequence_frames):
            del self.sequence_frames[idx]
            self._mark_seq_unsaved()
            self.refresh_sequence_listbox()

    def _ctx_duplicate_step(self, idx):
        if 0 <= idx < len(self.sequence_frames):
            import copy
            dup = copy.deepcopy(self.sequence_frames[idx])
            dup["name"] = dup.get("name", "Step") + " (Kopie)"
            self.sequence_frames.insert(idx + 1, dup)
            self._mark_seq_unsaved()
            self.refresh_sequence_listbox()
            self.seq_listbox.selection_clear(0, tk.END)
            self.seq_listbox.selection_set(idx + 1)

    def open_step_editor(self, step_index):
        frame = self.sequence_frames[step_index]
        state = frame.get("state", {})
        pose = state.get("pose", {})
        limits = state.get("limits", {})
        velocities = state.get("velocities", {})
        sg_global = state.get("soft_grip_global", False)
        sg_motors = state.get("soft_grip_motors", {})

        editor = tk.Toplevel(self.root)
        editor.title(f"Schritt {step_index + 1} bearbeiten")
        editor.configure(bg=self.BG_COLOR)
        editor.geometry("520x680")
        editor.resizable(True, True)
        editor.transient(self.root)
        editor.grab_set()

        # --- Header ---
        hdr = tk.Label(editor, text=f"Schritt {step_index + 1}: {frame.get('name', 'Step')}",
                       bg=self.BG_COLOR, fg=self.ACCENT_BLUE, font=("Segoe UI", 12, "bold"))
        hdr.pack(pady=(10, 5))

        # --- Scrollable content ---
        canvas_edit = tk.Canvas(editor, bg=self.BG_COLOR, highlightthickness=0)
        scrollbar_edit = ttk.Scrollbar(editor, orient="vertical", command=canvas_edit.yview)
        content = tk.Frame(canvas_edit, bg=self.BG_COLOR)
        content.bind("<Configure>", lambda e: canvas_edit.configure(scrollregion=canvas_edit.bbox("all")))
        canvas_edit.create_window((0, 0), window=content, anchor="nw")
        canvas_edit.configure(yscrollcommand=scrollbar_edit.set)
        canvas_edit.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        scrollbar_edit.pack(side=tk.RIGHT, fill=tk.Y)
        canvas_edit.bind_all("<MouseWheel>", lambda e: canvas_edit.yview_scroll(-1 * (e.delta // 120), "units"))

        # === TIMING SECTION ===
        sec_time = tk.LabelFrame(content, text="Timing", bg=self.PANEL_BG, fg=self.ACCENT_BLUE,
                                 font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        sec_time.pack(fill=tk.X, pady=5)

        time_row = tk.Frame(sec_time, bg=self.PANEL_BG)
        time_row.pack(fill=tk.X)

        tk.Label(time_row, text="Zeit (ms):", bg=self.PANEL_BG, fg=self.FG_COLOR,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        edit_wait_val = tk.StringVar(value=str(frame.get("wait_val", 1000)))
        tk.Entry(time_row, textvariable=edit_wait_val, width=8, bg=self.SURFACE_BG,
                 fg=self.FG_COLOR, insertbackground=self.FG_COLOR, font=("Segoe UI", 9)).pack(side=tk.LEFT)

        # === VELOCITY GLOBAL SECTION ===
        sec_vel = tk.LabelFrame(content, text="Geschwindigkeit (Global)", bg=self.PANEL_BG, fg=self.ACCENT_BLUE,
                                font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        sec_vel.pack(fill=tk.X, pady=5)
        
        vel_row = tk.Frame(sec_vel, bg=self.PANEL_BG)
        vel_row.pack(fill=tk.X)
        
        tk.Label(vel_row, text="Alle %:", bg=self.PANEL_BG, fg=self.SUBTEXT,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(5, 4))
        
        dxl_vel_values = [velocities.get(str(d), velocities.get(d, 100)) for d in MOTOR_IDS]
        avg_vel = int(sum(dxl_vel_values) / len(dxl_vel_values)) if dxl_vel_values else 100
        
        global_vel_var = tk.IntVar(value=avg_vel)
        global_vel_lbl = tk.Label(vel_row, text=f"{avg_vel} %", bg=self.PANEL_BG, fg=self.ACCENT_PEACH,
                                  font=("Segoe UI", 9, "bold"), width=7)
        global_vel_lbl.pack(side=tk.RIGHT, padx=4)
        
        motor_vel_sliders = {}
        motor_vel_labels = {}
        
        def on_global_vel_change(val):
            v = int(float(val))
            global_vel_lbl.config(text=f"{v} %")
            for did, sl in motor_vel_sliders.items():
                sl.set(v)
                motor_vel_labels[did].config(text=f"{v} %")
                
        global_vel_slider = tk.Scale(vel_row, from_=1, to=100, orient=tk.HORIZONTAL,
                                     variable=global_vel_var, command=on_global_vel_change,
                                     bg=self.PANEL_BG, fg=self.FG_COLOR, troughcolor=self.SURFACE_BG,
                                     highlightthickness=0, length=120, showvalue=False)
        global_vel_slider.pack(side=tk.RIGHT, padx=4)

        # === SOFT-GRIP GLOBAL SECTION ===
        sec_sg = tk.LabelFrame(content, text="Soft-Close (Global)", bg=self.PANEL_BG, fg=self.ACCENT_BLUE,
                               font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        sec_sg.pack(fill=tk.X, pady=5)

        edit_sg_global = tk.BooleanVar(value=sg_global)
        sg_row = tk.Frame(sec_sg, bg=self.PANEL_BG)
        sg_row.pack(fill=tk.X)

        tk.Checkbutton(sg_row, text="Soft-Close aktiv", variable=edit_sg_global,
                       bg=self.PANEL_BG, fg=self.FG_COLOR, selectcolor=self.SURFACE_BG,
                       activebackground=self.PANEL_BG, activeforeground=self.FG_COLOR,
                       font=("Segoe UI", 9)).pack(side=tk.LEFT)

        # Global current slider
        tk.Label(sg_row, text="Alle mA:", bg=self.PANEL_BG, fg=self.SUBTEXT,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(20, 4))
        global_current_var = tk.IntVar(value=600)
        global_current_lbl = tk.Label(sg_row, text="600", bg=self.PANEL_BG, fg=self.ACCENT_PEACH,
                                      font=("Segoe UI", 9, "bold"), width=5)
        global_current_lbl.pack(side=tk.RIGHT, padx=4)

        # Store per-motor widgets for global slider callback
        motor_current_sliders = {}
        motor_current_labels = {}

        def on_global_current_change(val):
            v = int(float(val))
            global_current_lbl.config(text=str(v))
            for did, sl in motor_current_sliders.items():
                sl.set(v)
                motor_current_labels[did].config(text=str(v))

        global_current_slider = tk.Scale(sg_row, from_=0, to=1750, orient=tk.HORIZONTAL,
                                         variable=global_current_var, command=on_global_current_change,
                                         bg=self.PANEL_BG, fg=self.FG_COLOR, troughcolor=self.SURFACE_BG,
                                         highlightthickness=0, length=120, showvalue=False)
        global_current_slider.pack(side=tk.RIGHT, padx=4)

        # === PER-MOTOR SECTION ===
        sec_motors = tk.LabelFrame(content, text="Motoren (individuell)", bg=self.PANEL_BG, fg=self.ACCENT_BLUE,
                                   font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        sec_motors.pack(fill=tk.X, pady=5)

        edit_sg_motors = {}
        edit_limits = {}
        edit_ma_is_default = {}
        edit_positions = {}
        edit_velocities = {}
        pos_edit_enabled = {}

        for dxl_id in MOTOR_IDS:
            dxl_str = str(dxl_id)
            motor_name = self.motor_names.get(dxl_id, f"Motor {dxl_id}")
            has_pose = dxl_str in pose or dxl_id in pose

            card = tk.Frame(sec_motors, bg=self.SURFACE_BG, bd=1, relief=tk.GROOVE)
            card.pack(fill=tk.X, pady=3, padx=2)

            # Row 1: Motor name + Soft-Grip checkbox
            r1 = tk.Frame(card, bg=self.SURFACE_BG)
            r1.pack(fill=tk.X, padx=6, pady=(4, 2))

            tk.Label(r1, text=motor_name, bg=self.SURFACE_BG, fg=self.ACCENT_GREEN,
                     font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

            sg_val = sg_motors.get(dxl_str, "default")
            sg_display = "Ablauf-Standard" if sg_val == "default" else ("Aktiviert" if sg_val is True or sg_val == "True" else "Deaktiviert")
            sg_var = tk.StringVar(value=sg_display)
            edit_sg_motors[dxl_str] = sg_var
            
            tk.Label(r1, text="Soft-Close:", bg=self.SURFACE_BG, fg=self.SUBTEXT, font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(10, 2))
            cb_sg = ttk.Combobox(r1, textvariable=sg_var, values=["Ablauf-Standard", "Aktiviert", "Deaktiviert"],
                                 width=15, state="readonly", font=("Segoe UI", 8))
            cb_sg.pack(side=tk.LEFT, padx=2)

            # Test button
            if has_pose and self.is_connected:
                def make_test_cmd(did=dxl_id, lims=edit_limits, poss=edit_positions, vels=edit_velocities):
                    def test_cmd():
                        if not self.is_connected: return
                        if not self.ensure_torque_enabled([did]): return
                        self.serial_mutex = True
                        
                        lim_val = lims[str(did)].get()
                        self.current_vars[did].set(lim_val)
                        self.current_labels[did].config(text=str(lim_val))
                        self.packetHandler.write2ByteTxRx(self.portHandler, did, ADDR_GOAL_CURRENT, lim_val)
                        
                        # Apply test velocity
                        vel_val = vels[str(did)].get()
                        hardware_vel = int((vel_val / 100.0) * 300) if vel_val < 100 else 0
                        if hardware_vel == 0 and vel_val < 100: hardware_vel = 1
                        self.packetHandler.write4ByteTxRx(self.portHandler, did, ADDR_PROFILE_VELOCITY, hardware_vel)

                        pos_val = poss[str(did)].get()
                        self.slider_vars[did].set(pos_val)
                        self.write_goal_position(did, pos_val)
                        self.serial_mutex = False
                    return test_cmd
                ttk.Button(r1, text="Test", width=5, command=make_test_cmd()).pack(side=tk.RIGHT, padx=2)

            # Row 2: Current limit slider
            r2 = tk.Frame(card, bg=self.SURFACE_BG)
            r2.pack(fill=tk.X, padx=6, pady=1)

            tk.Label(r2, text="mA:", bg=self.SURFACE_BG, fg=self.SUBTEXT,
                     font=("Segoe UI", 8)).pack(side=tk.LEFT)

            cur_val = limits.get(dxl_str, limits.get(dxl_id, "default"))
            is_def = (cur_val == "default" or cur_val == "default_ma")
            
            ma_def_var = tk.BooleanVar(value=is_def)
            edit_ma_is_default[dxl_str] = ma_def_var
            
            slider_val = 600 if is_def else int(cur_val)
            cur_var = tk.IntVar(value=slider_val)
            edit_limits[dxl_str] = cur_var

            cur_lbl = tk.Label(r2, text="Standard" if is_def else str(slider_val), bg=self.SURFACE_BG, fg=self.ACCENT_PEACH,
                               font=("Segoe UI", 8, "bold"), width=8)
            cur_lbl.pack(side=tk.RIGHT, padx=4)
            motor_current_labels[dxl_id] = cur_lbl

            def make_cur_cb(lbl=cur_lbl):
                def cb(val):
                    lbl.config(text=str(int(float(val))))
                return cb

            cur_sl = tk.Scale(r2, from_=0, to=1750, orient=tk.HORIZONTAL, variable=cur_var,
                              command=make_cur_cb(), bg=self.SURFACE_BG, fg=self.FG_COLOR,
                              troughcolor=self.PANEL_BG, highlightthickness=0, showvalue=False,
                              state=tk.DISABLED if is_def else tk.NORMAL)
            cur_sl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            motor_current_sliders[dxl_id] = cur_sl
            
            def make_ma_def_toggle(sl=cur_sl, lbl=cur_lbl, var=cur_var, def_v=ma_def_var):
                def toggle():
                    if def_v.get():
                        sl.config(state=tk.DISABLED)
                        lbl.config(text="Standard")
                    else:
                        sl.config(state=tk.NORMAL)
                        lbl.config(text=str(var.get()))
                return toggle
                
            chk_def = ttk.Checkbutton(r2, text="Standard", variable=ma_def_var, command=make_ma_def_toggle())
            chk_def.pack(side=tk.RIGHT, padx=4)

            # Row 2b: Velocity slider
            r2b = tk.Frame(card, bg=self.SURFACE_BG)
            r2b.pack(fill=tk.X, padx=6, pady=1)

            tk.Label(r2b, text="Vel %:", bg=self.SURFACE_BG, fg=self.SUBTEXT,
                     font=("Segoe UI", 8)).pack(side=tk.LEFT)

            vel_val = velocities.get(dxl_str, velocities.get(dxl_id, 100))
            vel_var = tk.IntVar(value=vel_val)
            edit_velocities[dxl_str] = vel_var

            vel_lbl = tk.Label(r2b, text=f"{vel_val} %", bg=self.SURFACE_BG, fg=self.ACCENT_PEACH,
                               font=("Segoe UI", 8, "bold"), width=7)
            vel_lbl.pack(side=tk.RIGHT, padx=4)
            motor_vel_labels[dxl_id] = vel_lbl

            def make_vel_cb(lbl=vel_lbl):
                def cb(val):
                    lbl.config(text=f"{int(float(val))} %")
                return cb

            vel_sl = tk.Scale(r2b, from_=1, to=100, orient=tk.HORIZONTAL, variable=vel_var,
                              command=make_vel_cb(), bg=self.SURFACE_BG, fg=self.FG_COLOR,
                              troughcolor=self.PANEL_BG, highlightthickness=0, showvalue=False)
            vel_sl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            motor_vel_sliders[dxl_id] = vel_sl

            # Row 3: Position (only if this motor has a pose entry)
            if has_pose:
                r3 = tk.Frame(card, bg=self.SURFACE_BG)
                r3.pack(fill=tk.X, padx=6, pady=(1, 4))

                pos_raw = pose.get(dxl_str, pose.get(dxl_id, 0))
                pos_var = tk.IntVar(value=pos_raw)
                edit_positions[dxl_str] = pos_var

                tk.Label(r3, text="Pos:", bg=self.SURFACE_BG, fg=self.SUBTEXT,
                         font=("Segoe UI", 8)).pack(side=tk.LEFT)

                # Determine slider range from calibration
                c_zero = self.calib_zero.get(dxl_id)
                c_limit = self.calib_limit.get(dxl_id)
                if c_zero is not None and c_limit is not None:
                    pos_min = min(c_zero, c_limit)
                    pos_max = max(c_zero, c_limit)
                else:
                    pos_min = pos_raw - 2000
                    pos_max = pos_raw + 2000

                pos_lbl = tk.Label(r3, text=str(pos_raw), bg=self.SURFACE_BG, fg=self.ACCENT_YELLOW,
                                   font=("Segoe UI", 8, "bold"), width=6)
                pos_lbl.pack(side=tk.RIGHT, padx=4)

                pos_slider = tk.Scale(r3, from_=pos_min, to=pos_max, orient=tk.HORIZONTAL,
                                      variable=pos_var, bg=self.SURFACE_BG, fg=self.FG_COLOR,
                                      troughcolor=self.PANEL_BG, highlightthickness=0,
                                      showvalue=False, state=tk.DISABLED)
                pos_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

                def make_pos_cb(lbl=pos_lbl):
                    def cb(val):
                        lbl.config(text=str(int(float(val))))
                    return cb
                pos_slider.config(command=make_pos_cb())

                def make_unlock_cmd(sl=pos_slider, did=dxl_id):
                    def unlock():
                        if messagebox.askyesno("Warnung",
                                f"Bist du sicher, dass du die Zielposition von "
                                f"{self.motor_names.get(did, f'Motor {did}')} ändern willst?\n"
                                f"Eine falsche Position kann zu Kollisionen führen!",
                                parent=editor):
                            sl.config(state=tk.NORMAL)
                    return unlock

                ttk.Button(r3, text="Freigeben", width=8,
                           command=make_unlock_cmd()).pack(side=tk.LEFT, padx=4)

        # === BUTTON ROW ===
        btn_row = tk.Frame(editor, bg=self.BG_COLOR)
        btn_row.pack(fill=tk.X, pady=10, padx=10)

        def save_edits():
            # Update wait settings
            try:
                wv = int(edit_wait_val.get())
            except ValueError:
                wv = 1000
            frame["wait_type"] = "Time"
            frame["wait_val"] = wv

            # Update soft-grip global
            state["soft_grip_global"] = edit_sg_global.get()

            # Update soft-grip motors
            saved_sg_motors = {}
            for k, v in edit_sg_motors.items():
                val_str = v.get()
                if val_str == "Ablauf-Standard":
                    saved_sg_motors[k] = "default"
                elif val_str == "Aktiviert":
                    saved_sg_motors[k] = True
                else:
                    saved_sg_motors[k] = False
            state["soft_grip_motors"] = saved_sg_motors
            
            # Mark unsaved changes
            self._mark_seq_unsaved()

            # Update limits
            new_limits = {}
            for k, v in edit_limits.items():
                if edit_ma_is_default[k].get():
                    new_limits[k] = "default"
                else:
                    new_limits[k] = v.get()
            state["limits"] = new_limits

            # Update velocities
            new_velocities = {}
            for k, v in edit_velocities.items():
                new_velocities[k] = v.get()
            state["velocities"] = new_velocities

            # Update positions (only if editing was enabled)
            new_pose = dict(pose)  # Start from existing pose
            for k, v in edit_positions.items():
                new_pose[k] = v.get()
            state["pose"] = new_pose

            frame["state"] = state
            self.sequence_frames[step_index] = frame
            self.refresh_sequence_listbox()
            editor.destroy()

        ttk.Button(btn_row, text="Speichern", command=save_edits,
                   style="Success.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row, text="Abbrechen", command=editor.destroy).pack(side=tk.LEFT, padx=5)

    def save_sequence_to_file(self):
        name = self.seq_name_var.get().strip()
        if not name or not self.sequence_frames:
            messagebox.showwarning("Warnung", "Ungültiger Name oder Ablauf ist leer!")
            return
        self.saved_sequences[name] = {
            "frames": self.sequence_frames,
            "default_sg": {str(did): var.get() for did, var in self.seq_default_sg_vars.items()},
            "default_ma": {str(did): var.get() for did, var in self.seq_default_ma_vars.items()}
        }
        try:
            with open("sequences.json", "w") as f:
                json.dump(self.saved_sequences, f)
            self.update_sequence_combobox()
            self.cb_sequences.set(name)
            self.seq_unsaved_changes = False
            messagebox.showinfo("Erfolg", f"Ablauf '{name}' gespeichert!")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def load_sequences_from_file(self):
        if os.path.exists("sequences.json"):
            try:
                with open("sequences.json", "r") as f:
                    self.saved_sequences = json.load(f)
                self.update_sequence_combobox()
            except Exception as e:
                print(f"Fehler beim Laden der Sequenzen: {e}")

    def update_sequence_combobox(self):
        names = list(self.saved_sequences.keys())
        self.cb_sequences['values'] = names
        if names and not self.cb_sequences.get():
            self.cb_sequences.set(names[0])



    def _delete_selected_seq(self):
        name = self.cb_sequences.get()
        if not name or name not in self.saved_sequences:
            return
        if messagebox.askyesno("Löschen", f"Möchtest du den Ablauf '{name}' wirklich löschen?"):
            del self.saved_sequences[name]
            with open("sequences.json", "w") as f:
                json.dump(self.saved_sequences, f, indent=4)
            self.cb_sequences.set("")
            self.update_sequence_combobox()

    def open_seq_sg_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Ablauf Standard-SG Einstellungen")
        win.configure(bg=self.BG_COLOR)
        win.geometry("450x330")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        hdr = tk.Label(win, text="Standard-SG & mA Einstellungen für Ablauf",
                       bg=self.BG_COLOR, fg=self.ACCENT_BLUE, font=("Segoe UI", 11, "bold"))
        hdr.pack(pady=10)

        main_frame = tk.Frame(win, bg=self.PANEL_BG, highlightbackground=self.SURFACE_BG, highlightthickness=1)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

        # We'll use a recursive helper to apply the panel background to frames and labels
        def update_bg_recursive(w):
            c_name = w.winfo_class()
            if not c_name.startswith("T") and c_name not in ("Canvas", "Menu"):
                try:
                    w.config(bg=self.PANEL_BG)
                except tk.TclError:
                    pass
                if c_name == "Label":
                    txt = w.cget("text")
                    if txt in ("mA:", "Aktiv:"):
                        w.config(fg=self.SUBTEXT)
            for child in w.winfo_children():
                update_bg_recursive(child)

        for dxl_id in MOTOR_IDS:
            row = tk.Frame(main_frame, bg=self.PANEL_BG)
            row.pack(fill=tk.X, padx=10, pady=5)

            motor_name = self.motor_names.get(dxl_id, f"Motor {dxl_id}")
            lbl_name = tk.Label(row, text=motor_name, bg=self.PANEL_BG, fg=self.ACCENT_GREEN, font=("Segoe UI", 9, "bold"), width=12, anchor="w")
            lbl_name.pack(side=tk.LEFT)

            # Checkbox
            chk = ttk.Checkbutton(row, text="Aktiv", variable=self.seq_default_sg_vars[dxl_id],
                                  command=self._mark_seq_unsaved)
            chk.pack(side=tk.LEFT, padx=(10, 5))

            # Scale Label
            lbl_ma = tk.Label(row, text="600 mA", bg=self.PANEL_BG, fg=self.ACCENT_PEACH, font=("Segoe UI", 9, "bold"), width=8)
            
            # Slider
            def make_scale_cb(lbl=lbl_ma, var=self.seq_default_ma_vars[dxl_id]):
                def cb(val):
                    v = int(float(val))
                    if var.get() != v:
                        var.set(v)
                        self._mark_seq_unsaved()
                    lbl.config(text=f"{v} mA")
                return cb

            initial_val = self.seq_default_ma_vars[dxl_id].get()
            scale = tk.Scale(row, from_=0, to=1750, orient=tk.HORIZONTAL,
                             bg=self.PANEL_BG, fg=self.FG_COLOR, troughcolor=self.SURFACE_BG,
                             highlightthickness=0, showvalue=False, length=120)
            scale.set(initial_val)
            scale.config(command=make_scale_cb())
            scale.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            lbl_ma.config(text=f"{initial_val} mA")
            lbl_ma.pack(side=tk.RIGHT, padx=5)

        update_bg_recursive(main_frame)

        btn_close = ttk.Button(win, text="Schließen", command=win.destroy, width=12)
        btn_close.pack(pady=10)

    def _mark_seq_unsaved(self):
        self.seq_unsaved_changes = True

    def check_unsaved_sequence_changes(self):
        """
        Gibt True zurück, wenn es sicher ist fortzufahren (entweder gespeichert, verworfen oder keine Änderungen).
        Gibt False zurück, wenn der Benutzer auf Abbrechen geklickt hat.
        """
        if not self.seq_unsaved_changes or not self.sequence_frames:
            return True
            
        dialog = tk.Toplevel(self.root)
        dialog.title("Ungespeicherte Änderungen")
        dialog.geometry("400x180")
        dialog.resizable(False, False)
        dialog.configure(bg=self.BG_COLOR)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Zentriere über dem Hauptfenster
        dialog.geometry(f"+{self.root.winfo_x() + 100}+{self.root.winfo_y() + 100}")
        
        lbl_msg = tk.Label(dialog, text="Du hast ungespeicherte Änderungen im Ablauf.\nMöchtest du diese jetzt speichern?",
                           bg=self.BG_COLOR, fg=self.FG_COLOR, font=("Segoe UI", 10))
        lbl_msg.pack(pady=(15, 10))
        
        name_row = tk.Frame(dialog, bg=self.BG_COLOR)
        name_row.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(name_row, text="Name:", bg=self.BG_COLOR, fg=self.SUBTEXT, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        
        default_name = self.seq_name_var.get().strip() or "MeinAblauf"
        name_var = tk.StringVar(value=default_name)
        ent_name = ttk.Entry(name_row, textvariable=name_var, font=("Segoe UI", 9))
        ent_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        btn_frame = tk.Frame(dialog, bg=self.BG_COLOR)
        btn_frame.pack(pady=15)
        
        result = tk.StringVar(value="cancel")
        
        def on_save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Warnung", "Bitte gib einen Namen ein!", parent=dialog)
                return
            
            self.seq_name_var.set(name)
            self.saved_sequences[name] = {
                "frames": self.sequence_frames,
                "default_sg": {str(did): var.get() for did, var in self.seq_default_sg_vars.items()},
                "default_ma": {str(did): var.get() for did, var in self.seq_default_ma_vars.items()}
            }
            try:
                with open("sequences.json", "w") as f:
                    json.dump(self.saved_sequences, f)
                self.update_sequence_combobox()
                self.cb_sequences.set(name)
                self.seq_unsaved_changes = False
                result.set("save")
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Fehler", f"Konnte Ablauf nicht speichern:\n{e}", parent=dialog)
                
        def on_discard():
            self.seq_unsaved_changes = False
            result.set("discard")
            dialog.destroy()
            
        def on_cancel():
            result.set("cancel")
            dialog.destroy()
            
        btn_save = ttk.Button(btn_frame, text="Speichern", command=on_save, style="Success.TButton", width=11)
        btn_save.pack(side=tk.LEFT, padx=5)
        
        btn_discard = ttk.Button(btn_frame, text="Verwerfen", command=on_discard, style="Danger.TButton", width=11)
        btn_discard.pack(side=tk.LEFT, padx=5)
        
        btn_cancel = ttk.Button(btn_frame, text="Abbrechen", command=on_cancel, width=11)
        btn_cancel.pack(side=tk.LEFT, padx=5)
        
        dialog.wait_window()
        return result.get() in ("save", "discard")

    def load_selected_sequence(self):
        name = self.cb_sequences.get()
        if name in self.saved_sequences:
            seq_data = self.saved_sequences[name]
            # Reset default SG and mA first
            for var in self.seq_default_sg_vars.values():
                var.set(False)
            for var in self.seq_default_ma_vars.values():
                var.set(600)
            
            if isinstance(seq_data, dict):
                raw_frames = seq_data.get("frames", [])
                
                # Load default SG
                defaults_sg = seq_data.get("default_sg", {})
                for k, v in defaults_sg.items():
                    did = int(k)
                    if did in self.seq_default_sg_vars:
                        self.seq_default_sg_vars[did].set(v)
                        
                # Load default mA
                defaults_ma = seq_data.get("default_ma", {})
                for k, v in defaults_ma.items():
                    did = int(k)
                    if did in self.seq_default_ma_vars:
                        self.seq_default_ma_vars[did].set(int(v))
            else:
                raw_frames = seq_data

            frames = []
            for f in raw_frames:
                if "pose" in f and "state" not in f:
                    # Upgrade from old format
                    frames.append({
                        "name": "Legacy", 
                        "state": {"pose": f["pose"], "limits": {}},
                        "wait_type": "Time",
                        "wait_val": f.get("delay", 1000)
                    })
                else:
                    frames.append(f)
            self.sequence_frames = frames
            self.seq_name_var.set(name)
            self.refresh_sequence_listbox()
            self.seq_unsaved_changes = False

    def play_sequence(self):
        if not self.is_connected or len(self.sequence_frames) == 0: return
        if self.is_playing: return 
        active_ids = [did for did in MOTOR_IDS if self.ui_sync_checkboxes[did].instate(['selected'])]
        if not self.ensure_torque_enabled(active_ids): return
        self.is_playing = True
        self.btn_play_seq.config(state=tk.DISABLED, text="▶ Spielt ab...")
        self.lbl_seq_status.config(text="Status: Initialisiere...")
        self.seq_listbox.selection_clear(0, tk.END)
        self.root.after(0, self._play_step, 0)

    def _play_step(self, step_index):
        if not self.is_connected or step_index >= len(self.sequence_frames) or not self.is_playing:
            self.is_playing = False
            self.btn_play_seq.config(state=tk.NORMAL,
                                     text=f"▶ Start ({len(self.sequence_frames)})")
            self.lbl_seq_status.config(text="Status: Bereit")
            self.seq_listbox.selection_clear(0, tk.END)
            return

        self.seq_listbox.selection_clear(0, tk.END)
        self.seq_listbox.selection_set(step_index)
        self.seq_listbox.see(step_index)

        frame = self.sequence_frames[step_index]
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
        if not self.is_playing or not self.is_connected: return
        if remaining_ms <= 0:
            self._play_step(step_index + 1)
        else:
            self.lbl_seq_status.config(text=f"Time: {remaining_ms/1000.0:.1f}s")
            self.root.after(100, self._wait_time_loop, step_index, remaining_ms - 100)

    def _check_grasp(self, step_index, active_ids, timeout_ms, start_t):
        """Verbesserte Grasp-Erkennung mit robuster Kontakterkennung (Feature 3)"""
        if not self.is_playing or not self.is_connected: return
        
        elapsed = (time.time() - start_t) * 1000
        rem = max(0, timeout_ms - elapsed)
        self.lbl_seq_status.config(text=f"Grasp: Warte auf Kontakt ({rem/1000.0:.1f}s Timeout)")
        
        if elapsed > timeout_ms:
            self._play_step(step_index + 1)
            return
            
        # Nutze die verbesserte Kontakterkennung (Feature 3)
        all_contact = True
        for dxl_id in active_ids:
            contact_state = self.detect_contact(dxl_id)
            if contact_state != "contact":
                all_contact = False
                break
                    
        if all_contact and active_ids:
            self.lbl_seq_status.config(text="Grasp: Kontakt erkannt! ✓")
            self.root.after(100, self._play_step, step_index + 1)
        else:
            self.root.after(50, self._check_grasp, step_index, active_ids, timeout_ms, start_t)

    # =================================================================
    # --- HARDWARE BRIDGE ---
    # =================================================================

    def toggle_connection(self):
        if not self.is_connected:
            try:
                if not self.portHandler.openPort(): raise Exception("Port Open Failed.")
                if not self.portHandler.setBaudRate(BAUDRATE): raise Exception("Baudrate Failed.")

                self.is_connected = True
                self.lbl_status.config(text="⬤ ONLINE", foreground=self.ACCENT_GREEN)
                self.btn_connect.config(text="Disconnect")

                self.master_slider.config(state=tk.NORMAL)
                self.master_vel_slider.config(state=tk.NORMAL)
                self.btn_home.config(state=tk.NORMAL)
                self.btn_save_pose.config(state=tk.NORMAL)
                self.btn_play_seq.config(state=tk.NORMAL)
                
                for dxl_id in MOTOR_IDS:
                    self.ui_torque_checkboxes[dxl_id].config(state=tk.NORMAL)
                    self.ui_mode_checkboxes[dxl_id].config(state=tk.NORMAL)
                    self.ui_btn_zero[dxl_id].config(state=tk.NORMAL)
                    self.ui_btn_limit[dxl_id].config(state=tk.NORMAL)
                    
                    # Set initial mode based on mode_vars
                    self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
                    if self.mode_vars[dxl_id].get():
                        mode_val = OP_MODE_VELOCITY
                        self.ui_indiv_sliders[dxl_id].config(state=tk.NORMAL, from_=MIN_VEL_LIMIT, to=MAX_VEL_LIMIT)
                        self.slider_vars[dxl_id].set(0)
                    else:
                        mode_val = OP_MODE_CURRENT_BASED_POSITION
                        
                    self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_OPERATING_MODE, mode_val)
                    
                    self.ui_current_sliders[dxl_id].config(state=tk.NORMAL)
                    self.packetHandler.write2ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_CURRENT, 600)
                    self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_PROFILE_ACCELERATION, 100)
                    self.calculate_reboot_offset(dxl_id)

                self.on_master_vel_move(100) 
                self.root.after(100, self.async_telemetry_scanner)

            except Exception as e:
                messagebox.showerror("Connection Failed", str(e))
        else:
            self.is_connected = False
            self.serial_mutex = True
            try:
                for dxl_id in MOTOR_IDS:
                    if self.mode_vars[dxl_id].get():
                        self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_VELOCITY, 0)

                    self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
                    self.torque_vars[dxl_id].set(False)

                self.portHandler.closePort()
                self.lbl_status.config(text="⬤ OFFLINE", foreground=self.ACCENT_RED)
                self.btn_connect.config(text=f"Connect ({COM_PORT})")
            except Exception as e:
                print(f"Fehler beim Trennen der Verbindung: {e}")
            finally:
                self.serial_mutex = False

    def emergency_stop(self):
        if not self.is_connected: return
        self.is_playing = False
        self.btn_play_seq.config(state=tk.NORMAL)
        
        # Soft-Grip deaktivieren
        self.soft_grip_global.set(False)
        self._update_soft_grip_global_button()
        for dxl_id in MOTOR_IDS:
            self.soft_grip_vars[dxl_id].set(False)
            self.soft_grip_frozen[dxl_id] = False
        
        # Immediate direct command without full mutex to ensure fast stop
        for dxl_id in MOTOR_IDS:
            self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
            self.torque_vars[dxl_id].set(False)
            
        messagebox.showwarning("EMERGENCY STOP", "Alle Motoren wurden deaktiviert!")

    def safe_quit(self):
        # Check unsaved changes first
        if not self.check_unsaved_sequence_changes():
            return
            
        if messagebox.askyesno("Beenden", "Möchtest du das Programm wirklich beenden?"):
            self._save_window_geometry()
            if self.is_connected:
                # Schalte Motoren sicher ab
                self.is_playing = False
                for dxl_id in MOTOR_IDS:
                    self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
                self.portHandler.closePort()
            self.root.quit()

    def _save_window_geometry(self):
        try:
            geo = self.root.geometry()
            with open("window_layout.json", "w") as f:
                json.dump({"geometry": geo, "dark_mode": self.is_dark_mode}, f)
        except Exception:
            pass

    def _load_window_geometry(self):
        try:
            if os.path.exists("window_layout.json"):
                with open("window_layout.json", "r") as f:
                    data = json.load(f)
                geo = data.get("geometry")
                if geo:
                    self.root.geometry(geo)
                if not data.get("dark_mode", True):
                    self.toggle_theme()
        except Exception:
            pass

    def auto_scan_motors(self):
        if not self.is_connected:
            messagebox.showwarning("Nicht verbunden", "Bitte erst verbinden, dann scannen.")
            return
        
        self.serial_mutex = True
        found = []
        try:
            for test_id in range(21):
                model, res, _ = self.packetHandler.ping(self.portHandler, test_id)
                if res == COMM_SUCCESS:
                    found.append(test_id)
        except Exception as e:
            print(f"Fehler beim Scannen der Motoren: {e}")
        finally:
            self.serial_mutex = False
        
        if found:
            ids_str = ", ".join(str(i) for i in found)
            messagebox.showinfo("Scan Ergebnis", f"Gefundene Motoren:\n\nIDs: {ids_str}\n\n"
                                f"Aktuell konfiguriert: {MOTOR_IDS}\n\n"
                                f"Wenn die IDs nicht übereinstimmen, passe MOTOR_IDS im Code an.")
        else:
            messagebox.showwarning("Scan Ergebnis", "Keine Motoren gefunden!\n\n"
                                   "Prüfe Kabel, Stromversorgung und COM-Port.")

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        
        if self.is_dark_mode:
            self.BG_COLOR = "#1e1e2e"
            self.FG_COLOR = "#cdd6f4"
            self.ACCENT_BLUE = "#89b4fa"
            self.ACCENT_GREEN = "#a6e3a1"
            self.ACCENT_RED = "#f38ba8"
            self.ACCENT_YELLOW = "#f9e2af"
            self.ACCENT_PEACH = "#fab387"
            self.PANEL_BG = "#313244"
            self.SURFACE_BG = "#45475a"
            self.SUBTEXT = "#a6adc8"
            self.motor_colors = ["#f38ba8", "#a6e3a1", "#89b4fa", "#f9e2af", "#cba6f7"]
            self.btn_theme.config(text="Light Mode")
        else:
            self.BG_COLOR = "#f5f5f5"
            self.FG_COLOR = "#1e1e2e"
            self.ACCENT_BLUE = "#1a73e8"
            self.ACCENT_GREEN = "#2e7d32"  # Much darker green
            self.ACCENT_RED = "#c62828"    # Much darker red
            self.ACCENT_YELLOW = "#f57f17" # Much darker yellow/orange
            self.ACCENT_PEACH = "#d84315"  # Much darker orange
            self.PANEL_BG = "#e8e8e8"
            self.SURFACE_BG = "#d4d4d4"
            self.SUBTEXT = "#5f6368"
            self.motor_colors = ["#d32f2f", "#2e7d32", "#1565c0", "#e65100", "#6a1b9a"]  # High contrast dark colors
            self.btn_theme.config(text="Dark Mode")
        
        self._apply_theme()

    def _apply_theme(self):
        self.root.configure(bg=self.BG_COLOR)
        
        if hasattr(self, 'paned') and self.paned:
            self.paned.configure(bg=self.BG_COLOR)
        if hasattr(self, 'left_outer') and self.left_outer:
            self.left_outer.configure(bg=self.BG_COLOR)
        if hasattr(self, 'canvas_left') and self.canvas_left:
            self.canvas_left.configure(bg=self.BG_COLOR)
        if hasattr(self, 'right_frame') and self.right_frame:
            self.right_frame.configure(bg=self.BG_COLOR)
            
        select_fg = "#1e1e2e" if self.is_dark_mode else "#ffffff"
        
        # ttk styles
        self.style.configure(".", background=self.BG_COLOR, foreground=self.FG_COLOR, font=("Segoe UI", 10))
        self.style.configure("TLabel", background=self.BG_COLOR, foreground=self.FG_COLOR)
        self.style.configure("Panel.TLabel", background=self.PANEL_BG, foreground=self.FG_COLOR)
        self.style.configure("Panel.TFrame", background=self.PANEL_BG)
        self.style.configure("Surface.TFrame", background=self.SURFACE_BG)
        self.style.configure("TFrame", background=self.BG_COLOR)
        self.style.configure("TLabelframe", background=self.PANEL_BG, foreground=self.ACCENT_BLUE, borderwidth=1, font=("Segoe UI", 10, "bold"))
        self.style.configure("TLabelframe.Label", background=self.PANEL_BG, foreground=self.ACCENT_BLUE)
        self.style.configure("TButton", background=self.SURFACE_BG, foreground=self.FG_COLOR, borderwidth=0, padding=4, font=("Segoe UI", 9))
        self.style.map("TButton", background=[("active", self.ACCENT_BLUE)], foreground=[("active", select_fg)])
        self.style.configure("Primary.TButton", background=self.ACCENT_BLUE, foreground=select_fg, font=("Segoe UI", 9, "bold"))
        self.style.configure("Danger.TButton", background=self.ACCENT_RED, foreground=select_fg, font=("Segoe UI", 9, "bold"))
        self.style.configure("Success.TButton", background=self.ACCENT_GREEN, foreground=select_fg, font=("Segoe UI", 9, "bold"))
        self.style.configure("Toggle.TButton", background=self.SURFACE_BG, foreground=self.SUBTEXT, font=("Segoe UI", 9))
        self.style.configure("ToggleOn.TButton", background=self.ACCENT_GREEN, foreground=select_fg, font=("Segoe UI", 9, "bold"))
        self.style.configure("TCheckbutton", background=self.BG_COLOR, foreground=self.FG_COLOR)
        self.style.map("TCheckbutton", background=[("active", self.BG_COLOR)], indicatorcolor=[("selected", self.ACCENT_BLUE)])
        self.style.configure("Panel.TCheckbutton", background=self.PANEL_BG, foreground=self.FG_COLOR)
        self.style.map("Panel.TCheckbutton", background=[("active", self.PANEL_BG)], indicatorcolor=[("selected", self.ACCENT_BLUE)])
        self.style.configure("Horizontal.TScale", background=self.BG_COLOR, troughcolor=self.SURFACE_BG)
        self.style.configure("Panel.Horizontal.TScale", background=self.PANEL_BG, troughcolor=self.SURFACE_BG)
        self.style.configure("TEntry", fieldbackground=self.SURFACE_BG, foreground=self.FG_COLOR, insertcolor=self.FG_COLOR)
        self.style.map("TEntry", selectbackground=[("focus", self.ACCENT_BLUE)], selectforeground=[("focus", select_fg)])
        self.style.configure("TCombobox", fieldbackground=self.SURFACE_BG, foreground=self.FG_COLOR, background=self.SURFACE_BG)
        self.style.map("TCombobox", fieldbackground=[("readonly", self.SURFACE_BG)], 
                       selectbackground=[("readonly", self.ACCENT_BLUE)], selectforeground=[("readonly", select_fg)])
        
        # Update tk widgets that don't follow ttk styles automatically
        graph_bg = "#11111b" if self.is_dark_mode else "#ffffff"
        self.canvas.config(bg=graph_bg)
        
        # Update seq_listbox
        select_fg = "#1e1e2e" if self.is_dark_mode else "#ffffff"
        self.seq_listbox.config(bg=self.SURFACE_BG, fg=self.FG_COLOR, selectbackground=self.ACCENT_BLUE, selectforeground=select_fg)
        
        # Update motor card backgrounds and borders recursively
        def update_bg_recursive(w):
            c_name = w.winfo_class()
            if not c_name.startswith("T") and c_name not in ("Canvas", "Menu"):
                try:
                    if c_name == "Frame":
                        w.config(bg=self.PANEL_BG, highlightbackground=self.SURFACE_BG)
                    else:
                        w.config(bg=self.PANEL_BG)
                except tk.TclError:
                    pass
                if c_name == "Label":
                    txt = w.cget("text")
                    if txt in ("Pos:", "mA:", "Vel %:"):
                        w.config(fg=self.SUBTEXT)
                    elif txt.startswith("#"):
                        w.config(fg=self.SUBTEXT)
            for child in w.winfo_children():
                update_bg_recursive(child)

        for dxl_id in MOTOR_IDS:
            card = self.motor_cards.get(dxl_id)
            if card:
                update_bg_recursive(card)
            
            # Explicitly update dynamic label foregrounds inside motor cards
            if dxl_id in self.current_labels:
                self.current_labels[dxl_id].config(fg=self.FG_COLOR)
            if dxl_id in self.readout_labels:
                self.readout_labels[dxl_id].config(fg=self.FG_COLOR)
            if dxl_id in self.temp_labels:
                curr_fg = self.temp_labels[dxl_id].cget("fg")
                if curr_fg in ("#f38ba8", "#c62828"):
                    self.temp_labels[dxl_id].config(fg=self.ACCENT_RED)
                else:
                    self.temp_labels[dxl_id].config(fg=self.ACCENT_GREEN)
            if dxl_id in self.error_labels:
                curr_fg = self.error_labels[dxl_id].cget("fg")
                if curr_fg in ("#f38ba8", "#c62828"):
                    self.error_labels[dxl_id].config(fg=self.ACCENT_RED)
                else:
                    self.error_labels[dxl_id].config(fg=self.ACCENT_GREEN)
            if dxl_id in self.contact_labels:
                # Refresh contact labels color based on state
                state = self.detect_contact(dxl_id)
                if state == "contact":
                    self.contact_labels[dxl_id].config(fg=self.ACCENT_GREEN)
                elif state == "approaching":
                    self.contact_labels[dxl_id].config(fg=self.ACCENT_YELLOW)
                else:
                    self.contact_labels[dxl_id].config(fg=self.SUBTEXT)
        
        # Update sequence status label color
        self.lbl_seq_status.config(foreground=self.ACCENT_GREEN)
        
        # Update motor colors & legend colors
        for idx, dxl_id in enumerate(MOTOR_IDS):
            c = self.motor_colors[idx % len(self.motor_colors)]
            if dxl_id in self.motor_name_labels:
                self.motor_name_labels[dxl_id].config(fg=c)
            if dxl_id in self.graph_indicators:
                self.graph_indicators[dxl_id]["label"].config(fg=c)
                self.graph_indicators[dxl_id]["color"] = c

    def toggle_torque_all(self):
        if not self.is_connected: return
        self.serial_mutex = True
        
        # Prüfen ob irgendein Motor aus ist -> Wenn ja, schalte alle ein. Ansonsten alle aus.
        any_off = any(not self.torque_vars[dxl_id].get() for dxl_id in MOTOR_IDS)
        
        for dxl_id in MOTOR_IDS:
            self.torque_vars[dxl_id].set(any_off)
            self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 1 if any_off else 0)
            
        self.serial_mutex = False

    def ensure_torque_enabled(self, dxl_ids=None):
        if not self.is_connected: return False
        if dxl_ids is None:
            dxl_ids = MOTOR_IDS
            
        off_ids = [did for did in dxl_ids if not self.torque_vars[did].get()]
        if not off_ids:
            return True
            
        # Ask user
        names = [self.motor_names[did] for did in off_ids]
        msg = "Das Drehmoment (Torque) ist für folgende Motoren deaktiviert:\n\n"
        msg += "\n".join(f"- {n}" for n in names)
        msg += "\n\nMöchtest du Torque für diese Motoren jetzt aktivieren, um die Bewegung auszuführen?"
        
        if messagebox.askyesno("Torque aktivieren?", msg):
            self.serial_mutex = True
            for did in off_ids:
                self.torque_vars[did].set(True)
                self.packetHandler.write1ByteTxRx(self.portHandler, did, ADDR_TORQUE_ENABLE, 1)
            self.serial_mutex = False
            return True
        return False



    def reboot_motor(self, dxl_id):
        if not self.is_connected: return
        if not messagebox.askyesno("Motor Neustart", f"Möchtest du Motor ID {dxl_id} wirklich neu starten?\n(Das löscht alle aktuellen Hardware-Fehler)"):
            return
            
        self.serial_mutex = True
        try:
            # Torque aus zur Sicherheit
            self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)
            self.torque_vars[dxl_id].set(False)

            # SDK Reboot command
            res, error = self.packetHandler.reboot(self.portHandler, dxl_id)

            if res == COMM_SUCCESS:
                print(f"Motor {dxl_id} erfolgreich neugestartet.")
                self.error_labels[dxl_id].config(text="✓", fg=self.ACCENT_GREEN)

                # Kurze Pause damit der Motor wieder online kommt
                self.root.update()
                time.sleep(0.5)

                # RAM-Parameter wiederherstellen, da diese beim Reboot gelöscht werden
                mode_val = OP_MODE_VELOCITY if self.mode_vars[dxl_id].get() else OP_MODE_CURRENT_BASED_POSITION
                self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_OPERATING_MODE, mode_val)

                limit_val = self.current_vars[dxl_id].get()
                self.packetHandler.write2ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_CURRENT, limit_val)

                master_vel_percent = self.master_vel_var.get()
                hardware_vel = int((master_vel_percent / 100.0) * 300) if master_vel_percent < 100 else 0
                if hardware_vel == 0 and master_vel_percent < 100: hardware_vel = 1
                self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_PROFILE_VELOCITY, hardware_vel)
                self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_PROFILE_ACCELERATION, 100)
                self.calculate_reboot_offset(dxl_id)

            else:
                print(f"Fehler beim Neustart von Motor {dxl_id}: {self.packetHandler.getTxRxResult(res)}")
                messagebox.showerror("Reboot Failed", f"Motor {dxl_id} konnte nicht neu gestartet werden.")
        except Exception as e:
            print(f"Fehler beim Neustart von Motor {dxl_id}: {e}")
        finally:
            self.serial_mutex = False

    def on_torque_check(self, dxl_id):
        if not self.is_connected: return
        self.serial_mutex = True
        try:
            enable = 1 if self.torque_vars[dxl_id].get() else 0
            self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, enable)
            if enable:
                # The first slider action after re-enabling torque must always be
                # sent, even if it happens to match the last target.
                self._last_slider_targets.pop(dxl_id, None)

            if enable and self.mode_vars[dxl_id].get():
                self.packetHandler.write4ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_VELOCITY, 0)
                self.slider_vars[dxl_id].set(0)
        except Exception as e:
            print(f"Fehler beim Umschalten von Torque (ID {dxl_id}): {e}")
        finally:
            self.serial_mutex = False

    def on_mode_toggle(self, dxl_id):
        if not self.is_connected: return
        self.serial_mutex = True
        try:
            is_endless = self.mode_vars[dxl_id].get()
            was_torque_on = self.torque_vars[dxl_id].get()

            if was_torque_on:
                self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 0)

            if is_endless:
                self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id,
                                                 ADDR_OPERATING_MODE, OP_MODE_VELOCITY)
                self.ui_indiv_sliders[dxl_id].config(state=tk.NORMAL, from_=MIN_VEL_LIMIT, to=MAX_VEL_LIMIT)
                self.slider_vars[dxl_id].set(0)
            else:
                self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id,
                                                 ADDR_OPERATING_MODE, OP_MODE_CURRENT_BASED_POSITION)
                if self.calib_zero[dxl_id] is not None and self.calib_limit[dxl_id] is not None:
                    self.check_calibration_status(dxl_id)
                else:
                    self.ui_indiv_sliders[dxl_id].config(state=tk.DISABLED)

            if was_torque_on:
                self.packetHandler.write1ByteTxRx(self.portHandler, dxl_id, ADDR_TORQUE_ENABLE, 1)
        except Exception as e:
            print(f"Fehler beim Wechseln des Modus (ID {dxl_id}): {e}")
        finally:
            self.serial_mutex = False

    def on_slider_release(self, event, dxl_id):
        if not self.is_connected or not self.torque_vars[dxl_id].get(): return
        if self.mode_vars[dxl_id].get():
            self.slider_vars[dxl_id].set(0)            
            self.on_indiv_slider_move(dxl_id, 0)
        else:
            # Do not leave the final mouse position waiting for the next timer.
            self._flush_indiv_slider_command(dxl_id, force=True)

    def on_current_slider_release(self, event, dxl_id):
        if not self.is_connected: return
        val = self.current_vars[dxl_id].get()
        self.on_current_slider_move(dxl_id, val)

    def on_current_slider_move(self, dxl_id, val):
        if not self.is_connected: return
        self.serial_mutex = True
        try:
            target = int(float(val))
            self.current_labels[dxl_id].config(text=f"{target}")
            self.packetHandler.write2ByteTxRx(self.portHandler, dxl_id, ADDR_GOAL_CURRENT, target)
        except Exception as e:
            print(f"Fehler beim Senden des Strom-Limits (ID {dxl_id}): {e}")
        finally:
            self.serial_mutex = False

    def on_indiv_slider_move(self, dxl_id, val):
        if getattr(self, 'is_programmatic_change', False): return
        if not self.is_connected or not self.torque_vars[dxl_id].get() or self.is_playing: return
        
        # Soft-Grip: Unfreeze wenn User manuell bewegt
        self.soft_grip_frozen[dxl_id] = False
        
        target = int(float(val))
        self._pending_slider_targets[dxl_id] = target

        # Schedule at most one pending transmission for this motor.  A rapid
        # drag merely replaces its target, so the motor receives the latest
        # position without a backlog of stale commands.
        if dxl_id not in self._slider_send_jobs:
            self._slider_send_jobs[dxl_id] = self.root.after(
                self._slider_send_interval_ms,
                lambda did=dxl_id: self._flush_indiv_slider_command(did)
            )

    def _flush_indiv_slider_command(self, dxl_id, force=False):
        """Send the latest queued individual-slider command safely."""
        job = self._slider_send_jobs.pop(dxl_id, None)
        if force and job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass

        if (not self.is_connected or not self.torque_vars[dxl_id].get()
                or self.is_playing or dxl_id not in self._pending_slider_targets):
            self._pending_slider_targets.pop(dxl_id, None)
            return

        # A telemetry or configuration operation owns the bus; retry shortly
        # instead of interleaving packet traffic.
        if self.serial_mutex:
            self._slider_send_jobs[dxl_id] = self.root.after(
                10, lambda did=dxl_id: self._flush_indiv_slider_command(did)
            )
            return

        target = self._pending_slider_targets.pop(dxl_id)
        mode_is_velocity = self.mode_vars[dxl_id].get()
        command_key = (mode_is_velocity, target)
        if not force and self._last_slider_targets.get(dxl_id) == command_key:
            return

        self.serial_mutex = True
        try:
            if mode_is_velocity:
                self.packetHandler.write4ByteTxRx(
                    self.portHandler, dxl_id, ADDR_GOAL_VELOCITY, target & 0xFFFFFFFF
                )
                self.readout_labels[dxl_id].config(text=f"Spd: {target}")
            else:
                self.write_goal_position(dxl_id, target)
            self._last_slider_targets[dxl_id] = command_key
        except Exception as e:
            print(f"Fehler beim Senden der Slider-Position (ID {dxl_id}): {e}")
        finally:
            self.serial_mutex = False

    def on_master_slider_move(self, val):
        new_val = float(val)
        if getattr(self, 'is_programmatic_change', False):
            self.last_master_val = new_val
            return

        percent = float(val) / 100.0
        old_val = getattr(self, 'last_master_val', 0.0)
        delta_pct = (new_val - old_val) / 100.0
        self.last_master_val = new_val

        if not self.is_connected or self.is_playing: return
        
        self.is_programmatic_change = True
        self.serial_mutex = True
        try:
            self.lbl_master_pos.config(text=f"{new_val:.1f} %")

            self.sync_write_pos.clearParam()

            for dxl_id in MOTOR_IDS:
                c_zero = self.calib_zero[dxl_id]
                c_limit = self.calib_limit[dxl_id]

                if (self.sync_vars[dxl_id].get() and not self.mode_vars[dxl_id].get()
                        and c_zero is not None and c_limit is not None):
                    current_pos = self.slider_vars[dxl_id].get()
                    range_ticks = c_limit - c_zero
                    target_pos = int(current_pos + delta_pct * range_ticks)

                    min_pos = min(c_zero, c_limit)
                    max_pos = max(c_zero, c_limit)
                    target_pos = max(min_pos, min(max_pos, target_pos))

                    self.slider_vars[dxl_id].set(target_pos)
                    self.soft_grip_frozen[dxl_id] = False  # Unfreeze bei Master-Bewegung

            if not getattr(self, '_master_sync_pending', False):
                self._master_sync_pending = True
                self.root.after(20, self._transmit_master_sync)
        except Exception as e:
            print(f"Fehler bei Master-Slider-Bewegung: {e}")
        finally:
            self.serial_mutex = False
            self.is_programmatic_change = False

    def _transmit_master_sync(self):
        self._master_sync_pending = False
        if not self.is_connected: return
        
        self.serial_mutex = True
        try:
            self.sync_write_pos.clearParam()
            has_targets = False

            for dxl_id in MOTOR_IDS:
                if self.sync_vars[dxl_id].get() and not self.mode_vars[dxl_id].get() and self.torque_vars[dxl_id].get():
                    target_pos = self.slider_vars[dxl_id].get()
                    offset = self.reboot_offsets.get(dxl_id, 0)
                    raw_pos = int(target_pos - offset) & 0xFFFFFFFF
                    param_pos = [
                        raw_pos & 0xFF,
                        (raw_pos >> 8) & 0xFF,
                        (raw_pos >> 16) & 0xFF,
                        (raw_pos >> 24) & 0xFF
                    ]
                    self.sync_write_pos.addParam(dxl_id, param_pos)
                    has_targets = True

            if has_targets:
                self.sync_write_pos.txPacket()
        except Exception as e:
            print(f"Fehler beim Senden der Master-Sync Position: {e}")
        finally:
            self.serial_mutex = False

    def on_master_slider_release(self, event):
        self.is_programmatic_change = True
        self.master_slider_var.set(0.0)
        self.lbl_master_pos.config(text="0.0 %")
        self.last_master_val = 0.0
        self.is_programmatic_change = False

    def on_master_vel_move(self, val):
        if not self.is_connected: return
        percent = int(float(val))
        self.serial_mutex = True
        self.master_vel_var.set(percent)
        
        if percent >= 100:
            hardware_vel = 0
            self.lbl_master_vel.config(text="Vel: 100 % (Max)")
        else:
            hardware_vel = int((percent / 100.0) * 300)
            if hardware_vel == 0: hardware_vel = 1
            self.lbl_master_vel.config(text=f"Vel: {percent} %")

        self.sync_write_profile_vel.clearParam()
        param_vel = [
            hardware_vel & 0xFF,
            (hardware_vel >> 8) & 0xFF,
            (hardware_vel >> 16) & 0xFF,
            (hardware_vel >> 24) & 0xFF
        ]
        for dxl_id in MOTOR_IDS:
            self.sync_write_profile_vel.addParam(dxl_id, param_vel)
        self.sync_write_profile_vel.txPacket()
        self.serial_mutex = False

    # =================================================================
    # --- TELEMETRIE & MONITORING ---
    # =================================================================

    def async_telemetry_scanner(self):
        if not self.is_connected: return

        if self.serial_mutex:
            # Watchdog: if some code path left the bus lock held (e.g. an
            # unexpected comm exception before a fix/finally could run), the
            # whole UI would otherwise appear "frozen" until Torque is
            # manually toggled. Auto-release after ~1s (10 ticks @ 100ms) so
            # it self-heals instead.
            self._mutex_busy_cycles += 1
            if self._mutex_busy_cycles > 10:
                print("[WATCHDOG] serial_mutex war zu lange blockiert - wird zurückgesetzt.")
                self.serial_mutex = False
                self._mutex_busy_cycles = 0
        else:
            self._mutex_busy_cycles = 0

        if not self.serial_mutex:
            self.serial_mutex = True
            
            # Group Sync Reads for all motors
            self.sync_read_pos.txRxPacket()
            self.sync_read_curr.txRxPacket()
            self.sync_read_temp.txRxPacket()
            self.sync_read_err.txRxPacket()
            
            warning_messages = []
            
            for dxl_id in MOTOR_IDS:
                # --- Strom auslesen ---
                res_c = COMM_SUCCESS
                if self.sync_read_curr.isAvailable(dxl_id, ADDR_PRESENT_CURRENT, 2):
                    curr = self.sync_read_curr.getData(dxl_id, ADDR_PRESENT_CURRENT, 2)
                    if curr > 32767: curr = curr - 65536
                    self.graph_history[dxl_id].append(curr)
                    
                    limit_ma = self.current_vars[dxl_id].get()
                    self.limit_history[dxl_id].append(limit_ma)
                else:
                    res_c = -1
                
                # --- Temperatur auslesen (Feature 4) ---
                res_temp = COMM_SUCCESS
                if self.sync_read_temp.isAvailable(dxl_id, ADDR_PRESENT_TEMPERATURE, 1):
                    temp = self.sync_read_temp.getData(dxl_id, ADDR_PRESENT_TEMPERATURE, 1)
                    self.temp_labels[dxl_id].config(text=f"\ud83c\udf21 {temp}\u00b0C")
                    
                    if temp > TEMP_WARN:
                        self.temp_labels[dxl_id].config(fg=self.ACCENT_RED)
                        name = self.motor_names.get(dxl_id, f"ID {dxl_id}")
                        warning_messages.append(f"\u26a0 {name}: {temp}\u00b0C!")
                    elif temp > TEMP_OK:
                        self.temp_labels[dxl_id].config(fg=self.ACCENT_YELLOW)
                    else:
                        self.temp_labels[dxl_id].config(fg=self.ACCENT_GREEN)
                else:
                    res_temp = -1
                    self.temp_labels[dxl_id].config(text="\ud83c\udf21 --\u00b0C", fg=self.SUBTEXT)
                
                # --- Hardware Error auslesen (Feature 4) ---
                res_err = COMM_SUCCESS
                if self.sync_read_err.isAvailable(dxl_id, ADDR_HARDWARE_ERROR_STATUS, 1):
                    hw_err = self.sync_read_err.getData(dxl_id, ADDR_HARDWARE_ERROR_STATUS, 1)
                    if hw_err > 0:
                        self.error_labels[dxl_id].config(text="\u26a0", fg=self.ACCENT_RED)
                        name = self.motor_names.get(dxl_id, f"ID {dxl_id}")
                        warning_messages.append(f"\u26a0 {name}: HW-Error {hw_err}")
                        if self.torque_vars[dxl_id].get():
                            self.torque_vars[dxl_id].set(False)
                    else:
                        self.error_labels[dxl_id].config(text="\u2713", fg=self.ACCENT_GREEN)
                else:
                    res_err = -1
                
                # --- Position verarbeiten ---
                res = COMM_SUCCESS
                if self.sync_read_pos.isAvailable(dxl_id, ADDR_PRESENT_POSITION, 4):
                    pos = self.sync_read_pos.getData(dxl_id, ADDR_PRESENT_POSITION, 4)
                    if pos > 2147483647: pos = pos - 4294967296
                    offset = self.reboot_offsets.get(dxl_id, 0)
                    pos = pos + offset
                    self.present_positions[dxl_id] = pos
                        
                    if not self.mode_vars[dxl_id].get():
                        self.readout_labels[dxl_id].config(text=f"Pos: {pos}", fg=self.FG_COLOR)
                        if not self.torque_vars[dxl_id].get() and self.calib_zero[dxl_id] is not None:
                            self.slider_vars[dxl_id].set(pos)
                else:
                    res = -1
                    self.readout_labels[dxl_id].config(text="[ NO ACK ]", fg=self.ACCENT_PEACH) 
            
            # --- Kontakt-Indikatoren aktualisieren (Feature 3) ---
            self.update_contact_indicators()
            
            # --- Soft-Grip verarbeiten (Feature 6) ---
            if not self.is_playing:
                self.process_soft_grip()
            
            # --- Warning Banner aktualisieren (Feature 4) ---
            if warning_messages:
                self.lbl_warning.config(text="  ".join(warning_messages))
                self.warning_frame.pack(fill=tk.X, pady=(5, 0))
            else:
                self.warning_frame.pack_forget()
            
            self.serial_mutex = False

        # --- Graph IMMER zeichnen (auch w\u00e4hrend Ablauf) ---
        self._draw_graph()

        self.root.after(100, self.async_telemetry_scanner)

    def _draw_graph(self):
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width > 10 and height > 10:
            # R\u00e4nder f\u00fcr Achsenbeschriftungen
            margin_left = 50   # Platz f\u00fcr Y-Achsen-Werte
            margin_bottom = 22 # Platz f\u00fcr X-Achsen-Beschriftung
            margin_top = 8
            margin_right = 8
            
            plot_w = width - margin_left - margin_right
            plot_h = height - margin_top - margin_bottom
            
            if plot_w < 10 or plot_h < 10:
                plot_w = max(plot_w, 10)
                plot_h = max(plot_h, 10)
            
            y_max = 1750.0
            y_scale = plot_h / y_max
            x_step = plot_w / 50.0
            
            # --- Achsenlinien ---
            # Y-Achse
            self.canvas.create_line(margin_left, margin_top, margin_left, height - margin_bottom,
                                    fill="#45475a", width=1)
            # X-Achse
            self.canvas.create_line(margin_left, height - margin_bottom, width - margin_right, height - margin_bottom,
                                    fill="#45475a", width=1)
            
            # --- Y-Achse Beschriftung & Tick-Marks ---
            self.canvas.create_text(margin_left - 5, margin_top + plot_h // 2, anchor="e",
                                    text="Strom\n(mA)", fill="#a6adc8", font=("Segoe UI", 7),
                                    justify="center")
            
            y_ticks = [0, 250, 500, 750, 1000, 1250, 1500, 1750]
            for tick_val in y_ticks:
                y_pos = (height - margin_bottom) - (tick_val * y_scale)
                if y_pos >= margin_top:
                    # Tick-Linie
                    self.canvas.create_line(margin_left - 4, y_pos, margin_left, y_pos,
                                            fill="#585b70", width=1)
                    # Tick-Beschriftung
                    self.canvas.create_text(margin_left - 6, y_pos, anchor="e",
                                            text=str(tick_val), fill="#6c7086", font=("Segoe UI", 7))
                    # Horizontale Hilfslinien (dezent)
                    if tick_val > 0:
                        self.canvas.create_line(margin_left + 1, y_pos, width - margin_right, y_pos,
                                                fill="#1e1e2e", width=1, dash=(2, 4))
            
            # --- X-Achse Beschriftung ---
            self.canvas.create_text(margin_left + plot_w // 2, height - 3, anchor="s",
                                    text="Zeit (t)", fill="#a6adc8", font=("Segoe UI", 8))
            
            for i, dxl_id in enumerate(MOTOR_IDS):
                hist = self.graph_history[dxl_id]
                color = self.graph_indicators[dxl_id]["color"]
                
                # --- Grenzlinie für Strom-Limit über Zeit (pro Motor) ---
                limit_hist = self.limit_history[dxl_id]
                limit_points = []
                for idx, val in enumerate(limit_hist):
                    x = margin_left + (idx * x_step)
                    y = (height - margin_bottom) - (val * y_scale)
                    y = max(margin_top, min(y, height - margin_bottom))
                    limit_points.extend([x, y])
                    
                if len(limit_points) >= 4:
                    self.canvas.create_line(limit_points, fill=color, width=1, dash=(6, 3))
                    
                    current_limit = limit_hist[-1]
                    limit_y = (height - margin_bottom) - (current_limit * y_scale)
                    limit_y = max(margin_top, min(limit_y, height - margin_bottom))
                    self.canvas.create_text(
                        width - margin_right - 2, limit_y - 2, anchor="se",
                        text=f"{current_limit} mA",
                        fill=color, font=("Segoe UI", 7)
                    )
                
                # Kontakt-Indikator im Graph (basierend auf Feature 3)
                contact = self.contact_states.get(dxl_id, "none")
                if contact == "contact":
                    self.graph_indicators[dxl_id]["label"].config(bg=self.ACCENT_GREEN, fg="#1e1e2e")
                elif contact == "approaching":
                    self.graph_indicators[dxl_id]["label"].config(bg=self.ACCENT_YELLOW, fg="#1e1e2e")
                else:
                    self.graph_indicators[dxl_id]["label"].config(bg=self.PANEL_BG, fg=color)
                    
                points = []
                for idx, val in enumerate(hist):
                    x = margin_left + (idx * x_step)
                    y = (height - margin_bottom) - (abs(val) * y_scale)
                    # Clamp to plot area
                    y = max(margin_top, min(y, height - margin_bottom))
                    points.extend([x, y])
                    
                if len(points) >= 4:
                    self.canvas.create_line(points, fill=color, width=2, smooth=True)

    def export_graph_menu(self):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Als Excel-Datei exportieren (.xls)", command=self.export_graph_excel)
        menu.add_command(label="Als CSV-Daten exportieren (.csv)", command=self.export_graph_csv)
        menu.add_command(label="Als Bild exportieren (.png)", command=self.export_graph_png)
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def export_graph_excel(self):
        from tkinter import filedialog
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xls",
            filetypes=[("Excel 97-2003 Arbeitsmappe", "*.xls"), ("Alle Dateien", "*.*")],
            title="Graphendaten für Excel exportieren"
        )
        if not file_path:
            return
        try:
            # Erzeuge XML Spreadsheet 2003 Struktur (wird von Excel nativ geöffnet)
            xml_lines = [
                '<?xml version="1.0" encoding="utf-8"?>',
                '<?mso-application progid="Excel.Sheet"?>',
                '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
                ' xmlns:o="urn:schemas-microsoft-com:office:office"',
                ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
                ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"',
                ' xmlns:html="http://www.w3.org/TR/REC-html40">',
                ' <Worksheet ss:Name="Graphendaten">',
                '  <Table>'
            ]
            
            # Header Zeile
            xml_lines.append('   <Row>')
            xml_lines.append('    <Cell><Data ss:Type="String">Index</Data></Cell>')
            for dxl_id in MOTOR_IDS:
                name = self.motor_names.get(dxl_id, f"Motor_{dxl_id}")
                xml_lines.append(f'    <Cell><Data ss:Type="String">{name} Strom (mA)</Data></Cell>')
                xml_lines.append(f'    <Cell><Data ss:Type="String">{name} Limit (mA)</Data></Cell>')
            xml_lines.append('   </Row>')
            
            # Daten Zeilen
            for idx in range(50):
                xml_lines.append('   <Row>')
                xml_lines.append(f'    <Cell><Data ss:Type="Number">{idx}</Data></Cell>')
                for dxl_id in MOTOR_IDS:
                    curr = self.graph_history[dxl_id][idx]
                    lim = self.limit_history[dxl_id][idx]
                    xml_lines.append(f'    <Cell><Data ss:Type="Number">{curr}</Data></Cell>')
                    xml_lines.append(f'    <Cell><Data ss:Type="Number">{lim}</Data></Cell>')
                xml_lines.append('   </Row>')
                
            xml_lines.extend([
                '  </Table>',
                ' </Worksheet>',
                '</Workbook>'
            ])
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(xml_lines))
                
            messagebox.showinfo("Erfolg", f"Excel-kompatible Datei erfolgreich exportiert nach:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Excel-Datei nicht exportieren:\n{e}")

    def export_graph_csv(self):
        from tkinter import filedialog
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
            title="Graphendaten exportieren"
        )
        if not file_path:
            return
        try:
            import csv
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                header = ["Index"]
                for dxl_id in MOTOR_IDS:
                    name = self.motor_names.get(dxl_id, f"Motor_{dxl_id}")
                    header.extend([f"{name}_Strom_mA", f"{name}_Limit_mA"])
                writer.writerow(header)
                for idx in range(50):
                    row = [idx]
                    for dxl_id in MOTOR_IDS:
                        curr = self.graph_history[dxl_id][idx]
                        lim = self.limit_history[dxl_id][idx]
                        row.extend([curr, lim])
                    writer.writerow(row)
            messagebox.showinfo("Erfolg", f"Daten erfolgreich exportiert nach:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Daten nicht exportieren:\n{e}")

    def export_graph_png(self):
        from tkinter import filedialog
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG-Bilder", "*.png"), ("Alle Dateien", "*.*")],
            title="Graph als Bild exportieren"
        )
        if not file_path:
            return
        try:
            self.root.update_idletasks()
            x = self.canvas.winfo_rootx()
            y = self.canvas.winfo_rooty()
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            img.save(file_path)
            messagebox.showinfo("Erfolg", f"Bild erfolgreich gespeichert unter:\n{file_path}")
        except Exception as e:
            try:
                eps_path = file_path.rsplit(".", 1)[0] + ".eps"
                self.canvas.postscript(file=eps_path, colormode="color")
                messagebox.showinfo("Teilerfolg", f"PNG-Export fehlgeschlagen, aber EPS-Vektorgrafik wurde gespeichert:\n{eps_path}")
            except Exception as eps_err:
                messagebox.showerror("Fehler", f"Konnte Bild nicht exportieren:\n{e}\n\nEPS-Fehler: {eps_err}")


if __name__ == "__main__":
    root = tk.Tk()
    app = DynamixelSquadApp(root)
    root.mainloop()