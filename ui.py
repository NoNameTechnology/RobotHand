import os
import json
import time
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from typing import Dict, List, Any, Optional

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

from config import (
    config, DEFAULT_GRASP_TYPES, ADDR_GOAL_CURRENT,
    ADDR_PROFILE_VELOCITY, ADDR_GOAL_POSITION
)

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
                         background="#1e1e38", foreground="#e2e8f0", relief='solid', borderwidth=1,
                         font=("Segoe UI", 9, "normal"))
        label.pack(ipadx=6, ipady=5)

    def leave(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

def create_tooltip(widget, text):
    ToolTip(widget, text)


class RobotHandUI:
    def __init__(self, root, controller):
        self.root = root
        self.c = controller
        
        self.is_dark_mode = True
        self.last_draw_time = 0.0
        
        # Color definitions
        self.BG_COLOR = "#0c0c14"
        self.FG_COLOR = "#e2e8f0"
        self.ACCENT_BLUE = "#818cf8"
        self.ACCENT_GREEN = "#6ee7b7"
        self.ACCENT_RED = "#fb7185"
        self.ACCENT_YELLOW = "#fbbf24"
        self.ACCENT_PEACH = "#f59e6b"
        self.PANEL_BG = "#141424"
        self.SURFACE_BG = "#1e1e38"
        self.SUBTEXT = "#94a3b8"
        self.motor_colors = ["#fb7185", "#6ee7b7", "#818cf8", "#fbbf24", "#c084fc"]
        
        # Variable declarations
        self.master_slider_var = tk.DoubleVar(value=0.0)
        self.master_vel_var = tk.IntVar(value=100)
        self.pose_name_var = tk.StringVar(value="Hand Open")
        self.wait_val_var = tk.StringVar(value="1000")
        self.seq_name_var = tk.StringVar(value="MySequence")
        
        self.wait_type_var = tk.StringVar(value="Time")
        self.soft_grip_global = tk.BooleanVar(value=False)
        
        # Elements references
        self.torque_vars = {}
        self.mode_vars = {}
        self.sync_vars = {}
        self.slider_vars = {}
        self.current_vars = {}
        self.soft_grip_vars = {}
        
        self.ui_torque_checkboxes = {}
        self.ui_mode_checkboxes = {}
        self.ui_sync_checkboxes = {}
        self.ui_soft_grip_checkboxes = {}
        self.ui_indiv_sliders = {}
        self.ui_current_sliders = {}
        self.ui_btn_zero = {}
        self.ui_btn_limit = {}
        
        self.motor_cards = {}
        self.motor_name_frames = {}
        self.motor_name_labels = {}
        self.contact_labels = {}
        self.readout_labels = {}
        self.temp_labels = {}
        self.error_labels = {}
        self.current_labels = {}
        self.graph_indicators = {}
        
        self.seq_default_sg_vars = {dxl_id: tk.BooleanVar(value=False) for dxl_id in config.motor_ids}
        self.seq_default_ma_vars = {dxl_id: tk.IntVar(value=1750) for dxl_id in config.motor_ids}
        
        self._build_ui()
        
    def _build_ui(self):
        # --- THEME & STYLING ---
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except:
            pass
            
        self.root.configure(bg=self.BG_COLOR)
        
        self.style.configure(".", background=self.BG_COLOR, foreground=self.FG_COLOR, font=("Segoe UI", 11))
        self.style.configure("TLabel", background=self.BG_COLOR, foreground=self.FG_COLOR)
        self.style.configure("Panel.TLabel", background=self.PANEL_BG, foreground=self.FG_COLOR)
        self.style.configure("Panel.TFrame", background=self.PANEL_BG)
        self.style.configure("Surface.TFrame", background=self.SURFACE_BG)
        self.style.configure("TFrame", background=self.BG_COLOR)
        
        self.style.configure("TLabelframe", background=self.PANEL_BG, foreground=self.ACCENT_BLUE,
                             borderwidth=0, font=("Segoe UI", 10, "bold"))
        self.style.configure("TLabelframe.Label", background=self.PANEL_BG, foreground=self.ACCENT_BLUE)
        
        self.style.configure("TButton", background=self.SURFACE_BG, foreground=self.FG_COLOR,
                             borderwidth=0, padding=(10, 5), font=("Segoe UI", 9))
        self.style.map("TButton", background=[("active", self.ACCENT_BLUE)],
                       foreground=[("active", "#0c0c14")])
        
        self.style.configure("Primary.TButton", background=self.ACCENT_BLUE, foreground="#0c0c14",
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Primary.TButton", background=[("active", "#a5b4fc")])
        
        self.style.configure("Danger.TButton", background=self.ACCENT_RED, foreground="#0c0c14",
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Danger.TButton", background=[("active", "#fda4af")])
        
        self.style.configure("Success.TButton", background=self.ACCENT_GREEN, foreground="#0c0c14",
                             font=("Segoe UI", 9, "bold"))
        self.style.map("Success.TButton", background=[("active", "#86efac")])
        
        self.style.configure("Toggle.TButton", background=self.SURFACE_BG, foreground=self.SUBTEXT,
                             font=("Segoe UI", 9))
        self.style.configure("ToggleOn.TButton", background=self.ACCENT_GREEN, foreground="#0c0c14",
                             font=("Segoe UI", 9, "bold"))
        
        self.style.configure("TCheckbutton", background=self.BG_COLOR, foreground=self.FG_COLOR)
        self.style.map("TCheckbutton", background=[("active", self.BG_COLOR)],
                       indicatorcolor=[("selected", self.ACCENT_BLUE)])
        self.style.configure("Panel.TCheckbutton", background=self.PANEL_BG, foreground=self.FG_COLOR)
        self.style.map("Panel.TCheckbutton", background=[("active", self.PANEL_BG)],
                       indicatorcolor=[("selected", self.ACCENT_BLUE)])
        self.style.configure("Horizontal.TScale", background=self.BG_COLOR, troughcolor=self.SURFACE_BG)
        self.style.configure("Panel.Horizontal.TScale", background=self.PANEL_BG, troughcolor=self.SURFACE_BG)
        
        self.style.configure("TEntry", fieldbackground=self.SURFACE_BG, foreground=self.FG_COLOR, insertcolor=self.FG_COLOR)
        self.style.map("TEntry", selectbackground=[("focus", self.ACCENT_BLUE)], selectforeground=[("focus", "#1e1e2e")])
        self.style.configure("TCombobox", fieldbackground=self.SURFACE_BG, foreground=self.FG_COLOR, background=self.SURFACE_BG)
        self.style.map("TCombobox", fieldbackground=[("readonly", self.SURFACE_BG)], 
                       selectbackground=[("readonly", self.ACCENT_BLUE)], selectforeground=[("readonly", "#1e1e2e")])
        
        # --- MAIN HORIZONTAL SPLIT ---
        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self.BG_COLOR,
                               sashwidth=2, sashrelief=tk.FLAT, bd=0)
        self.paned.pack(fill=tk.BOTH, expand=True)
        
        # ===== LEFT PANEL — Scrollable =====
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
        
        # ===== RIGHT PANEL =====
        self.right_frame = tk.Frame(self.paned, bg=self.BG_COLOR, padx=5, pady=10)

        self.paned.add(self.left_outer, minsize=500, stretch="always")
        self.paned.add(self.right_frame, minsize=300, stretch="always")
        
        # Set initial sash position
        def set_sash_position(event=None):
            total_width = self.root.winfo_width()
            if total_width > 100:
                self.paned.sash_place(0, int(total_width * 0.66), 0)
                self.root.unbind("<Map>")
        self.root.bind("<Map>", set_sash_position)

        # ----- 1. STATUS PANEL -----
        conn_frame = ttk.LabelFrame(left_frame, text=" System Status ", padding="10")
        conn_frame.pack(fill=tk.X, pady=(0, 8))

        status_row1 = ttk.Frame(conn_frame)
        status_row1.pack(fill=tk.X)

        self.btn_connect = ttk.Button(status_row1, text=f"Connect ({config.port})",
                                      command=self.c.toggle_connection, style="Primary.TButton")
        self.btn_connect.pack(side=tk.LEFT, padx=5)
        create_tooltip(self.btn_connect, "Verbindet sich mit den Motoren auf dem gewählten COM-Port.")

        self.lbl_status = ttk.Label(status_row1, text="⬤ OFFLINE", foreground=self.ACCENT_RED,
                                    font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(side=tk.LEFT, padx=15)
        
        self.btn_soft_grip_global = ttk.Button(status_row1, text="🤏 Soft-Grip: OFF",
                                                command=self.c.toggle_soft_grip_global, style="Toggle.TButton")
        self.btn_soft_grip_global.pack(side=tk.LEFT, padx=15)
        create_tooltip(self.btn_soft_grip_global, "Aktiviert Soft-Grip für ALLE Motoren.\nBei Kontakt hält der Motor automatisch an.")
        
        self.btn_quit = ttk.Button(status_row1, text="❌ Exit",
                                   command=self.c.safe_quit, style="Danger.TButton")
        self.btn_quit.pack(side=tk.RIGHT, padx=5)
        create_tooltip(self.btn_quit, "Schließt das Programm sicher und schaltet Motoren ab.")

        self.btn_estop = ttk.Button(status_row1, text="🚨 EMERGENCY STOP 🚨",
                                    command=self.c.emergency_stop, style="Danger.TButton")
        self.btn_estop.pack(side=tk.RIGHT, padx=5)
        create_tooltip(self.btn_estop, "Schaltet sofort den Strom für alle Motoren ab (Torque OFF).")
        
        self.btn_torque_all = ttk.Button(status_row1, text="Torque ALL",
                                         command=self.c.toggle_torque_all, style="Primary.TButton")
        self.btn_torque_all.pack(side=tk.RIGHT, padx=15)
        create_tooltip(self.btn_torque_all, "Schaltet das Drehmoment aller Motoren an oder aus.")
        
        status_row2 = ttk.Frame(conn_frame)
        status_row2.pack(fill=tk.X, pady=(4, 0))
        
        self.btn_scan = ttk.Button(status_row2, text="Scan Motors",
                                   command=self.c.auto_scan_motors, style="TButton")
        self.btn_scan.pack(side=tk.LEFT, padx=5)
        create_tooltip(self.btn_scan, "Scannt den Bus nach vorhandenen Motoren (ID 0-20).")

        self.btn_theme = ttk.Button(status_row2, text="☀ Light",
                                    command=self.toggle_theme, style="TButton")
        self.btn_theme.pack(side=tk.LEFT, padx=5)
        create_tooltip(self.btn_theme, "Wechselt zwischen Dark Mode und Light Mode.")
        
        self.btn_undo = ttk.Button(status_row2, text="↩ Undo",
                                   command=self.c.perform_undo, style="TButton")
        self.btn_undo.pack(side=tk.LEFT, padx=5)
        create_tooltip(self.btn_undo, "Macht die letzte Slider-Bewegung rückgängig (Strg + Z).")
        self.root.bind("<Control-z>", lambda event: self.c.perform_undo())
        
        self.warning_frame = tk.Frame(conn_frame, bg=self.ACCENT_YELLOW, height=0)
        self.warning_frame.pack(fill=tk.X, pady=(5, 0))
        self.warning_frame.pack_forget()
        
        self.lbl_warning = tk.Label(self.warning_frame, text="", bg=self.ACCENT_YELLOW,
                                    fg="#1e1e2e", font=("Segoe UI", 9, "bold"), anchor="w")
        self.lbl_warning.pack(fill=tk.X, padx=10, pady=4)

        # ----- 2. MASTER BROADCAST PANEL -----
        master_frame = ttk.LabelFrame(left_frame, text=" Master Broadcast (Sync Motors) ", padding="10")
        master_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(master_frame, text="Master Position (%):").grid(row=0, column=0, sticky="w", padx=5)
        
        self.master_slider = ttk.Scale(
            master_frame, from_=0, to=100, variable=self.master_slider_var,
            orient="horizontal", command=self.c.on_master_slider_move, state=tk.DISABLED
        )
        self.master_slider.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        create_tooltip(self.master_slider, "Steuert gleichzeitig alle Motoren, bei denen 'Sync' aktiviert ist.")
        master_frame.columnconfigure(1, weight=1)
        
        self.lbl_master_pos = ttk.Label(master_frame, text="0.0 %", width=8)
        self.lbl_master_pos.grid(row=0, column=2, sticky="w", padx=5)
        
        ttk.Label(master_frame, text="Master Profile Vel (%):").grid(row=1, column=0, sticky="w", padx=5)
        self.master_vel_slider = ttk.Scale(
            master_frame, from_=1, to=100, variable=self.master_vel_var,
            orient="horizontal", command=self.c.on_master_vel_move, state=tk.DISABLED
        )
        self.master_vel_slider.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        create_tooltip(self.master_vel_slider, "Regelt die Geschwindigkeit aller synchronisierten Bewegungen (1-100%).")
        
        self.lbl_master_vel = ttk.Label(master_frame, text="Vel: 100 % (Max)", width=15)
        self.lbl_master_vel.grid(row=1, column=2, sticky="w", padx=5)

        # ----- 3. INDIVIDUAL CHANNELS -----
        indiv_frame = ttk.LabelFrame(left_frame, text=" Individual Motor Channels ", padding="10")
        indiv_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        for idx, dxl_id in enumerate(config.motor_ids):
            # Motor Card
            motor_card = tk.Frame(indiv_frame, bg=self.PANEL_BG, highlightthickness=0)
            motor_card.pack(fill=tk.X, pady=4, padx=4)
            self.motor_cards[dxl_id] = motor_card
            
            # ROW 1: Header Info
            row1 = tk.Frame(motor_card, bg=self.PANEL_BG)
            row1.pack(fill=tk.X, padx=10, pady=(8, 3))
            
            accent_color = self.motor_colors[idx % len(self.motor_colors)]
            name_frame = tk.Frame(row1, bg=self.PANEL_BG)
            name_frame.pack(side=tk.LEFT)
            self.motor_name_frames[dxl_id] = name_frame
            
            name_lbl = tk.Label(name_frame, text=self.c.motor_names.get(dxl_id, f"Motor {dxl_id}"),
                                bg=self.PANEL_BG, fg=accent_color,
                                font=("Segoe UI", 11, "bold"), anchor="w", cursor="hand2",
                                width=12)
            name_lbl.pack(fill=tk.BOTH, expand=True)
            name_lbl.bind("<Double-Button-1>", lambda e, did=dxl_id: self.start_name_edit(did))
            create_tooltip(name_lbl, "Doppelklick zum Umbenennen")
            self.motor_name_labels[dxl_id] = name_lbl
            
            id_lbl = tk.Label(row1, text=f"#{dxl_id}", bg=self.SURFACE_BG, fg=self.SUBTEXT,
                              font=("Segoe UI", 8), padx=6, pady=2)
            id_lbl.pack(side=tk.LEFT, padx=(0, 6))
            
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
                command=lambda id=dxl_id: self.c.on_torque_check(id), state=tk.DISABLED,
                style="Panel.TCheckbutton"
            )
            chk_t.pack(side=tk.LEFT, padx=2)
            self.ui_torque_checkboxes[dxl_id] = chk_t
            create_tooltip(chk_t, "Aktiviert das Drehmoment. Wenn aus, ist der Motor stromlos und frei beweglich.")

            m_var = tk.BooleanVar(value=True)
            self.mode_vars[dxl_id] = m_var
            chk_m = ttk.Checkbutton(
                row1, text="Endless", variable=m_var,
                command=lambda id=dxl_id: self.c.on_mode_toggle(id), state=tk.DISABLED,
                style="Panel.TCheckbutton"
            )
            chk_m.pack(side=tk.LEFT, padx=2)
            self.ui_mode_checkboxes[dxl_id] = chk_m
            create_tooltip(chk_m, "Wechselt zwischen Positionssteuerung und Endlos-Drehung.")
            
            sg_var = tk.BooleanVar(value=False)
            self.soft_grip_vars[dxl_id] = sg_var
            chk_sg = ttk.Checkbutton(
                row1, text="SG", variable=sg_var,
                command=lambda id=dxl_id: self.c.on_soft_grip_motor_toggle(id),
                style="Panel.TCheckbutton"
            )
            chk_sg.pack(side=tk.LEFT, padx=2)
            self.ui_soft_grip_checkboxes[dxl_id] = chk_sg
            create_tooltip(chk_sg, "Soft-Grip: Bei Kontakt hält der Motor automatisch an.")
            
            tk.Frame(row1, bg=self.SURFACE_BG, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=2)
            
            btn_zero = ttk.Button(row1, text="Set Zero", width=10,
                                  command=lambda id=dxl_id: self.c.handle_calibration_click(id, "zero"),
                                  state=tk.DISABLED)
            btn_zero.bind("<Button-3>", lambda event, id=dxl_id: self.delete_calibration_menu(event, id, "zero"))
            btn_zero.pack(side=tk.LEFT, padx=2)
            self.ui_btn_zero[dxl_id] = btn_zero
            create_tooltip(btn_zero, "Links-Klick: Position setzen oder anfahren.\nRechts-Klick: Position löschen.")
            
            btn_limit = ttk.Button(row1, text="Set Limit", width=10,
                                   command=lambda id=dxl_id: self.c.handle_calibration_click(id, "limit"),
                                   state=tk.DISABLED)
            btn_limit.bind("<Button-3>", lambda event, id=dxl_id: self.c.delete_calibration_menu(event, id, "limit"))
            btn_limit.pack(side=tk.LEFT, padx=2)
            self.ui_btn_limit[dxl_id] = btn_limit
            create_tooltip(btn_limit, "Links-Klick: Position setzen oder anfahren.\nRechts-Klick: Position löschen.")
            
            tk.Frame(row1, bg=self.SURFACE_BG, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=2)
            
            contact_lbl = tk.Label(row1, text="● No Contact", bg=self.PANEL_BG,
                                   fg=self.SUBTEXT, font=("Segoe UI", 9), width=14, anchor="w")
            contact_lbl.pack(side=tk.LEFT, padx=2)
            self.contact_labels[dxl_id] = contact_lbl
            
            lbl_readout = tk.Label(row1, text="Pos: ------", bg=self.PANEL_BG,
                                   fg=self.FG_COLOR, font=("Segoe UI", 9), width=11, anchor="w")
            lbl_readout.pack(side=tk.LEFT, padx=2)
            self.readout_labels[dxl_id] = lbl_readout
            
            temp_lbl = tk.Label(row1, text="🌡--°C", bg=self.PANEL_BG, fg=self.ACCENT_GREEN,
                                font=("Segoe UI", 9), width=6)
            temp_lbl.pack(side=tk.RIGHT, padx=2)
            self.temp_labels[dxl_id] = temp_lbl
            
            err_lbl = tk.Label(row1, text="✓", bg=self.PANEL_BG, fg=self.ACCENT_GREEN,
                               font=("Segoe UI", 9, "bold"), width=2)
            err_lbl.pack(side=tk.RIGHT, padx=2)
            self.error_labels[dxl_id] = err_lbl

            btn_reboot = ttk.Button(row1, text="Reboot", width=6,
                                    command=lambda id=dxl_id: self.c.reboot_motor(id))
            btn_reboot.pack(side=tk.RIGHT, padx=2)
            create_tooltip(btn_reboot, "Startet den Motor neu, um Fehler (z.B. Overload) zu löschen.")

            # ROW 2: Position Slider
            row2 = tk.Frame(motor_card, bg=self.PANEL_BG)
            row2.pack(fill=tk.X, padx=10, pady=(3, 3))
            
            tk.Label(row2, text="Pos:", bg=self.PANEL_BG, fg=self.SUBTEXT,
                     font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(0, 2))
            
            s_var = tk.IntVar(value=0)
            self.slider_vars[dxl_id] = s_var
            slider = ttk.Scale(
                row2, from_=0, to=1, variable=s_var,
                orient="horizontal",
                command=lambda val, id=dxl_id: self.c.on_indiv_slider_move(id, val),
                state=tk.DISABLED, style="Panel.Horizontal.TScale"
            )
            slider.bind("<ButtonRelease-1>", lambda event, id=dxl_id: self.c.on_slider_release(event, id))
            slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self.ui_indiv_sliders[dxl_id] = slider
            
            # ROW 3: Current Limit Slider
            row3 = tk.Frame(motor_card, bg=self.PANEL_BG)
            row3.pack(fill=tk.X, padx=10, pady=(3, 8))
            
            lbl_m = tk.Label(row3, text="mA:", bg=self.PANEL_BG, fg=self.SUBTEXT,
                             font=("Segoe UI", 8))
            lbl_m.pack(side=tk.LEFT, padx=(0, 2))
            
            c_var = tk.IntVar(value=1750)
            self.current_vars[dxl_id] = c_var
            curr_slider = ttk.Scale(
                row3, from_=0, to=1750, variable=c_var,
                orient="horizontal",
                command=lambda val, id=dxl_id: self.c.on_current_slider_move(id, val),
                state=tk.DISABLED, style="Panel.Horizontal.TScale"
            )
            curr_slider.bind("<ButtonRelease-1>", lambda event, id=dxl_id: self.c.on_current_slider_release(event, id))
            curr_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self.ui_current_sliders[dxl_id] = curr_slider
            
            lbl_curr = tk.Label(row3, text="1750", bg=self.PANEL_BG, fg=self.FG_COLOR,
                                font=("Segoe UI", 8), width=5, anchor="e")
            lbl_curr.pack(side=tk.LEFT, padx=2)
            self.current_labels[dxl_id] = lbl_curr

        # ----- 4. POSES LIBRARY (RIGHT SIDE) -----
        poses_frame = ttk.LabelFrame(self.right_frame, text=" Pose Library ", padding="8")
        poses_frame.pack(fill=tk.X, pady=(0, 8))
        
        row_p1 = ttk.Frame(poses_frame)
        row_p1.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(row_p1, text="Name:").pack(side=tk.LEFT, padx=1)
        entry_pose_name = ttk.Entry(row_p1, textvariable=self.pose_name_var, width=18)
        entry_pose_name.pack(side=tk.LEFT, padx=1)
        
        self.btn_save_pose = ttk.Button(row_p1, text="💾", width=3, command=self.c.save_single_pose)
        self.btn_save_pose.pack(side=tk.LEFT, padx=1)
        create_tooltip(self.btn_save_pose, "Speichert die aktuellen Positionen aller synchronisierten Motoren als neue Pose.")
        
        ttk.Separator(row_p1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        self.cb_poses = ttk.Combobox(row_p1, state="readonly", width=18)
        self.cb_poses.pack(side=tk.LEFT, padx=1)
        btn_go_pose = ttk.Button(row_p1, text="▶ Go", width=6, command=self.c.go_to_selected_pose)
        btn_go_pose.pack(side=tk.LEFT, padx=1)
        btn_add_seq = ttk.Button(row_p1, text="+ Sequence", width=9, command=self.c.add_pose_to_sequence)
        btn_add_seq.pack(side=tk.LEFT, padx=1)
        btn_del_pose = ttk.Button(row_p1, text="🗑", width=3, command=self.c.delete_selected_pose, style="Danger.TButton")
        btn_del_pose.pack(side=tk.LEFT, padx=1)

        # ----- 5. SEQUENCE CONTROL -----
        seq_frame = ttk.LabelFrame(self.right_frame, text=" Sequence Control ", padding="8")
        seq_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        
        seq_ctrl = ttk.Frame(seq_frame)
        seq_ctrl.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(seq_ctrl, text="ms:").pack(side=tk.LEFT, padx=1)
        entry_wait = ttk.Entry(seq_ctrl, textvariable=self.wait_val_var, width=5)
        entry_wait.pack(side=tk.LEFT, padx=1)
        
        ttk.Separator(seq_ctrl, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        btn_append = ttk.Button(seq_ctrl, text="+ Pose", width=8, command=self.c.append_current_pose_to_sequence)
        btn_append.pack(side=tk.LEFT, padx=1)
        
        self.btn_home = ttk.Button(seq_ctrl, text="⌂ Zero", width=6, command=self.c.go_home)
        self.btn_home.pack(side=tk.LEFT, padx=1)
        
        btn_sg_settings = ttk.Button(seq_ctrl, text="⚙ SG-Def", width=9, command=self.open_seq_sg_settings)
        btn_sg_settings.pack(side=tk.LEFT, padx=1)
        
        list_container = ttk.Frame(seq_frame)
        list_container.pack(fill=tk.BOTH, expand=True, pady=3)
        
        self.seq_listbox = tk.Listbox(list_container, bg=self.SURFACE_BG, fg=self.FG_COLOR,
                                      borderwidth=0, selectbackground=self.ACCENT_BLUE,
                                      selectforeground="#0c0c14", font=("Segoe UI", 9))
        self.seq_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self.seq_listbox.bind("<Button-3>", self.seq_listbox_context_menu)
        
        list_btn_frame = ttk.Frame(list_container)
        list_btn_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        btn_up = ttk.Button(list_btn_frame, text="▲", width=3, command=self.c.seq_move_up)
        btn_up.pack(fill=tk.X, pady=1)
        
        btn_down = ttk.Button(list_btn_frame, text="▼", width=3, command=self.c.seq_move_down)
        btn_down.pack(fill=tk.X, pady=1)
        
        btn_del = ttk.Button(list_btn_frame, text="✕", width=3, command=self.c.seq_delete_step)
        btn_del.pack(fill=tk.X, pady=1)
        btn_clear = ttk.Button(list_btn_frame, text="⌀", width=3, command=self.c.seq_clear_all)
        btn_clear.pack(fill=tk.X, pady=1)
        
        seq_play_row1 = ttk.Frame(seq_frame)
        seq_play_row1.pack(fill=tk.X, pady=(5, 2))
        
        self.btn_play_seq = ttk.Button(seq_play_row1, text="▶ Start (0)", width=10,
                                       command=self.c.play_sequence, style="Primary.TButton")
        self.btn_play_seq.pack(side=tk.LEFT, padx=1)
        
        self.lbl_seq_status = ttk.Label(seq_play_row1, text="Ready", width=25,
                                        font=("Segoe UI", 9, "bold"), foreground=self.ACCENT_GREEN)
        self.lbl_seq_status.pack(side=tk.LEFT, padx=5)
        
        seq_play_row2 = ttk.Frame(seq_frame)
        seq_play_row2.pack(fill=tk.X, pady=(2, 0))
        
        lbl_name = ttk.Label(seq_play_row2, text="Name:")
        lbl_name.pack(side=tk.LEFT, padx=1)
        
        entry_seq_name = ttk.Entry(seq_play_row2, textvariable=self.seq_name_var, width=12)
        entry_seq_name.pack(side=tk.LEFT, padx=1)
        
        btn_save_seq = ttk.Button(seq_play_row2, text="💾", width=3, command=self.c.save_sequence_to_file)
        btn_save_seq.pack(side=tk.LEFT, padx=1)
        
        ttk.Separator(seq_play_row2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        self.cb_sequences = ttk.Combobox(seq_play_row2, state="readonly", width=12)
        self.cb_sequences.pack(side=tk.LEFT, padx=1)
        btn_load_seq = ttk.Button(seq_play_row2, text="📂 Load", width=9, command=self.c.load_selected_sequence)
        btn_load_seq.pack(side=tk.LEFT, padx=1)
        btn_del_seq = ttk.Button(seq_play_row2, text="🗑", width=3, command=self.c.delete_selected_seq, style="Danger.TButton")
        btn_del_seq.pack(side=tk.LEFT, padx=1)

        # ----- 6. LIVE CURRENT GRAPH -----
        graph_frame = ttk.LabelFrame(self.root, text=" Live Current (Contact Detection) ", padding="8")
        graph_frame.pack(side=tk.BOTTOM, fill=tk.X, expand=False, pady=(5, 5), padx=10, before=self.paned)
        
        self.canvas = tk.Canvas(graph_frame, bg="#08080f", height=250, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        legend_frame = ttk.Frame(graph_frame)
        legend_frame.pack(fill=tk.X, pady=5)
        
        for i, dxl_id in enumerate(config.motor_ids):
            c = self.motor_colors[i % len(self.motor_colors)]
            ind = tk.Label(legend_frame, text=self.c.motor_names.get(dxl_id, f"ID {dxl_id:02d}"),
                           bg=self.PANEL_BG, fg=c, font=("Segoe UI", 8, "bold"), padx=4, pady=1)
            ind.pack(side=tk.LEFT, padx=3)
            self.graph_indicators[dxl_id] = {"label": ind, "color": c}
            
        btn_export = ttk.Button(legend_frame, text="💾 Export Graph", command=self.export_graph_menu, width=18)
        btn_export.pack(side=tk.RIGHT, padx=5)

        # Bindings for mouse scroll wheel on scale elements
        self.root.bind_class("TScale", "<MouseWheel>", self.on_class_slider_mousewheel)
        self.root.bind_class("Scale", "<MouseWheel>", self.on_class_slider_mousewheel)
        self.root.bind_class("TScale", "<Button-4>", self.on_class_slider_mousewheel)
        self.root.bind_class("Scale", "<Button-4>", self.on_class_slider_mousewheel)
        self.root.bind_class("TScale", "<Button-5>", self.on_class_slider_mousewheel)
        self.root.bind_class("Scale", "<Button-5>", self.on_class_slider_mousewheel)

    def start_name_edit(self, dxl_id):
        self.motor_name_labels[dxl_id].pack_forget()
        entry = tk.Entry(self.motor_name_frames[dxl_id], bg=self.SURFACE_BG, fg=self.FG_COLOR,
                         insertbackground=self.FG_COLOR, font=("Segoe UI", 10, "bold"),
                         relief="flat", borderwidth=2)
        entry.insert(0, self.c.motor_names[dxl_id])
        entry.pack(fill=tk.BOTH, expand=True)
        entry.select_range(0, tk.END)
        entry.focus_set()
        
        entry.bind("<Return>", lambda e: self.finish_name_edit(dxl_id, entry))
        entry.bind("<Escape>", lambda e: self.cancel_name_edit(dxl_id, entry))
        entry.bind("<FocusOut>", lambda e: self.finish_name_edit(dxl_id, entry))

    def finish_name_edit(self, dxl_id, entry):
        new_name = entry.get().strip()
        if new_name:
            self.c.motor_names[dxl_id] = new_name
            self.c.state.motors[dxl_id].name = new_name
            self.motor_name_labels[dxl_id].config(text=new_name)
            if dxl_id in self.graph_indicators:
                self.graph_indicators[dxl_id]["label"].config(text=new_name)
            self.c.save_motor_names()
        entry.destroy()
        self.motor_name_labels[dxl_id].pack(fill=tk.BOTH, expand=True)

    def cancel_name_edit(self, dxl_id, entry):
        entry.destroy()
        self.motor_name_labels[dxl_id].pack(fill=tk.BOTH, expand=True)

    def delete_calibration_menu(self, event, dxl_id, point_type):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Löschen", command=lambda: self.c.delete_calibration(dxl_id, point_type))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        if self.is_dark_mode:
            self.BG_COLOR = "#0c0c14"
            self.FG_COLOR = "#e2e8f0"
            self.ACCENT_BLUE = "#818cf8"
            self.ACCENT_GREEN = "#6ee7b7"
            self.ACCENT_RED = "#fb7185"
            self.ACCENT_YELLOW = "#fbbf24"
            self.ACCENT_PEACH = "#f59e6b"
            self.PANEL_BG = "#141424"
            self.SURFACE_BG = "#1e1e38"
            self.SUBTEXT = "#94a3b8"
            self.motor_colors = ["#fb7185", "#6ee7b7", "#818cf8", "#fbbf24", "#c084fc"]
            self.btn_theme.config(text="☀ Light")
        else:
            self.BG_COLOR = "#f8fafc"
            self.FG_COLOR = "#0f172a"
            self.ACCENT_BLUE = "#6366f1"
            self.ACCENT_GREEN = "#059669"
            self.ACCENT_RED = "#e11d48"
            self.ACCENT_YELLOW = "#d97706"
            self.ACCENT_PEACH = "#ea580c"
            self.PANEL_BG = "#f1f5f9"
            self.SURFACE_BG = "#e2e8f0"
            self.SUBTEXT = "#64748b"
            self.motor_colors = ["#e11d48", "#059669", "#6366f1", "#d97706", "#7c3aed"]
            self.btn_theme.config(text="🌙 Dark")
        self._apply_theme()

    def _apply_theme(self):
        self.root.configure(bg=self.BG_COLOR)
        self.paned.configure(bg=self.BG_COLOR)
        self.left_outer.configure(bg=self.BG_COLOR)
        self.canvas_left.configure(bg=self.BG_COLOR)
        self.right_frame.configure(bg=self.BG_COLOR)
            
        select_fg = "#0c0c14" if self.is_dark_mode else "#ffffff"
        
        self.style.configure(".", background=self.BG_COLOR, foreground=self.FG_COLOR, font=("Segoe UI", 11))
        self.style.configure("TLabel", background=self.BG_COLOR, foreground=self.FG_COLOR)
        self.style.configure("Panel.TLabel", background=self.PANEL_BG, foreground=self.FG_COLOR)
        self.style.configure("Panel.TFrame", background=self.PANEL_BG)
        self.style.configure("Surface.TFrame", background=self.SURFACE_BG)
        self.style.configure("TFrame", background=self.BG_COLOR)
        self.style.configure("TLabelframe", background=self.PANEL_BG, foreground=self.ACCENT_BLUE, borderwidth=0, font=("Segoe UI", 10, "bold"))
        self.style.configure("TLabelframe.Label", background=self.PANEL_BG, foreground=self.ACCENT_BLUE)
        self.style.configure("TButton", background=self.SURFACE_BG, foreground=self.FG_COLOR, borderwidth=0, padding=(10, 5), font=("Segoe UI", 9))
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
        
        graph_bg = "#08080f" if self.is_dark_mode else "#ffffff"
        self.canvas.config(bg=graph_bg)
        self.seq_listbox.config(bg=self.SURFACE_BG, fg=self.FG_COLOR, selectbackground=self.ACCENT_BLUE, selectforeground=select_fg)
        
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

        for dxl_id in config.motor_ids:
            card = self.motor_cards.get(dxl_id)
            if card:
                update_bg_recursive(card)
            
            if dxl_id in self.current_labels:
                self.current_labels[dxl_id].config(fg=self.FG_COLOR)
            if dxl_id in self.readout_labels:
                self.readout_labels[dxl_id].config(fg=self.FG_COLOR)
            if dxl_id in self.temp_labels:
                curr_fg = self.temp_labels[dxl_id].cget("fg")
                if curr_fg in ("#fb7185", "#e11d48"):
                    self.temp_labels[dxl_id].config(fg=self.ACCENT_RED)
                else:
                    self.temp_labels[dxl_id].config(fg=self.ACCENT_GREEN)
            if dxl_id in self.error_labels:
                curr_fg = self.error_labels[dxl_id].cget("fg")
                if curr_fg in ("#fb7185", "#e11d48"):
                    self.error_labels[dxl_id].config(fg=self.ACCENT_RED)
                else:
                    self.error_labels[dxl_id].config(fg=self.ACCENT_GREEN)
            if dxl_id in self.contact_labels:
                state = self.c.get_contact_state(dxl_id)
                if state == "contact":
                    self.contact_labels[dxl_id].config(fg=self.ACCENT_GREEN)
                elif state == "approaching":
                    self.contact_labels[dxl_id].config(fg=self.ACCENT_YELLOW)
                else:
                    self.contact_labels[dxl_id].config(fg=self.SUBTEXT)
        
        self.lbl_seq_status.config(foreground=self.ACCENT_GREEN)
        
        for idx, dxl_id in enumerate(config.motor_ids):
            c = self.motor_colors[idx % len(self.motor_colors)]
            if dxl_id in self.motor_name_labels:
                self.motor_name_labels[dxl_id].config(fg=c)
            if dxl_id in self.graph_indicators:
                self.graph_indicators[dxl_id]["label"].config(fg=c)
                self.graph_indicators[dxl_id]["color"] = c

    def draw_graph_throttled(self):
        curr_time = time.time()
        if curr_time - self.last_draw_time >= 1.0 / config.graph_refresh_hz:
            self._draw_graph()
            self.last_draw_time = curr_time

    def _draw_graph(self):
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width > 10 and height > 10:
            margin_left = 50
            margin_bottom = 22
            margin_top = 8
            margin_right = 8
            
            plot_w = width - margin_left - margin_right
            plot_h = height - margin_top - margin_bottom
            
            if plot_w < 10 or plot_h < 10:
                plot_w = max(plot_w, 10)
                plot_h = max(plot_h, 10)
            
            y_max = float(config.current_max)
            y_scale = plot_h / y_max
            x_step = plot_w / 50.0
            
            # Grid
            self.canvas.create_line(margin_left, margin_top, margin_left, height - margin_bottom, fill="#1e1e38", width=1)
            self.canvas.create_line(margin_left, height - margin_bottom, width - margin_right, height - margin_bottom, fill="#1e1e38", width=1)
            
            self.canvas.create_text(margin_left - 5, margin_top + plot_h // 2, anchor="e",
                                    text="Strom\n(mA)", fill="#94a3b8", font=("Segoe UI", 7),
                                    justify="center")
            
            y_ticks = [0, 250, 500, 750, 1000, 1250, 1500, int(config.current_max)]
            for tick_val in y_ticks:
                y_pos = (height - margin_bottom) - (tick_val * y_scale)
                if y_pos >= margin_top:
                    self.canvas.create_line(margin_left - 4, y_pos, margin_left, y_pos, fill="#2a2a45", width=1)
                    self.canvas.create_text(margin_left - 6, y_pos, anchor="e", text=str(tick_val), fill="#64748b", font=("Segoe UI", 7))
                    if tick_val > 0:
                        self.canvas.create_line(margin_left + 1, y_pos, width - margin_right, y_pos, fill="#141424", width=1, dash=(2, 4))
            
            self.canvas.create_text(margin_left + plot_w // 2, height - 3, anchor="s", text="Zeit (t)", fill="#94a3b8", font=("Segoe UI", 8))
            
            for i, dxl_id in enumerate(config.motor_ids):
                motor = self.c.state.motors[dxl_id]
                hist = motor.graph_history
                color = self.graph_indicators[dxl_id]["color"]
                
                # Limit line
                limit_hist = motor.limit_history
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
                
                contact = self.c.get_contact_state(dxl_id)
                if contact == "contact":
                    self.graph_indicators[dxl_id]["label"].config(bg=self.ACCENT_GREEN, fg="#0c0c14")
                elif contact == "approaching":
                    self.graph_indicators[dxl_id]["label"].config(bg=self.ACCENT_YELLOW, fg="#0c0c14")
                else:
                    self.graph_indicators[dxl_id]["label"].config(bg=self.PANEL_BG, fg=color)
                    
                points = []
                for idx, val in enumerate(hist):
                    x = margin_left + (idx * x_step)
                    y = (height - margin_bottom) - (abs(val) * y_scale)
                    y = max(margin_top, min(y, height - margin_bottom))
                    points.extend([x, y])
                    
                if len(points) >= 4:
                    self.canvas.create_line(points, fill=color, width=2, smooth=True)

    def on_class_slider_mousewheel(self, event):
        slider = event.widget
        is_disabled = False
        try:
            state_val = str(slider.cget("state"))
            if "disabled" in state_val:
                is_disabled = True
        except Exception:
            pass
            
        try:
            if hasattr(slider, "state") and "disabled" in slider.state():
                is_disabled = True
        except Exception:
            pass
            
        if is_disabled:
            return "break"
            
        if event.num == 4:
            direction = 1
        elif event.num == 5:
            direction = -1
        elif event.delta > 0:
            direction = 1
        elif event.delta < 0:
            direction = -1
        else:
            return "break"
            
        try:
            from_ = float(slider.cget("from"))
            to = float(slider.cget("to"))
        except Exception:
            return "break"
            
        range_val = abs(to - from_)
        
        if range_val > 1000:
            step = 10
        elif range_val > 200:
            step = 5
        else:
            step = 1
            
        current_val = float(slider.get())
        new_val = current_val + direction * step
        
        min_limit = min(from_, to)
        max_limit = max(from_, to)
        if new_val < min_limit:
            new_val = min_limit
        elif new_val > max_limit:
            new_val = max_limit
            
        # Store state for undo before sliding
        # Find which motor slider is this
        dxl_id = None
        for mid, s in self.ui_indiv_sliders.items():
            if s == slider:
                dxl_id = mid
                break
                
        if dxl_id is not None:
            old_val = self.slider_vars[dxl_id].get()
            self.c.state.history.push({
                "type": "slider",
                "motor_id": dxl_id,
                "old_value": old_val,
                "new_value": int(new_val)
            })

        slider.set(new_val)
        return "break"

    def refresh_sequence_listbox(self):
        self.seq_listbox.delete(0, tk.END)
        for i, frame in enumerate(self.c.sequence_frames):
            name = frame.get("name", "Step")
            wt = frame.get("wait_type", "Time")
            wv = frame.get("wait_val", 1000)
            sg = "🤏" if frame.get("state", {}).get("soft_grip_global", False) else ""
            self.seq_listbox.insert(tk.END, f"{i+1}. {name} ({wt}: {wv}ms) {sg}")
        self.btn_play_seq.config(text=f"▶ Start ({len(self.c.sequence_frames)})")

    def update_pose_combobox(self):
        names = list(self.c.saved_poses.keys())
        self.cb_poses['values'] = names
        if names and not self.cb_poses.get():
            self.cb_poses.set(names[0])

    def update_sequence_combobox(self):
        names = list(self.c.saved_sequences.keys())
        self.cb_sequences['values'] = names
        if names and not self.cb_sequences.get():
            self.cb_sequences.set(names[0])

    def seq_listbox_context_menu(self, event):
        idx = self.seq_listbox.nearest(event.y)
        if idx < 0 or idx >= len(self.c.sequence_frames):
            return
        self.seq_listbox.selection_clear(0, tk.END)
        self.seq_listbox.selection_set(idx)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Edit", command=lambda: self.open_step_editor(idx))
        menu.add_command(label="Duplicate", command=lambda: self.c.ctx_duplicate_step(idx))
        menu.add_separator()
        menu.add_command(label="Delete", command=lambda: self.c.ctx_delete_step(idx))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def open_step_editor(self, step_index):
        frame = self.c.sequence_frames[step_index]
        state = frame.get("state", {})
        pose = state.get("pose", {})
        limits = state.get("limits", {})
        velocities = state.get("velocities", {})
        sg_global = state.get("soft_grip_global", False)
        sg_motors = state.get("soft_grip_motors", {})

        editor = tk.Toplevel(self.root)
        editor.title(f"Edit Step {step_index + 1}")
        editor.configure(bg=self.BG_COLOR)
        editor.geometry("520x680")
        editor.resizable(True, True)
        editor.transient(self.root)
        editor.grab_set()

        hdr = tk.Label(editor, text=f"Step {step_index + 1}: {frame.get('name', 'Step')}",
                       bg=self.BG_COLOR, fg=self.ACCENT_BLUE, font=("Segoe UI", 12, "bold"))
        hdr.pack(pady=(10, 5))

        canvas_edit = tk.Canvas(editor, bg=self.BG_COLOR, highlightthickness=0)
        scrollbar_edit = ttk.Scrollbar(editor, orient="vertical", command=canvas_edit.yview)
        content = tk.Frame(canvas_edit, bg=self.BG_COLOR)
        content.bind("<Configure>", lambda e: canvas_edit.configure(scrollregion=canvas_edit.bbox("all")))
        canvas_edit.create_window((0, 0), window=content, anchor="nw")
        canvas_edit.configure(yscrollcommand=scrollbar_edit.set)
        canvas_edit.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        scrollbar_edit.pack(side=tk.RIGHT, fill=tk.Y)
        canvas_edit.bind_all("<MouseWheel>", lambda e: canvas_edit.yview_scroll(-1 * (e.delta // 120), "units"))

        # TIMING
        sec_time = tk.LabelFrame(content, text="Timing", bg=self.PANEL_BG, fg=self.ACCENT_BLUE,
                                 font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        sec_time.pack(fill=tk.X, pady=5)
        time_row = tk.Frame(sec_time, bg=self.PANEL_BG)
        time_row.pack(fill=tk.X)
        tk.Label(time_row, text="Time (ms):", bg=self.PANEL_BG, fg=self.FG_COLOR, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        edit_wait_val = tk.StringVar(value=str(frame.get("wait_val", 1000)))
        tk.Entry(time_row, textvariable=edit_wait_val, width=8, bg=self.SURFACE_BG, fg=self.FG_COLOR, insertbackground=self.FG_COLOR, font=("Segoe UI", 9)).pack(side=tk.LEFT)

        # VELOCITY GLOBAL
        sec_vel = tk.LabelFrame(content, text="Velocity (Global)", bg=self.PANEL_BG, fg=self.ACCENT_BLUE,
                                font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        sec_vel.pack(fill=tk.X, pady=5)
        vel_row = tk.Frame(sec_vel, bg=self.PANEL_BG)
        vel_row.pack(fill=tk.X)
        tk.Label(vel_row, text="All %:", bg=self.PANEL_BG, fg=self.SUBTEXT, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(5, 4))
        
        dxl_vel_values = [velocities.get(str(d), velocities.get(d, 100)) for d in config.motor_ids]
        avg_vel = int(sum(dxl_vel_values) / len(dxl_vel_values)) if dxl_vel_values else 100
        
        global_vel_var = tk.IntVar(value=avg_vel)
        global_vel_lbl = tk.Label(vel_row, text=f"{avg_vel} %", bg=self.PANEL_BG, fg=self.ACCENT_PEACH, font=("Segoe UI", 9, "bold"), width=7)
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

        # SOFT-GRIP GLOBAL
        sec_sg = tk.LabelFrame(content, text="Soft-Grip (Global)", bg=self.PANEL_BG, fg=self.ACCENT_BLUE,
                               font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        sec_sg.pack(fill=tk.X, pady=5)
        edit_sg_global = tk.BooleanVar(value=sg_global)
        sg_row = tk.Frame(sec_sg, bg=self.PANEL_BG)
        sg_row.pack(fill=tk.X)
        tk.Checkbutton(sg_row, text="Soft-Grip active", variable=edit_sg_global,
                       bg=self.PANEL_BG, fg=self.FG_COLOR, selectcolor=self.SURFACE_BG,
                       activebackground=self.PANEL_BG, activeforeground=self.FG_COLOR,
                       font=("Segoe UI", 9)).pack(side=tk.LEFT)

        tk.Label(sg_row, text="All mA:", bg=self.PANEL_BG, fg=self.SUBTEXT, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(20, 4))
        global_current_var = tk.IntVar(value=1750)
        global_current_lbl = tk.Label(sg_row, text="1750", bg=self.PANEL_BG, fg=self.ACCENT_PEACH, font=("Segoe UI", 9, "bold"), width=5)
        global_current_lbl.pack(side=tk.RIGHT, padx=4)

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

        # PER-MOTOR INDIVIDUALS
        sec_motors = tk.LabelFrame(content, text="Motors (Individual)", bg=self.PANEL_BG, fg=self.ACCENT_BLUE,
                                   font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        sec_motors.pack(fill=tk.X, pady=5)

        edit_sg_motors = {}
        edit_limits = {}
        edit_ma_is_default = {}
        edit_positions = {}
        edit_velocities = {}

        for dxl_id in config.motor_ids:
            dxl_str = str(dxl_id)
            motor_name = self.c.motor_names.get(dxl_id, f"Motor {dxl_id}")
            has_pose = dxl_str in pose or dxl_id in pose

            card = tk.Frame(sec_motors, bg=self.SURFACE_BG, bd=1, relief=tk.GROOVE)
            card.pack(fill=tk.X, pady=3, padx=2)

            r1 = tk.Frame(card, bg=self.SURFACE_BG)
            r1.pack(fill=tk.X, padx=6, pady=(4, 2))
            tk.Label(r1, text=motor_name, bg=self.SURFACE_BG, fg=self.ACCENT_GREEN, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

            sg_val = sg_motors.get(dxl_str, "default")
            sg_display = "Sequence Default" if sg_val == "default" else ("Enabled" if sg_val is True or sg_val == "True" else "Disabled")
            sg_var = tk.StringVar(value=sg_display)
            edit_sg_motors[dxl_str] = sg_var
            
            tk.Label(r1, text="Soft-Grip:", bg=self.SURFACE_BG, fg=self.SUBTEXT, font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(10, 2))
            cb_sg = ttk.Combobox(r1, textvariable=sg_var, values=["Sequence Default", "Enabled", "Disabled"], width=15, state="readonly", font=("Segoe UI", 8))
            cb_sg.pack(side=tk.LEFT, padx=2)

            # Test command
            if has_pose and self.c.hardware.is_connected:
                def make_test_cmd(did=dxl_id, lims=edit_limits, poss=edit_positions, vels=edit_velocities):
                    def test_cmd():
                        if not self.c.hardware.is_connected: return
                        if not self.c.ensure_torque_enabled([did]): return
                        lim_val = lims[str(did)].get()
                        self.current_vars[did].set(lim_val)
                        self.current_labels[did].config(text=str(lim_val))
                        self.c.hardware.enqueue_command({"type": "goal_current", "motor_id": did, "value": lim_val})
                        
                        vel_val = vels[str(did)].get()
                        hardware_vel = int((vel_val / 100.0) * 300) if vel_val < 100 else 0
                        if hardware_vel == 0 and vel_val < 100: hardware_vel = 1
                        self.c.hardware.enqueue_command({"type": "profile_velocity", "motor_id": did, "value": hardware_vel})

                        pos_val = poss[str(did)].get()
                        self.slider_vars[did].set(pos_val)
                        self.c.hardware.enqueue_command({"type": "goal_position", "motor_id": did, "value": pos_val})
                    return test_cmd
                ttk.Button(r1, text="Test", width=5, command=make_test_cmd()).pack(side=tk.RIGHT, padx=2)

            # Current limit slider
            r2 = tk.Frame(card, bg=self.SURFACE_BG)
            r2.pack(fill=tk.X, padx=6, pady=1)
            tk.Label(r2, text="mA:", bg=self.SURFACE_BG, fg=self.SUBTEXT, font=("Segoe UI", 8)).pack(side=tk.LEFT)

            cur_val = limits.get(dxl_str, limits.get(dxl_id, "default"))
            is_def = (cur_val == "default" or cur_val == "default_ma")
            ma_def_var = tk.BooleanVar(value=is_def)
            edit_ma_is_default[dxl_str] = ma_def_var
            
            slider_val = 1750 if is_def else int(cur_val)
            cur_var = tk.IntVar(value=slider_val)
            edit_limits[dxl_str] = cur_var

            cur_lbl = tk.Label(r2, text="Default" if is_def else str(slider_val), bg=self.SURFACE_BG, fg=self.ACCENT_PEACH, font=("Segoe UI", 8, "bold"), width=8)
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
                        lbl.config(text="Default")
                    else:
                        sl.config(state=tk.NORMAL)
                        lbl.config(text=str(var.get()))
                return toggle
                
            chk_def = ttk.Checkbutton(r2, text="Default", variable=ma_def_var, command=make_ma_def_toggle())
            chk_def.pack(side=tk.RIGHT, padx=4)

            # Velocity slider
            r2b = tk.Frame(card, bg=self.SURFACE_BG)
            r2b.pack(fill=tk.X, padx=6, pady=1)
            tk.Label(r2b, text="Vel %:", bg=self.SURFACE_BG, fg=self.SUBTEXT, font=("Segoe UI", 8)).pack(side=tk.LEFT)

            vel_val = velocities.get(dxl_str, velocities.get(dxl_id, 100))
            vel_var = tk.IntVar(value=vel_val)
            edit_velocities[dxl_str] = vel_var

            vel_lbl = tk.Label(r2b, text=f"{vel_val} %", bg=self.SURFACE_BG, fg=self.ACCENT_PEACH, font=("Segoe UI", 8, "bold"), width=7)
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

            # Position
            if has_pose:
                r3 = tk.Frame(card, bg=self.SURFACE_BG)
                r3.pack(fill=tk.X, padx=6, pady=(1, 4))

                pos_raw = pose.get(dxl_str, pose.get(dxl_id, 0))
                pos_var = tk.IntVar(value=pos_raw)
                edit_positions[dxl_str] = pos_var

                tk.Label(r3, text="Pos:", bg=self.SURFACE_BG, fg=self.SUBTEXT, font=("Segoe UI", 8)).pack(side=tk.LEFT)

                motor_state = self.c.state.motors[dxl_id]
                c_zero = motor_state.calib_zero
                c_limit = motor_state.calib_limit
                if c_zero is not None and c_limit is not None:
                    pos_min = min(c_zero, c_limit)
                    pos_max = max(c_zero, c_limit)
                else:
                    pos_min = pos_raw - 2000
                    pos_max = pos_raw + 2000

                pos_lbl = tk.Label(r3, text=str(pos_raw), bg=self.SURFACE_BG, fg=self.ACCENT_YELLOW, font=("Segoe UI", 8, "bold"), width=6)
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
                        if messagebox.askyesno("Warning",
                                f"Are you sure you want to change the target position of "
                                f"{self.c.motor_names.get(did, f'Motor {did}')}?\n"
                                f"An incorrect position can cause collisions!",
                                parent=editor):
                            sl.config(state=tk.NORMAL)
                    return unlock

                ttk.Button(r3, text="Unlock", width=8, command=make_unlock_cmd()).pack(side=tk.LEFT, padx=4)

        # BUTTON ROW
        btn_row = tk.Frame(editor, bg=self.BG_COLOR)
        btn_row.pack(fill=tk.X, pady=10, padx=10)

        def save_edits():
            try:
                wv = int(edit_wait_val.get())
            except ValueError:
                wv = 1000
            frame["wait_type"] = "Time"
            frame["wait_val"] = wv
            state["soft_grip_global"] = edit_sg_global.get()

            saved_sg_motors = {}
            for k, v in edit_sg_motors.items():
                val_str = v.get()
                if val_str in ("Ablauf-Standard", "Sequence Default"):
                    saved_sg_motors[k] = "default"
                elif val_str in ("Aktiviert", "Enabled"):
                    saved_sg_motors[k] = True
                else:
                    saved_sg_motors[k] = False
            state["soft_grip_motors"] = saved_sg_motors
            
            self.c.mark_seq_unsaved()

            new_limits = {}
            for k, v in edit_limits.items():
                if edit_ma_is_default[k].get():
                    new_limits[k] = "default"
                else:
                    new_limits[k] = v.get()
            state["limits"] = new_limits

            new_velocities = {}
            for k, v in edit_velocities.items():
                new_velocities[k] = v.get()
            state["velocities"] = new_velocities

            new_pose = dict(pose)
            for k, v in edit_positions.items():
                new_pose[k] = v.get()
            state["pose"] = new_pose

            frame["state"] = state
            self.c.sequence_frames[step_index] = frame
            self.refresh_sequence_listbox()
            editor.destroy()

        ttk.Button(btn_row, text="Save", command=save_edits, style="Success.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row, text="Cancel", command=editor.destroy).pack(side=tk.LEFT, padx=5)

    def open_seq_sg_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Sequence Default SG Settings")
        win.configure(bg=self.BG_COLOR)
        win.geometry("450x330")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        hdr = tk.Label(win, text="Default SG & mA Settings for Sequence",
                       bg=self.BG_COLOR, fg=self.ACCENT_BLUE, font=("Segoe UI", 11, "bold"))
        hdr.pack(pady=10)

        main_frame = tk.Frame(win, bg=self.PANEL_BG, highlightbackground=self.SURFACE_BG, highlightthickness=1)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

        def update_bg_recursive(w):
            c_name = w.winfo_class()
            if not c_name.startswith("T") and c_name not in ("Canvas", "Menu"):
                try:
                    w.config(bg=self.PANEL_BG)
                except tk.TclError:
                    pass
                if c_name == "Label":
                    txt = w.cget("text")
                    if txt in ("mA:", "Active:"):
                        w.config(fg=self.SUBTEXT)
            for child in w.winfo_children():
                update_bg_recursive(child)

        for dxl_id in config.motor_ids:
            row = tk.Frame(main_frame, bg=self.PANEL_BG)
            row.pack(fill=tk.X, padx=10, pady=5)

            motor_name = self.c.motor_names.get(dxl_id, f"Motor {dxl_id}")
            lbl_name = tk.Label(row, text=motor_name, bg=self.PANEL_BG, fg=self.ACCENT_GREEN, font=("Segoe UI", 9, "bold"), width=12, anchor="w")
            lbl_name.pack(side=tk.LEFT)

            chk = ttk.Checkbutton(row, text="Active", variable=self.seq_default_sg_vars[dxl_id],
                                  command=self.c.mark_seq_unsaved)
            chk.pack(side=tk.LEFT, padx=(10, 5))

            lbl_ma = tk.Label(row, text="1750 mA", bg=self.PANEL_BG, fg=self.ACCENT_PEACH, font=("Segoe UI", 9, "bold"), width=8)
            
            def make_scale_cb(lbl=lbl_ma, var=self.seq_default_ma_vars[dxl_id]):
                def cb(val):
                    v = int(float(val))
                    if var.get() != v:
                        var.set(v)
                        self.c.mark_seq_unsaved()
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

        btn_close = ttk.Button(win, text="Close", command=win.destroy, width=12)
        btn_close.pack(pady=10)

    def export_graph_menu(self):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Als Excel-Datei exportieren (.xls)", command=self.export_graph_excel)
        menu.add_command(label="Als CSV-Daten exportieren (.csv)", command=self.export_graph_csv)
        menu.add_command(label="Als Bild exportieren (.png)", command=self.export_graph_png)
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def export_graph_excel(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xls",
            filetypes=[("Excel 97-2003 Workbook", "*.xls"), ("All Files", "*.*")],
            title="Export graph data for Excel"
        )
        if not file_path:
            return
        try:
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
            
            xml_lines.append('   <Row>')
            xml_lines.append('    <Cell><Data ss:Type="String">Index</Data></Cell>')
            for dxl_id in config.motor_ids:
                name = self.c.motor_names.get(dxl_id, f"Motor_{dxl_id}")
                xml_lines.append(f'    <Cell><Data ss:Type="String">{name} Current (mA)</Data></Cell>')
                xml_lines.append(f'    <Cell><Data ss:Type="String">{name} Limit (mA)</Data></Cell>')
            xml_lines.append('   </Row>')
            
            for idx in range(50):
                xml_lines.append('   <Row>')
                xml_lines.append(f'    <Cell><Data ss:Type="Number">{idx}</Data></Cell>')
                for dxl_id in config.motor_ids:
                    motor = self.c.state.motors[dxl_id]
                    curr = motor.graph_history[idx]
                    lim = motor.limit_history[idx]
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
                
            messagebox.showinfo("Success", f"Excel-compatible file successfully exported to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not export Excel file:\n{e}")

    def export_graph_csv(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="Export graph data"
        )
        if not file_path:
            return
        try:
            import csv
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                header = ["Index"]
                for dxl_id in config.motor_ids:
                    name = self.c.motor_names.get(dxl_id, f"Motor_{dxl_id}")
                    header.extend([f"{name}_Current_mA", f"{name}_Limit_mA"])
                writer.writerow(header)
                for idx in range(50):
                    row = [idx]
                    for dxl_id in config.motor_ids:
                        motor = self.c.state.motors[dxl_id]
                        curr = motor.graph_history[idx]
                        lim = motor.limit_history[idx]
                        row.extend([curr, lim])
                    writer.writerow(row)
            messagebox.showinfo("Success", f"Data successfully exported to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not export data:\n{e}")

    def export_graph_png(self):
        if not ImageGrab:
            messagebox.showerror("Error", "Pillow package is required to export graph as PNG.")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Images", "*.png"), ("All Files", "*.*")],
            title="Export graph as image"
        )
        if not file_path:
            return
        try:
            self.root.update_idletasks()
            x = self.canvas.winfo_rootx()
            y = self.canvas.winfo_rooty()
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            img.save(file_path)
            messagebox.showinfo("Success", f"Image successfully saved under:\n{file_path}")
        except Exception as e:
            try:
                eps_path = file_path.rsplit(".", 1)[0] + ".eps"
                self.canvas.postscript(file=eps_path, colormode="color")
                messagebox.showinfo("Partial Success", f"PNG export failed, but EPS vector graphic was saved:\n{eps_path}")
            except Exception as eps_err:
                messagebox.showerror("Error", f"Could not export image:\n{e}\n\nEPS Error: {eps_err}")
