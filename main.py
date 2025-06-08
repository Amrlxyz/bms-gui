import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import can
import threading
import time
import struct
import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os # For flushing log file writer

# --- Constants ---
NUM_COLUMNS = 16
NUM_ROWS = 7
TOTAL_CELLS = NUM_COLUMNS * NUM_ROWS
CELL_FONT = ("Arial", 8) # Font for the text inside cells

# --- Configuration (USER MUST ADJUST THESE) ---
# Example: if your cells have CAN IDs from 0x18FF0000 to 0x18FF006F (112 IDs)
# The (r,c) to CAN ID mapping is also crucial.
# This example assumes CAN IDs are sequential starting from BASE_CELL_CAN_ID,
# and map linearly to cells row by row.
BASE_CELL_CAN_ID = 0x069 # !!! USER: Replace with your actual base CAN ID !!!
# Voltage scaling:
# Raw value is a signed 16-bit integer (-32768 to 32767)
# Define how this raw value maps to your actual voltage.
# Example: If -32768 maps to 0.0V and 32767 maps to 1.0V
RAW_VALUE_MIN = -32768
RAW_VALUE_MAX = 32767
VOLTAGE_TARGET_MIN = 0.0 # !!! USER: Adjust to your minimum expected voltage !!!
VOLTAGE_TARGET_MAX = 1.0 # !!! USER: Adjust to your maximum expected voltage !!!
# --- End Configuration ---


# --- Global Variables (managed carefully) ---
# These are module-level to be accessible by the CAN listener thread and app methods.
can_bus_instance = None # Stores the python-can bus object
can_listener_thread_obj = None # Stores the thread object
stop_can_thread_event = threading.Event() # Event to signal the thread to stop
log_file_writer_obj = None # File object for logging
is_logging_active = False
is_playback_mode = False


class CanTelemetryApp:
    def __init__(self, root_window):
        self.root = root_window
        self.root.title("CAN Telemetry Viewer")
        self.root.geometry("1000x750") # Adjusted initial size

        # --- Data Storage ---
        # cell_data: {cell_id_internal: {'voltage': float, 'flags': int, 
        #                               'widget': tk.Canvas, 'value_label': ttk.Label,
        #                               'raw_value': int, 'last_update': float}}
        self.cell_data = {}
        # cell_history: {cell_id_internal: [(timestamp, voltage), ...]}
        self.cell_history = {}

        # Initialize data structures for all cells
        for i in range(TOTAL_CELLS):
            internal_id = i
            self.cell_data[internal_id] = {
                'voltage': 0.0, 'flags': 0, 'widget': None, 'value_label': None,
                'raw_value': 0, 'last_update': 0.0
            }
            self.cell_history[internal_id] = []

        self.create_widgets()
        self.update_grid_display() # Initial display with default values

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def get_internal_id_from_grid(self, r, c):
        """Maps grid row and column (0-indexed) to an internal cell ID (0 to TOTAL_CELLS-1)."""
        if 0 <= r < NUM_ROWS and 0 <= c < NUM_COLUMNS:
            return r * NUM_COLUMNS + c
        return None

    def get_grid_position_from_internal_id(self, internal_id_to_find):
        """Maps an internal cell ID back to its (row, column) in the grid."""
        if 0 <= internal_id_to_find < TOTAL_CELLS:
            r = internal_id_to_find // NUM_COLUMNS
            c = internal_id_to_find % NUM_COLUMNS
            return r, c
        return None, None

    def get_can_id_from_internal_id(self, internal_id):
        """
        Converts an internal cell ID (0 to TOTAL_CELLS-1) to its corresponding Extended CAN ID.
        !!! USER: This logic might need adjustment based on your CAN ID allocation scheme. !!!
        This example assumes sequential CAN IDs.
        """
        if 0 <= internal_id < TOTAL_CELLS:
            return BASE_CELL_CAN_ID + internal_id
        return None

    def get_internal_id_from_can_id(self, arbitration_id):
        """
        Converts a received Extended CAN ID to an internal cell ID (0 to TOTAL_CELLS-1).
        Returns None if the CAN ID is not in the expected range for the monitored cells.
        !!! USER: This logic is critical and must match your CAN ID allocation. !!!
        """
        if BASE_CELL_CAN_ID <= arbitration_id < (BASE_CELL_CAN_ID + TOTAL_CELLS):
            return arbitration_id - BASE_CELL_CAN_ID
        return None

    def create_widgets(self):
        # --- Menu ---
        menubar = tk.Menu(self.root)
        self.filemenu = tk.Menu(menubar, tearoff=0)
        self.filemenu.add_command(label="Connect to CAN", command=self.connect_can_dialog)
        self.filemenu.add_command(label="Disconnect CAN", command=self.disconnect_can, state=tk.DISABLED)
        self.filemenu.add_separator()
        self.filemenu.add_command(label="Load Log File", command=self.load_log_file_dialog)
        self.filemenu.add_separator()
        self.filemenu.add_command(label="Exit", command=self.on_closing)
        menubar.add_cascade(label="File", menu=self.filemenu)
        self.root.config(menu=menubar)

        # --- Main Display Frame (16x7 Grid) ---
        self.grid_frame = ttk.LabelFrame(self.root, text="Cell Voltages")
        self.grid_frame.pack(padx=10, pady=10, fill="both", expand=True)

        for r in range(NUM_ROWS):
            self.grid_frame.grid_rowconfigure(r, weight=1, minsize=50) 
            for c in range(NUM_COLUMNS):
                self.grid_frame.grid_columnconfigure(c, weight=1, minsize=60) # Adjusted minsize for text
                internal_id = self.get_internal_id_from_grid(r, c)
                if internal_id is None: continue

                # Each cell is a Frame containing a Canvas (for bg color) and a Label (for text)
                cell_container = tk.Frame(self.grid_frame, borderwidth=1, relief="solid", bg="lightgrey")
                cell_container.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)
                
                # Canvas for background color, covers the whole container
                # We don't strictly need a separate canvas if the Frame's bg is updated,
                # but this keeps the concept of a 'widget' for background separate.
                # Let's simplify: the cell_container itself will have its background changed.
                # The label will be placed inside this frame.
                
                value_label = ttk.Label(cell_container, text="--- V", anchor="center", font=CELL_FONT)
                value_label.place(relx=0.5, rely=0.5, anchor="center") # Center the label in the frame

                # Bind clicks to the container and label to show graph
                cell_container.bind("<Button-1>", lambda event, rid=internal_id: self.show_cell_graph(rid))
                value_label.bind("<Button-1>", lambda event, rid=internal_id: self.show_cell_graph(rid))
                
                # Store the container (for bg) and label (for text)
                self.cell_data[internal_id]['widget'] = cell_container # widget is now the Frame
                self.cell_data[internal_id]['value_label'] = value_label


        # --- Statistics Bar ---
        self.stats_frame = ttk.LabelFrame(self.root, text="Statistics")
        self.stats_frame.pack(padx=10, pady=(0, 10), fill="x")

        self.total_voltage_label = ttk.Label(self.stats_frame, text="Total Voltage: N/A", width=25)
        self.total_voltage_label.pack(side=tk.LEFT, padx=5, pady=2)
        self.avg_voltage_label = ttk.Label(self.stats_frame, text="Average Voltage: N/A", width=25)
        self.avg_voltage_label.pack(side=tk.LEFT, padx=5, pady=2)
        self.min_voltage_label = ttk.Label(self.stats_frame, text="Min Voltage: N/A", width=30)
        self.min_voltage_label.pack(side=tk.LEFT, padx=5, pady=2)
        self.max_voltage_label = ttk.Label(self.stats_frame, text="Max Voltage: N/A", width=30)
        self.max_voltage_label.pack(side=tk.LEFT, padx=5, pady=2)
        self.cells_reporting_label = ttk.Label(self.stats_frame, text="Cells Reporting: 0/0", width=20)
        self.cells_reporting_label.pack(side=tk.LEFT, padx=5, pady=2)


        # --- Status Bar ---
        self.status_bar = ttk.Label(self.root, text="Status: Disconnected", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def get_text_color_for_background(self, bg_color_hex):
        """Determines if text should be black or white based on background luminance."""
        try:
            bg_color_hex = bg_color_hex.lstrip('#')
            if len(bg_color_hex) != 6: # Basic validation for hex string
                return "black" 
            r_hex, g_hex, b_hex = bg_color_hex[0:2], bg_color_hex[2:4], bg_color_hex[4:6]
            r, g, b = int(r_hex, 16), int(g_hex, 16), int(b_hex, 16)
            # Calculate luminance (YIQ formula simplified)
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            return "white" if luminance < 0.5 else "black"
        except ValueError: # Fallback in case of invalid hex conversion
            return "black"
        except Exception: # General fallback
            return "black"

    def connect_can_dialog(self):
        global can_bus_instance, is_logging_active, log_file_writer_obj, is_playback_mode, can_listener_thread_obj

        if can_bus_instance and can_bus_instance.is_connected:
            messagebox.showinfo("Info", "Already connected to CAN bus.")
            return
        if is_playback_mode:
            messagebox.showwarning("Playback Active", "Cannot connect to live CAN while in playback mode.")
            return

        port = simpledialog.askstring("CAN Port", "Enter SLCAN port (e.g., COM3 or /dev/ttyUSB0):", parent=self.root)
        if not port: return
        try:
            common_bitrates = ["125000", "250000", "500000", "1000000"]
            bitrate_str = simpledialog.askstring("CAN Bitrate", f"Enter bitrate (e.g., {', '.join(common_bitrates)}):", initialvalue="500000", parent=self.root)
            if not bitrate_str: return
            bitrate = int(bitrate_str)
        except (ValueError, TypeError):
            messagebox.showerror("Error", "Invalid bitrate. Please enter a number.", parent=self.root)
            return

        try:
            self.status_bar.config(text=f"Status: Connecting to {port} at {bitrate} bps...")
            self.root.update_idletasks()
            # can_bus_instance = can.interface.Bus(interface='slcan', channel=port, bitrate=bitrate)
            can_bus_instance = can.Bus(interface="slcan", channel="/dev/serial/by-id/usb-WeAct_Studio_USB2CANV1_ComPort_AAA120643984-if00", bitrate=500000)
            self.status_bar.config(text=f"Status: Connected to {port} at {bitrate} bps")
            self.filemenu.entryconfig("Connect to CAN", state=tk.DISABLED)
            self.filemenu.entryconfig("Disconnect CAN", state=tk.NORMAL)
            self.filemenu.entryconfig("Load Log File", state=tk.DISABLED)
            stop_can_thread_event.clear()
            can_listener_thread_obj = threading.Thread(target=self._can_listener_loop, daemon=True)
            can_listener_thread_obj.start()
            log_filename = f"can_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            log_file_writer_obj = open(log_filename, "w", encoding='utf-8')
            log_file_writer_obj.write("timestamp,arbitration_id,data_hex,dlc,is_extended_id\n")
            is_logging_active = True
            messagebox.showinfo("Logging", f"Logging CAN data to {log_filename}", parent=self.root)
        except can.CanError as e:
            messagebox.showerror("CAN Connection Error", f"Failed to connect to CAN bus on {port}: {e}", parent=self.root)
            if can_bus_instance: can_bus_instance = None
            self.status_bar.config(text="Status: Connection Failed")
        except Exception as e:
            messagebox.showerror("Connection Error", f"An unexpected error occurred: {e}", parent=self.root)
            if can_bus_instance: can_bus_instance = None
            self.status_bar.config(text="Status: Connection Failed")

    def disconnect_can(self):
        global can_bus_instance, is_logging_active, log_file_writer_obj, can_listener_thread_obj
        if can_bus_instance:
            self.status_bar.config(text="Status: Disconnecting...")
            self.root.update_idletasks()
            stop_can_thread_event.set()
            if can_listener_thread_obj and can_listener_thread_obj.is_alive():
                can_listener_thread_obj.join(timeout=2.0)
            try:
                can_bus_instance.shutdown()
            except Exception as e:
                print(f"Error during CAN bus shutdown: {e}")
            can_bus_instance = None
            self.status_bar.config(text="Status: Disconnected")
            self.filemenu.entryconfig("Connect to CAN", state=tk.NORMAL)
            self.filemenu.entryconfig("Disconnect CAN", state=tk.DISABLED)
            self.filemenu.entryconfig("Load Log File", state=tk.NORMAL)
        if is_logging_active and log_file_writer_obj:
            try:
                log_file_writer_obj.close()
            except Exception as e:
                print(f"Error closing log file: {e}")
            log_file_writer_obj = None
            is_logging_active = False

    def _can_listener_loop(self):
        global can_bus_instance, log_file_writer_obj, is_logging_active, stop_can_thread_event
        if not can_bus_instance:
            self.root.after(0, lambda: self.status_bar.config(text="Status: Listener aborted (no bus)."))
            return
        self.root.after(0, lambda: self.status_bar.config(text="Status: Listening for CAN data..."))
        try:
            for msg in can_bus_instance:
                if stop_can_thread_event.is_set(): break
                if msg.is_extended_id:
                    if is_logging_active and log_file_writer_obj:
                        log_entry = f"{msg.timestamp},{msg.arbitration_id},{msg.data.hex()},{msg.dlc},{msg.is_extended_id}\n"
                        log_file_writer_obj.write(log_entry)
                        log_file_writer_obj.flush()
                        if hasattr(os, 'fsync'): os.fsync(log_file_writer_obj.fileno())
                    self.root.after(0, self.process_can_message, msg, True, msg.timestamp)
                if stop_can_thread_event.is_set(): break
        except can.CanError as e:
            print(f"CAN Error in listener thread: {e}")
            self.root.after(0, lambda: messagebox.showerror("CAN Error", f"CAN communication error: {e}. Disconnecting.", parent=self.root))
            self.root.after(0, self.disconnect_can)
        except Exception as e:
            print(f"Unexpected error in listener thread: {e}")
            self.root.after(0, lambda: self.status_bar.config(text=f"Status: Listener error - {type(e).__name__}"))
        finally:
            print("CAN listener thread stopped.")
            self.root.after(0, lambda: self.status_bar.config(text="Status: Listener stopped or Disconnected."))

    def process_can_message(self, msg_object_or_log_line, is_live_data, timestamp_override=None):
        arbitration_id = None
        data_bytes = None
        msg_timestamp = time.time()
        if is_live_data:
            if not msg_object_or_log_line.is_extended_id or msg_object_or_log_line.dlc < 3: return
            arbitration_id = msg_object_or_log_line.arbitration_id
            data_bytes = msg_object_or_log_line.data
            msg_timestamp = timestamp_override if timestamp_override is not None else msg_object_or_log_line.timestamp
        else:
            try:
                parts = msg_object_or_log_line.strip().split(',')
                if len(parts) < 5: return
                msg_timestamp = float(parts[0])
                arbitration_id = int(parts[1])
                data_hex_str = parts[2]
                if len(data_hex_str) < 6 : return
                data_bytes = bytes.fromhex(data_hex_str)
            except ValueError as e:
                print(f"Error parsing log line: '{msg_object_or_log_line.strip()}' - {e}")
                return
            except Exception as e:
                print(f"Unexpected error parsing log line: '{msg_object_or_log_line.strip()}' - {e}")
                return

        internal_cell_id = self.get_internal_id_from_can_id(arbitration_id)
        if internal_cell_id is not None and internal_cell_id in self.cell_data:
            try:
                raw_voltage_value = struct.unpack('>h', data_bytes[:2])[0]
                if RAW_VALUE_MAX == RAW_VALUE_MIN:
                    scaled_voltage = VOLTAGE_TARGET_MIN 
                else:
                    scaled_voltage = ((raw_voltage_value - RAW_VALUE_MIN) / (RAW_VALUE_MAX - RAW_VALUE_MIN)) * \
                                     (VOLTAGE_TARGET_MAX - VOLTAGE_TARGET_MIN) + VOLTAGE_TARGET_MIN
                scaled_voltage = max(VOLTAGE_TARGET_MIN, min(VOLTAGE_TARGET_MAX, scaled_voltage))
                flags_byte = data_bytes[2]
                self.cell_data[internal_cell_id]['voltage'] = scaled_voltage
                self.cell_data[internal_cell_id]['flags'] = flags_byte
                self.cell_data[internal_cell_id]['raw_value'] = raw_voltage_value
                self.cell_data[internal_cell_id]['last_update'] = msg_timestamp
                self.cell_history[internal_cell_id].append((msg_timestamp, scaled_voltage))
                max_history_points = 500
                if len(self.cell_history[internal_cell_id]) > max_history_points:
                    self.cell_history[internal_cell_id].pop(0)
                self.update_single_cell_display(internal_cell_id)
                self.update_statistics_display()
            except struct.error as e:
                print(f"Error unpacking data for CAN ID {hex(arbitration_id)} (Internal ID: {internal_cell_id}): {e}. Data: {data_bytes.hex()}")
            except IndexError:
                print(f"Data too short for CAN ID {hex(arbitration_id)} (Internal ID: {internal_cell_id}). DLC={len(data_bytes)}, Data: {data_bytes.hex()}")
            except Exception as e:
                print(f"Unexpected error processing message for CAN ID {hex(arbitration_id)} (Internal ID: {internal_cell_id}): {e}")

    def update_single_cell_display(self, internal_cell_id):
        if internal_cell_id not in self.cell_data: return
        
        cell_info = self.cell_data[internal_cell_id]
        cell_frame_widget = cell_info.get('widget') # This is the Frame
        value_label_widget = cell_info.get('value_label') # This is the Label

        if not cell_frame_widget or not value_label_widget: return

        voltage = cell_info['voltage']
        color_hex = self.get_color_for_voltage(voltage)
        text_color = self.get_text_color_for_background(color_hex)

        cell_frame_widget.config(bg=color_hex)
        value_label_widget.config(text=f"{voltage:.2f}V", background=color_hex, foreground=text_color)

    def update_grid_display(self):
        for r_idx in range(NUM_ROWS):
            for c_idx in range(NUM_COLUMNS):
                internal_id = self.get_internal_id_from_grid(r_idx, c_idx)
                if internal_id is not None:
                    self.update_single_cell_display(internal_id)

    def get_color_for_voltage(self, voltage):
        if VOLTAGE_TARGET_MAX == VOLTAGE_TARGET_MIN: return "#00FF00"
        normalized_voltage = (voltage - VOLTAGE_TARGET_MIN) / (VOLTAGE_TARGET_MAX - VOLTAGE_TARGET_MIN)
        normalized_voltage = max(0.0, min(1.0, normalized_voltage))
        r_float, g_float = 0.0, 0.0
        if normalized_voltage > 0.5:
            r_float = (1.0 - (normalized_voltage - 0.5) * 2.0)
            g_float = 1.0
        else:
            r_float = 1.0
            g_float = (normalized_voltage * 2.0)
        r, g, b = int(r_float * 255), int(g_float * 255), 0
        return f'#{r:02x}{g:02x}{b:02x}'

    def show_cell_graph(self, internal_cell_id_clicked):
        if internal_cell_id_clicked is None or internal_cell_id_clicked not in self.cell_history:
            messagebox.showerror("Error", "No data available for this cell.", parent=self.root)
            return
        history = self.cell_history[internal_cell_id_clicked]
        if not history:
            messagebox.showinfo("Info", f"No historical data for Cell (Internal ID: {internal_cell_id_clicked}).", parent=self.root)
            return

        popup = tk.Toplevel(self.root)
        r, c = self.get_grid_position_from_internal_id(internal_cell_id_clicked)
        actual_can_id = self.get_can_id_from_internal_id(internal_cell_id_clicked)
        popup.title(f"Trend - Cell R{r+1}C{c+1} (ID {internal_cell_id_clicked}, CAN: {hex(actual_can_id if actual_can_id else 0)})")
        popup.geometry("750x600")
        fig, ax = plt.subplots()
        timestamps, voltages = zip(*history)
        if timestamps:
            start_time = timestamps[0]
            relative_timestamps = [(ts - start_time) for ts in timestamps]
            ax.plot(relative_timestamps, voltages, marker='.', linestyle='-', markersize=4)
            ax.set_xlabel("Time (seconds from first data point for this cell)")
        else:
            ax.plot([], []) 
            ax.set_xlabel("Time")
        ax.set_ylabel(f"Voltage (Scaled, Target {VOLTAGE_TARGET_MIN:.2f}-{VOLTAGE_TARGET_MAX:.2f}V)")
        ax.set_title(f"Voltage Trend for Cell (Internal ID: {internal_cell_id_clicked})")
        ax.grid(True)
        fig.tight_layout(pad=1.5)
        canvas = FigureCanvasTkAgg(fig, master=popup)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        canvas.draw()
        details_frame = ttk.Frame(popup)
        details_frame.pack(pady=10, padx=10, fill="x")
        flags_frame = ttk.LabelFrame(details_frame, text="Flags (from 3rd byte of CAN data)")
        flags_frame.pack(side=tk.LEFT, padx=5, fill="y", expand=True)
        current_flags = self.cell_data[internal_cell_id_clicked].get('flags', 0)
        for i in range(8):
            flag_is_set = (current_flags >> i) & 1
            ttk.Label(flags_frame, text=f"Flag {i}: {flag_is_set}").pack(anchor="w", padx=5)
        raw_value_frame = ttk.LabelFrame(details_frame, text="Last Raw Value")
        raw_value_frame.pack(side=tk.LEFT, padx=5, fill="y", expand=True)
        raw_val = self.cell_data[internal_cell_id_clicked].get('raw_value', 'N/A')
        ttk.Label(raw_value_frame, text=f"Signed Int: {raw_val}").pack(anchor="w", padx=5)
        last_update_ts = self.cell_data[internal_cell_id_clicked].get('last_update', 0.0)
        last_update_str = datetime.datetime.fromtimestamp(last_update_ts).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] if last_update_ts > 0 else "N/A"
        ttk.Label(raw_value_frame, text=f"Last Update: {last_update_str}").pack(anchor="w", padx=5)

    def update_statistics_display(self):
        active_voltages = []
        reporting_cell_count = 0
        for internal_id in self.cell_data:
            cell_info = self.cell_data[internal_id]
            if cell_info.get('widget') is not None and cell_info.get('last_update', 0.0) > 0:
                active_voltages.append(cell_info['voltage'])
                reporting_cell_count +=1
        if not active_voltages:
            self.total_voltage_label.config(text="Total Voltage: N/A")
            self.avg_voltage_label.config(text="Average Voltage: N/A")
            self.min_voltage_label.config(text="Min Voltage: N/A")
            self.max_voltage_label.config(text="Max Voltage: N/A")
            self.cells_reporting_label.config(text=f"Cells Reporting: 0/{TOTAL_CELLS}")
            return
        total_v, avg_v = sum(active_voltages), sum(active_voltages) / len(active_voltages)
        min_v, max_v = min(active_voltages), max(active_voltages)
        self.total_voltage_label.config(text=f"Total Voltage: {total_v:.2f} V")
        self.avg_voltage_label.config(text=f"Average Voltage: {avg_v:.3f} V")
        min_v_cell_ids = [id for id, data in self.cell_data.items() if data.get('last_update',0.0)>0 and abs(data['voltage']-min_v)<1e-5]
        max_v_cell_ids = [id for id, data in self.cell_data.items() if data.get('last_update',0.0)>0 and abs(data['voltage']-max_v)<1e-5]
        min_v_cell_locs = ", ".join([f"R{self.get_grid_position_from_internal_id(id)[0]+1}C{self.get_grid_position_from_internal_id(id)[1]+1}" for id in min_v_cell_ids[:2]])
        max_v_cell_locs = ", ".join([f"R{self.get_grid_position_from_internal_id(id)[0]+1}C{self.get_grid_position_from_internal_id(id)[1]+1}" for id in max_v_cell_ids[:2]])
        self.min_voltage_label.config(text=f"Min Voltage: {min_v:.3f} V ({min_v_cell_locs})")
        self.max_voltage_label.config(text=f"Max Voltage: {max_v:.3f} V ({max_v_cell_locs})")
        self.cells_reporting_label.config(text=f"Cells Reporting: {reporting_cell_count}/{TOTAL_CELLS}")

    def load_log_file_dialog(self):
        global is_playback_mode
        if can_bus_instance and can_bus_instance.is_connected:
            messagebox.showwarning("Playback", "Disconnect from live CAN bus before loading a log file.", parent=self.root)
            return
        filepath = filedialog.askopenfilename(title="Open CAN Log File", filetypes=(("CSV Log files", "*.csv"),("Log files", "*.log"), ("All files", "*.*")), parent=self.root)
        if not filepath: return
        for internal_id in self.cell_data.keys():
            self.cell_data[internal_id].update({'voltage':0.0,'flags':0,'raw_value':0,'last_update':0.0})
            self.cell_history[internal_id] = []
        self.update_grid_display()
        self.update_statistics_display()
        is_playback_mode = True
        self.status_bar.config(text=f"Status: Playing back from {os.path.basename(filepath)}")
        self.filemenu.entryconfig("Connect to CAN", state=tk.DISABLED)
        self.filemenu.entryconfig("Load Log File", state=tk.DISABLED)
        playback_thread = threading.Thread(target=self._playback_log_file_thread, args=(filepath,), daemon=True)
        playback_thread.start()

    def _playback_log_file_thread(self, filepath):
        global is_playback_mode
        log_lines = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                header = f.readline().strip()
                if not header.startswith("timestamp,arbitration_id,data_hex"):
                    self.root.after(0, lambda: messagebox.showwarning("Log Format", "Log file does not seem to have the expected CSV header.", parent=self.root))
                log_lines = f.readlines()
            if not log_lines:
                self.root.after(0, lambda: messagebox.showinfo("Playback", "Log file is empty (after header).", parent=self.root))
                self.root.after(0, lambda: self.status_bar.config(text="Status: Playback finished (empty log)."))
                return
            
            first_msg_timestamp = None
            try:
                first_msg_parts = log_lines[0].strip().split(',')
                if len(first_msg_parts) > 0: first_msg_timestamp = float(first_msg_parts[0])
            except ValueError: first_msg_timestamp = None
            playback_start_time = time.time()

            for i, line in enumerate(log_lines):
                if not is_playback_mode: break
                current_msg_timestamp_from_log = None
                try:
                    current_msg_parts = line.strip().split(',')
                    if len(current_msg_parts) > 0: current_msg_timestamp_from_log = float(current_msg_parts[0])
                except ValueError: pass
                if first_msg_timestamp is not None and current_msg_timestamp_from_log is not None:
                    time_since_first_log_msg = current_msg_timestamp_from_log - first_msg_timestamp
                    target_processing_time = playback_start_time + time_since_first_log_msg
                    sleep_duration = target_processing_time - time.time()
                    if sleep_duration > 0.001: time.sleep(sleep_duration)
                else:
                    time.sleep(0.001)
                self.root.after(0, self.process_can_message, line, False, current_msg_timestamp_from_log)
                if i % 50 == 0:
                    progress_percent = ((i + 1) / len(log_lines)) * 100
                    self.root.after(0, lambda p=progress_percent: self.status_bar.config(text=f"Status: Playing back... ({p:.1f}%)"))
            if is_playback_mode:
                 self.root.after(0, lambda: messagebox.showinfo("Playback", "Log file playback finished.", parent=self.root))
                 self.root.after(0, lambda: self.status_bar.config(text="Status: Playback finished."))
        except FileNotFoundError:
            self.root.after(0, lambda: messagebox.showerror("Log File Error", f"File not found: {filepath}", parent=self.root))
            self.root.after(0, lambda: self.status_bar.config(text="Status: Playback error - File not found."))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Log File Error", f"Error reading or processing log file: {e}", parent=self.root))
            self.root.after(0, lambda: self.status_bar.config(text=f"Status: Playback error - {type(e).__name__}."))
        finally:
            self.root.after(0, self._finalize_playback_mode)

    def _finalize_playback_mode(self):
        global is_playback_mode
        is_playback_mode = False
        self.filemenu.entryconfig("Connect to CAN", state=tk.NORMAL)
        self.filemenu.entryconfig("Load Log File", state=tk.NORMAL)
        if not (can_bus_instance and can_bus_instance.is_connected):
             self.status_bar.config(text="Status: Disconnected (Playback ended)")

    def on_closing(self):
        global is_playback_mode, stop_can_thread_event
        if messagebox.askokcancel("Quit", "Do you want to quit?", parent=self.root):
            is_playback_mode = False 
            stop_can_thread_event.set() 
            self.disconnect_can() 
            self.root.destroy()

# --- Main Execution ---
if __name__ == "__main__":
    main_root_window = tk.Tk()
    app_instance = CanTelemetryApp(main_root_window)
    main_root_window.mainloop()
