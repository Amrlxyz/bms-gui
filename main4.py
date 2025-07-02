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
            self.voltageDiff_label.config(text=f"{voltage:+} mV")
            color = interpolate_color(voltage, 0, 500, "#00FF00", "#FF0000") # Red to Green
            self.voltageDiff_label.config(background=color)

        # Update Temperature
        if temp is not None:
            self.temp_label.config(text=f"{temp:.2f} °C")
            color = interpolate_color(temp, 10, 100, "#00FF00", "#FF0000") # Green to Red
            self.temp_label.config(background=color)
        
        # Update Flags
        if is_faulted is not None:
            self.fault_label.config(background="#FF0000" if is_faulted else "gray") # Blue or Gray
        
        if is_discharging is not None:
            self.discharging_label.config(background="#0000FF" if is_discharging else "gray") # Blue or Gray


class SystemInfoFrame(ttk.Frame):
    """A frame to display overall system voltage and current."""
    def __init__(self, parent, plot_callback):
        super().__init__(parent, borderwidth=1, relief="solid")

        self.columnconfigure(0, weight=1)  # Make column expandable
        self.rowconfigure(0, weight=1)     # Make rows expandable
        self.rowconfigure(1, weight=1)

        self.voltage_label = ttk.Label(self, text="Voltage: --- V", font=("Helvetica", 32), cursor="hand2", background="gray", anchor="center")
        self.voltage_label.grid(row=0, column=0, columnspan=1, sticky="nsew")
        
        self.current_label = ttk.Label(self, text="Current: --- A", font=("Helvetica", 32), cursor="hand2", background="gray", anchor="center")
        self.current_label.grid(row=1, column=0, columnspan=1, sticky="nsew")

        # Bind for plotting
        self.voltage_label.bind("<Button-1>", lambda e: plot_callback("BMS_Pack_Voltage"))
        self.current_label.bind("<Button-1>", lambda e: plot_callback("BMS_Pack_Current"))


    def update_values(self, voltage, current):
        if voltage is not None:
            self.voltage_label.config(text=f"Voltage: {voltage:.2f} V")
        if current is not None:
            self.current_label.config(text=f"Current: {current:.2f} A")
            
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
        self.signal_to_widget_map = {}
        self.cells = []
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
        self.on_cell_selected((0,0)) # Highlight the default cell at startup

    def _initialize_ui_layout(self):
        # Main layout frames
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        main_frame.columnconfigure(0, weight=3) # Cell grid and plot
        main_frame.columnconfigure(1, weight=1) # Right-side panel
        main_frame.rowconfigure(0, weight=1)

        # Left side (Cells + Plot)
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.rowconfigure(0, weight=2) # Cell grid
        left_frame.rowconfigure(1, weight=1) # Plot
        left_frame.columnconfigure(0, weight=1)
        
        self.cell_grid_frame = ttk.Frame(left_frame)
        self.cell_grid_frame.grid(row=0, column=0, sticky="nsew")

        self.plot_frame = ttk.Frame(left_frame)
        self.plot_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

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
        # --- Create Cell Widgets ---
        num_rows = 16
        num_cols = 7
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
                can.Printer(),
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
                
                self.log_frame.log_message(str(msg))

                try:
                    decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                    
                    for signal_name, value in decoded.items():
                        if signal_name in self.data_log:
                            self.data_log[signal_name].append((relative_time, value))
                            self.update_widget_for_signal(signal_name)
                            
                except KeyError: # Unknown message ID
                    print("Unknown Message ID", msg)
                    pass
        
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

        elif isinstance(widget, SystemInfoFrame):
            v = self.data_log.get("BMS_Pack_Voltage", [])[-1][1] if self.data_log.get("BMS_Pack_Voltage") else None
            c = self.data_log.get("BMS_Pack_Current", [])[-1][1] if self.data_log.get("BMS_Pack_Current") else None
            widget.update_values(v, c)
        
        # If the updated signal is the one being plotted, refresh the plot
        if signal_name == self.plotted_signal_name:
            self.update_plot()


    def on_cell_selected(self, cell_id: tuple):
        """Callback to highlight a cell when clicked."""
        if self.selected_cell_id and self.selected_cell_id != cell_id:
            old_row, old_col = self.selected_cell_id
            if self.cells[old_row][old_col]:
                self.cells[old_row][old_col].config(relief="solid", borderwidth=1)
        
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
            
            unit = ""
            # try:
            #     # Find unit from DBC for the y-axis label
            #     sig_obj = self.db.get_signal_by_name(self.plotted_signal_name)
            #     if sig_obj.unit:
            #         unit = f"({sig_obj.unit})"
            # except KeyError:
            #     pass # Signal not found, no unit

            self.ax.set_title(f"{self.plotted_signal_name}")
            self.ax.set_ylabel(f"Value {unit}")

            if signal_data:
                times, values = zip(*signal_data)
                self.ax.plot(times, values, '.-')
        else:
            self.ax.set_title("Click a value to plot")

        self.ax.set_xlabel("Time (s)")
        self.ax.grid(True, linestyle='--', alpha=0.6)
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
    usb_can_path = "/dev/serial/by-id/usb-WeAct_Studio_USB2CANV1_ComPort_AAA120643984-if00"
    dbc_filepath = "./databases/bms_can_database.dbc"
    bitrate = 250000

    app = Application(usb_can_path=usb_can_path, bitrate=bitrate, dbc_path=dbc_filepath)
    app.mainloop()

if __name__ == "__main__":
    main()
