import tkinter as tk
from tkinter import ttk
import queue
import datetime
from pathlib import Path
import can
import cantools
from cantools.database.can import Message, Signal, Database, Node
from pprint import pprint


# Matplotlib for plotting
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# --- Helper Functions ---

def interpolate_color(value: float, min_val: float, max_val: float, start_hex: str, end_hex: str) -> str:
    """Interpolates a color based on a value within a range."""
    if value is None: return "#808080" # Default gray for no data
    # Clamp the value within the specified range
    value = max(min_val, min(value, max_val))
    
    # Convert hex to RGB
    s_r, s_g, s_b = int(start_hex[1:3], 16), int(start_hex[3:5], 16), int(start_hex[5:7], 16)
    e_r, e_g, e_b = int(end_hex[1:3], 16), int(end_hex[3:5], 16), int(end_hex[5:7], 16)
    
    # Calculate the ratio
    ratio = (value - min_val) / (max_val - min_val)
    
    # Interpolate RGB values
    n_r = int(s_r + ratio * (e_r - s_r))
    n_g = int(s_g + ratio * (e_g - s_g))
    n_b = int(s_b + ratio * (e_b - s_b))
    
    return f"#{n_r:02x}{n_g:02x}{n_b:02x}"

# --- Original CAN Listener (Unchanged) ---

class CANListener(can.Listener):
    """A can.Listener that puts received messages into a queue."""
    def __init__(self, msg_queue: queue.Queue):
        self.queue = msg_queue

    def on_message_received(self, msg: can.Message):
        self.queue.put(msg)
    
    def on_error(self, exc: Exception):
        print(f"An error occurred in the CAN listener: {exc}")

# --- New UI Component Classes ---

class SegmentWidget(ttk.Frame):
    """A widget representing a single BMS segment."""
    def __init__(self, parent, seg_id: int, select_callback, plot_callback):
        super().__init__(parent, borderwidth=1, relief="solid")
        self.seg_id = seg_id
        
        # --- Layout Configuration ---
        self.columnconfigure(0, weight=5) # Temp
        self.columnconfigure(1, weight=1) # Fault
        self.columnconfigure(2, weight=1) # Comms_Fault
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # --- Widgets ---
        self.voltage_label      = ttk.Label(self, text="--- V"  , anchor="center", background="gray", cursor="hand2")
        self.temp_label         = ttk.Label(self, text="-- °C"  , anchor="center", background="gray", cursor="hand2")
        self.fault_label        = ttk.Label(self, text="FT"     , anchor="center", background="gray", cursor="hand2")
        self.commsFault_label   = ttk.Label(self, text="CF"     , anchor="center", background="gray", cursor="hand2")

        self.voltage_label.grid     (row=0, column=0, columnspan=3, sticky="nsew", pady=1)
        self.temp_label.grid        (row=1, column=0, sticky="nsew", padx=(0,1))
        self.fault_label.grid       (row=1, column=1, sticky="nsew", padx=(0,1))
        self.commsFault_label.grid  (row=1, column=2, sticky="nsew")
        
        # --- Click Binding ---
        # Bind individual labels for plotting
        voltage_signal      = f"SEG_{self.seg_id}_IC_Voltage"
        temp_signal         = f"SEG_{self.seg_id}_IC_Temp"
        fault_signal        = f"SEG_{self.seg_id}_isFaultDetected"
        comms_fault_signal  = f"SEG_{self.seg_id}_isCommsError"
        
        self.voltage_label.bind("<Button-1>",       lambda event: [select_callback(self.seg_id), plot_callback(voltage_signal)])
        self.temp_label.bind("<Button-1>",          lambda event: [select_callback(self.seg_id), plot_callback(temp_signal)])
        self.fault_label.bind("<Button-1>",         lambda event: [select_callback(self.seg_id), plot_callback(fault_signal)])
        self.commsFault_label.bind("<Button-1>",    lambda event: [select_callback(self.seg_id), plot_callback(comms_fault_signal)])


    def update_data(self, voltage: float, temp: float, is_faulted: bool, is_comms_fault: bool):
        """Updates the text and colors of the segment display."""
        # Update Voltage
        if voltage is not None:
            self.voltage_label.config(text=f"{voltage:.3f} V")
            # Assuming a segment voltage range of 16 cells * 3.0V to 16 * 4.2V
            color = interpolate_color(voltage, 48.0, 67.2, "#FF0000", "#00FF00") # Red to Green
            self.voltage_label.config(background=color)

        # Update Temperature
        if temp is not None:
            self.temp_label.config(text=f"{temp:.2f} °C")
            color = interpolate_color(temp, 10, 100, "#00FF00", "#FF0000") # Green to Red
            self.temp_label.config(background=color)
        
        # Update Flags
        if is_faulted is not None:
            self.fault_label.config(background="#FF0000" if is_faulted else "gray") # Red or Gray
        
        if is_comms_fault is not None:
            self.commsFault_label.config(background="#FFA500" if is_comms_fault else "gray") # Orange or Gray


class CellWidget(ttk.Frame):
    """A widget representing a single BMS cell."""
    def __init__(self, parent, cell_id: tuple, select_callback, plot_callback):
        super().__init__(parent, borderwidth=1, relief="solid")
        self.cell_id = cell_id # cell_id is a tuple (row, col)
        
        # --- Layout Configuration ---
        self.columnconfigure(0, weight=5) # Temp
        self.columnconfigure(1, weight=1) # Fault
        self.columnconfigure(2, weight=1) # Discharging
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # --- Widgets ---
        self.voltage_label      = ttk.Label(self, text="--- V"  , anchor="center", background="gray", cursor="hand2")
        self.voltageDiff_label  = ttk.Label(self, text="-- mV"  , anchor="center", background="gray", cursor="hand2")
        self.temp_label         = ttk.Label(self, text="-- °C"  , anchor="center", background="gray", cursor="hand2")
        self.fault_label        = ttk.Label(self, text="FT"     , anchor="center", background="gray", cursor="hand2")
        self.discharging_label  = ttk.Label(self, text="DC"     , anchor="center", background="gray", cursor="hand2")

        self.voltage_label.grid     (row=0, column=0, columnspan=1, sticky="nsew", pady=1, padx=(0,1))
        self.voltageDiff_label.grid (row=0, column=1, columnspan=2, sticky="nsew", pady=1)
        self.temp_label.grid        (row=1, column=0, sticky="nsew", padx=(0,1))
        self.fault_label.grid       (row=1, column=1, sticky="nsew", padx=(0,1))
        self.discharging_label.grid (row=1, column=2, sticky="nsew")
        
        # --- Click Binding ---
        # Bind individual labels for plotting
        row, col = self.cell_id
        seg = col + 1
        cell_idx = row + 1
        voltage_signal      = f"CELL_{seg}x{cell_idx}_Voltage"
        diff_signal         = f"CELL_{seg}x{cell_idx}_VoltageDiff"
        temp_signal         = f"CELL_{seg}x{cell_idx}_Temp"
        fault_signal        = f"CELL_{seg}x{cell_idx}_isFaultDetected"
        discharge_signal    = f"CELL_{seg}x{cell_idx}_isDischarging"
        
        self.voltage_label.bind("<Button-1>",       lambda event: [select_callback(self.cell_id), plot_callback(voltage_signal)])
        self.voltageDiff_label.bind("<Button-1>",   lambda event: [select_callback(self.cell_id), plot_callback(diff_signal)])
        self.temp_label.bind("<Button-1>",          lambda event: [select_callback(self.cell_id), plot_callback(temp_signal)])
        self.fault_label.bind("<Button-1>",         lambda event: [select_callback(self.cell_id), plot_callback(fault_signal)])
        self.discharging_label.bind("<Button-1>",   lambda event: [select_callback(self.cell_id), plot_callback(discharge_signal)])


    def update_data(self, voltage: float, voltageDiff: int, temp: float, is_faulted: bool, is_discharging: bool):
        """Updates the text and colors of the cell display."""
        # Update Voltage
        if voltage is not None:
            self.voltage_label.config(text=f"{voltage:.3f} V")
            color = interpolate_color(voltage, 3.0, 4.2, "#FF0000", "#00FF00") # Red to Green
            self.voltage_label.config(background=color)

        # Update Diff
        if voltageDiff is not None:
            self.voltageDiff_label.config(text=f"{voltageDiff:+} mV")
            color = interpolate_color(abs(voltageDiff), 0, 500, "#00FF00", "#FF0000") # Green to Red
            self.voltageDiff_label.config(background=color)

        # Update Temperature
        if temp is not None:
            self.temp_label.config(text=f"{temp:.2f} °C")
            color = interpolate_color(temp, 10, 100, "#00FF00", "#FF0000") # Green to Red
            self.temp_label.config(background=color)
        
        # Update Flags
        if is_faulted is not None:
            self.fault_label.config(background="#FF0000" if is_faulted else "gray") # Red or Gray
        
        if is_discharging is not None:
            self.discharging_label.config(background="#0000FF" if is_discharging else "gray") # Blue or Gray


class SystemInfoFrame(ttk.Frame):
    """A frame to display overall system voltage and current."""
    def __init__(self, parent, plot_callback):
        super().__init__(parent, borderwidth=1, relief="solid", padding=10)

        # Configure grid layout: 2 columns, 2 rows
        self.columnconfigure(0, weight=0) # Label column
        self.columnconfigure(1, weight=1) # Value column
        self.rowconfigure(0, weight=1)    # Voltage row
        self.rowconfigure(1, weight=1)    # Current row

        # --- Static Labels ---
        voltage_text_label = ttk.Label(self, text="Voltage:", font=("Helvetica", 32), anchor="w")
        voltage_text_label.grid(row=0, column=0, sticky="nsew", padx=5, pady=3)

        current_text_label = ttk.Label(self, text="Current:", font=("Helvetica", 32), anchor="w")
        current_text_label.grid(row=1, column=0, sticky="nsew", padx=5)

        # --- Value Labels ---
        self.voltage_value_label = ttk.Label(self, text="--- V", font=("Helvetica", 32), cursor="hand2", background="#D5D5D5", anchor="center")
        self.voltage_value_label.grid(row=0, column=1, sticky="nsew", pady=3)
        
        self.current_value_label = ttk.Label(self, text="--- A", font=("Helvetica", 32), cursor="hand2", background="#D5D5D5", anchor="center")
        self.current_value_label.grid(row=1, column=1, sticky="nsew")

        # Bind for plotting
        self.voltage_value_label.bind("<Button-1>", lambda e: plot_callback("BMS_Pack_Voltage"))
        self.current_value_label.bind("<Button-1>", lambda e: plot_callback("BMS_Pack_Current"))


    def update_values(self, voltage, current):
        if voltage is not None:
            self.voltage_value_label.config(text=f"{voltage:.2f} V")
        else:
            self.voltage_value_label.config(text="--- V")

        if current is not None:
            self.current_value_label.config(text=f"{current:.2f} A")
        else:
            self.current_value_label.config(text="--- A")
            

class LogFrame(ttk.LabelFrame):
    """A frame for displaying incoming CAN messages."""
    def __init__(self, parent):
        super().__init__(parent, text="CAN Log", padding=5)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Frame to hold listbox and scrollbars
        list_frame = ttk.Frame(self)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        h_scrollbar = ttk.Scrollbar(list_frame, orient="horizontal")

        self.text_list = tk.Listbox(list_frame, 
                                    yscrollcommand=v_scrollbar.set,
                                    xscrollcommand=h_scrollbar.set)
        
        v_scrollbar.config(command=self.text_list.yview)
        h_scrollbar.config(command=self.text_list.xview)
        
        # Grid placement
        self.text_list.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")

    def log_message(self, msg: str):
        """Inserts a message at the end of the listbox."""
        log_entry = f"{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]} | {msg}"
        self.text_list.insert(tk.END, log_entry)
        if self.text_list.size() > 500: # Keep the list from growing indefinitely
            self.text_list.delete(0)
        self.text_list.yview_moveto(1.0)


class Application(tk.Tk):
    def __init__(self, usb_can_path: str, dbc_path: str, bitrate: int):
        super().__init__()
        self.title("BMS CAN Bus Monitor")
        self.geometry("1400x900")

        # --- App State ---
        self.bus = None
        self.notifier = None
        self.asc_writer = None
        self.log_file = None
        self.start_timestamp = 0
        self.can_message_queue = queue.Queue()
        self.db: Database = cantools.database.load_file(dbc_path)

        # Data storage and UI component mapping
        self.data_log = {signal.name: [] for msg in self.db.messages for signal in msg.signals}
        self.data_units = {signal.name: signal.unit for msg in self.db.messages for signal in msg.signals}
        self.signal_to_widget_map = {}
        self.segments = []
        self.cells = []
        self.selected_segment_id = 1 # Default to segment 1
        self.selected_cell_id = (0, 0) # Default to cell (row=0, col=0)
        self.plotted_signal_name = None # Name of the signal currently in the plot
        
        # --- UI Setup ---
        self._initialize_ui_layout()
        self._initialize_ui_components()
        self._initialize_plot()

        # --- CAN Bus and Logging Initialization ---
        self._initialize_can_and_logging(usb_can_path, bitrate)

        # --- Protocol Handlers ---
        self.after(100, self.process_can_messages)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.on_segment_selected(1) # Highlight the default segment at startup
        self.on_cell_selected((0,0)) # Highlight the default cell at startup

    def _initialize_ui_layout(self):
        # Main layout frames
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        main_frame.columnconfigure(0, weight=3) # Cell grid and plot
        main_frame.columnconfigure(1, weight=1) # Right-side panel
        main_frame.rowconfigure(0, weight=1)

        # Left side (Segments + Cells + Plot)
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.rowconfigure(0, weight=0) # Segment grid (fixed size)
        left_frame.rowconfigure(1, weight=2) # Cell grid
        left_frame.rowconfigure(2, weight=1) # Plot
        left_frame.columnconfigure(0, weight=1)
        
        self.segment_grid_frame = ttk.Frame(left_frame)
        self.segment_grid_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        self.cell_grid_frame = ttk.Frame(left_frame)
        self.cell_grid_frame.grid(row=1, column=0, sticky="nsew")

        self.plot_frame = ttk.Frame(left_frame)
        self.plot_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))

        # Right side (Info + Log)
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.rowconfigure(0, weight=0) # System info (fixed size)
        right_frame.rowconfigure(1, weight=1) # Log (expanding)
        right_frame.columnconfigure(0, weight=1)

        self.system_info_frame = SystemInfoFrame(right_frame, self.on_signal_selected_for_plot)
        self.system_info_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        self.log_frame = LogFrame(right_frame)
        self.log_frame.grid(row=1, column=0, sticky="nsew")

    def _initialize_ui_components(self):
        num_cols = 7
        
        # --- Create Segment Widgets ---
        self.segments = [None for _ in range(num_cols)]
        for col in range(num_cols):
            self.segment_grid_frame.columnconfigure(col, weight=1)
            seg_id = col + 1 # Segments are 1-indexed
            segment_widget = SegmentWidget(self.segment_grid_frame, seg_id,
                                           self.on_segment_selected,
                                           self.on_signal_selected_for_plot)
            segment_widget.grid(row=0, column=col, sticky="nsew", padx=1, pady=1)
            self.segments[col] = segment_widget

            # Map signals to widget
            self.signal_to_widget_map[f"SEG_{seg_id}_IC_Voltage"] = segment_widget
            self.signal_to_widget_map[f"SEG_{seg_id}_IC_Temp"] = segment_widget
            self.signal_to_widget_map[f"SEG_{seg_id}_isFaultDetected"] = segment_widget
            self.signal_to_widget_map[f"SEG_{seg_id}_isCommsError"] = segment_widget

        # --- Create Cell Widgets ---
        num_rows = 16
        self.cells = [[None for _ in range(num_cols)] for _ in range(num_rows)]

        for row in range(num_rows):
            self.cell_grid_frame.rowconfigure(row, weight=1)
            for col in range(num_cols):
                self.cell_grid_frame.columnconfigure(col, weight=1)
                
                cell_widget = CellWidget(self.cell_grid_frame, (row, col), 
                                         self.on_cell_selected, 
                                         self.on_signal_selected_for_plot)
                cell_widget.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
                self.cells[row][col] = cell_widget
                
                seg = col + 1
                cell_idx = row + 1
                
                self.signal_to_widget_map[f"CELL_{seg}x{cell_idx}_Voltage"] = cell_widget
                self.signal_to_widget_map[f"CELL_{seg}x{cell_idx}_VoltageDiff"] = cell_widget
                self.signal_to_widget_map[f"CELL_{seg}x{cell_idx}_Temp"] = cell_widget
                self.signal_to_widget_map[f"CELL_{seg}x{cell_idx}_isDischarging"] = cell_widget
                self.signal_to_widget_map[f"CELL_{seg}x{cell_idx}_isFaultDetected"] = cell_widget
        
        self.signal_to_widget_map["BMS_Pack_Voltage"] = self.system_info_frame
        self.signal_to_widget_map["BMS_Pack_Current"] = self.system_info_frame

    def _initialize_plot(self):
        self.fig = Figure(figsize=(5, 2.5), dpi=100)
        self.fig.set_tight_layout(True)
        
        self.ax = self.fig.add_subplot(111)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.update_plot() # Initial empty plot

    def _initialize_can_and_logging(self, usb_can_path: str, bitrate: int):
        try:
            log_filename = f"can_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.asc" 
            log_file_path = Path("logs") / log_filename
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_file = open(log_file_path, "a", encoding='utf-8', newline='')
            self.asc_writer = can.ASCWriter(self.log_file)

            self.bus = can.Bus(interface="slcan", channel=usb_can_path, bitrate=bitrate)
            
            listeners = [
                CANListener(self.can_message_queue),
                self.asc_writer,
                # can.Printer(), # Can be noisy, uncomment for debugging
            ]
            self.notifier = can.Notifier(self.bus, listeners)
            self.log_frame.log_message("Successfully connected to CAN bus.")
        except Exception as e:
            error_msg = f"Error initializing CAN: {e}"
            self.log_frame.log_message(error_msg)
            self.notifier = None
            self.bus = None

    def process_can_messages(self):
        try:
            while not self.can_message_queue.empty():
                msg: can.Message = self.can_message_queue.get_nowait()
                
                if self.start_timestamp == 0: 
                    self.start_timestamp = msg.timestamp

                relative_time = msg.timestamp - self.start_timestamp
                
                # self.log_frame.log_message(str(msg)) # Can be too verbose, log decoded instead

                try:
                    decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                    log_msg_str = f"ID: {hex(msg.arbitration_id)} {self.db.get_message_by_frame_id(msg.arbitration_id).name} {decoded}"
                    self.log_frame.log_message(log_msg_str)
                    
                    for signal_name, value in decoded.items():
                        if signal_name in self.data_log:
                            self.data_log[signal_name].append((relative_time, value))
                            self.update_widget_for_signal(signal_name)
                            
                except KeyError: # Unknown message ID
                    print("Unknown Message ID", msg)
                    pass
                except Exception as e:
                    print(f"Error decoding or processing message: {e}")

        except queue.Empty:
            pass # Expected

        finally:
            self.after(100, self.process_can_messages)

    def update_widget_for_signal(self, signal_name: str):
        widget = self.signal_to_widget_map.get(signal_name)
        if not widget: return

        if isinstance(widget, CellWidget):
            row, col = widget.cell_id
            seg = col + 1
            cell_idx = row + 1
            
            v_sig  = f"CELL_{seg}x{cell_idx}_Voltage"
            vd_sig = f"CELL_{seg}x{cell_idx}_VoltageDiff"
            t_sig  = f"CELL_{seg}x{cell_idx}_Temp"
            d_sig  = f"CELL_{seg}x{cell_idx}_isDischarging"
            f_sig  = f"CELL_{seg}x{cell_idx}_isFaultDetected"
            
            v  = self.data_log.get(v_sig,  [])[-1][1] if self.data_log.get(v_sig)  else None
            vd = self.data_log.get(vd_sig, [])[-1][1] if self.data_log.get(vd_sig) else None
            t  = self.data_log.get(t_sig,  [])[-1][1] if self.data_log.get(t_sig)  else None
            d  = self.data_log.get(d_sig,  [])[-1][1] if self.data_log.get(d_sig)  else None
            f  = self.data_log.get(f_sig,  [])[-1][1] if self.data_log.get(f_sig)  else None
            
            widget.update_data(voltage=v, voltageDiff=vd, temp=t, is_faulted=f, is_discharging=d)

        elif isinstance(widget, SegmentWidget):
            seg_id = widget.seg_id
            
            v_sig = f"SEG_{seg_id}_IC_Voltage"
            t_sig = f"SEG_{seg_id}_IC_Temp"
            f_sig = f"SEG_{seg_id}_isFaultDetected"
            cf_sig = f"SEG_{seg_id}_isCommsError"

            v = self.data_log.get(v_sig, [])[-1][1] if self.data_log.get(v_sig) else None
            t = self.data_log.get(t_sig, [])[-1][1] if self.data_log.get(t_sig) else None
            f = self.data_log.get(f_sig, [])[-1][1] if self.data_log.get(f_sig) else None
            cf = self.data_log.get(cf_sig, [])[-1][1] if self.data_log.get(cf_sig) else None

            widget.update_data(voltage=v, temp=t, is_faulted=f, is_comms_fault=cf)

        elif isinstance(widget, SystemInfoFrame):
            v = self.data_log.get("BMS_Pack_Voltage", [])[-1][1] if self.data_log.get("BMS_Pack_Voltage") else None
            c = self.data_log.get("BMS_Pack_Current", [])[-1][1] if self.data_log.get("BMS_Pack_Current") else None
            widget.update_values(v, c)
        
        # If the updated signal is the one being plotted, refresh the plot
        if signal_name == self.plotted_signal_name:
            self.update_plot()

    def on_segment_selected(self, seg_id: int):
        """Callback to highlight a segment when clicked."""
        # seg_id is 1-indexed, list is 0-indexed
        col = seg_id - 1

        # Deselect old segment
        if self.selected_segment_id:
            old_col = self.selected_segment_id - 1
            if self.segments[old_col]:
                self.segments[old_col].config(relief="solid", borderwidth=1)
        
        # Select new segment
        self.selected_segment_id = seg_id
        if self.segments[col]:
            self.segments[col].config(relief="solid", borderwidth=3)

    def on_cell_selected(self, cell_id: tuple):
        """Callback to highlight a cell when clicked."""
        # Deselect old cell
        if self.selected_cell_id:
            old_row, old_col = self.selected_cell_id
            if self.cells[old_row][old_col]:
                self.cells[old_row][old_col].config(relief="solid", borderwidth=1)
        
        # Select new cell
        self.selected_cell_id = cell_id
        new_row, new_col = cell_id
        if self.cells[new_row][new_col]:
            self.cells[new_row][new_col].config(relief="solid", borderwidth=3)
        
    def on_signal_selected_for_plot(self, signal_name: str):
        """Callback for when a signal is chosen for plotting."""
        self.plotted_signal_name = signal_name
        self.update_plot()

    def update_plot(self):
        """Clears and redraws the plot for the currently selected signal."""
        self.ax.cla() # Clear the single axis
        
        if self.plotted_signal_name:
            signal_data = self.data_log.get(self.plotted_signal_name, [])
            signal_unit = self.data_units.get(self.plotted_signal_name, "")

            self.ax.set_title(f"{self.plotted_signal_name}")
            if (signal_unit):
                self.ax.set_ylabel(f"{signal_unit}")
            else:
                self.ax.set_ylabel(f"Value")

            if signal_data:
                # Limit plot to last 500 points for performance
                if len(signal_data) > 500:
                    signal_data = signal_data[-500:]
                times, values = zip(*signal_data)
                self.ax.plot(times, values, '.-')
        else:
            self.ax.set_title("Click a value to plot")

        self.ax.set_xlabel("Time (s)")
        self.ax.grid(True, linestyle='--', alpha=0.6)
        self.fig.tight_layout() # Adjust plot to prevent labels overlapping
        self.canvas.draw()
        
    def on_closing(self):
        print("Closing application...")
        if self.notifier:
            self.notifier.stop()
            print("Notifier stopped.")
        if self.bus:
            self.bus.shutdown()
            print("CAN bus shut down.")
        if self.log_file:
            self.log_file.close()
            print("Log file closed.")

        self.destroy()


def main():
    # --- Configuration ---
    # IMPORTANT: Update these paths for your system
    # For Linux: /dev/ttyACMX or /dev/serial/by-id/...
    # For Windows: COMX
    usb_can_path = "/dev/serial/by-id/usb-WeAct_Studio_USB2CANV1_ComPort_AAA120643984-if00"
    dbc_filepath = "./databases/bms_can_database.dbc"
    bitrate = 250000

    # --- Verify paths ---
    if not Path(dbc_filepath).exists():
        print(f"Error: DBC file not found at '{dbc_filepath}'")
        print("Please ensure the DBC file is in the same directory or provide the correct path.")
        return
        
    # On Linux, we don't check the CAN path as it might not exist until plugged in.
    # On Windows, you might want to add a check for the COM port.

    app = Application(usb_can_path=usb_can_path, bitrate=bitrate, dbc_path=dbc_filepath)
    app.mainloop()

if __name__ == "__main__":
    main()
