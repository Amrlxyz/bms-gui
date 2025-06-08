from pathlib import Path
import datetime
import queue
import can
import tkinter as tk
from tkinter import ttk

class CANListener(can.Listener):
    """
    A can.Listener that puts received messages into a queue.
    This is used to pass messages from the python-can thread to the
    main GUI thread in a thread-safe manner.
    """
    def __init__(self, msg_queue: queue.Queue):
        self.queue = msg_queue


    def on_message_received(self, msg: can.Message):
        """
        Called by the Notifier thread when a message is received.
        The message is put into the queue for the main thread to process.
        """
        self.queue.put(msg)
    
    def on_error(self, exc: Exception):
        """
        Called by the Notifier thread when an error occurs.
        """
        print(f"An error occurred in the CAN listener: {exc}")


class InputFrame(ttk.Frame):
    """A reusable frame containing an entry, buttons, and a listbox."""
    def __init__(self, parent):
        super().__init__(parent, padding=5)

        # Configure grid layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # --- Widgets ---
        self.entry = ttk.Entry(self)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.entry.bind("<Return>", self.add_to_list) # Bind Enter key

        self.add_button = ttk.Button(self, text="Add", command=self.add_to_list)
        self.add_button.grid(row=0, column=1, padx=(0, 5))

        self.clear_button = ttk.Button(self, text="Clear", command=self.clear_list)
        self.clear_button.grid(row=0, column=2)

        # Use a scrollbar for the listbox
        list_frame = ttk.Frame(self)
        list_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(5, 0))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.text_list = tk.Listbox(list_frame)
        self.text_list.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.text_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text_list.config(yscrollcommand=scrollbar.set)

    def add_to_list(self, _event=None):
        """Adds the content of the entry widget to the listbox."""
        text = self.entry.get()
        if text:
            self.text_list.insert(tk.END, text)
            self.entry.delete(0, tk.END)

    def clear_list(self):
        """Clears all items from the listbox."""
        self.text_list.delete(0, tk.END)

    def log_message(self, msg):
        """Inserts a message at the end of the listbox."""
        self.text_list.insert(tk.END, f"{datetime.datetime.now().time()} | {msg}")
        self.text_list.yview_moveto(1.0) # Auto-scroll to the bottom


class Application(tk.Tk):
    def __init__(self, usb_can_path: str, bitrate: int):
        super().__init__()
        self.title("CAN Bus Logger and GUI")
        self.geometry("800x600")

        # --- App State ---
        self.bus = None
        self.notifier = None
        self.asc_writer = None
        self.log_file = None

        self.start_timestamp = 0
        self.prev_timestamp = 0
        self.avg_time = 0
        self.message_count = 0
        
        # Thread-safe queue for messages from the CAN thread
        self.can_message_queue = queue.Queue()

        # --- UI Setup ---
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1) # Give equal weight to both frames
        self.rowconfigure(0, weight=1)

        self.received_messages_frame = InputFrame(self)
        self.received_messages_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        # Modify the widgets to be more descriptive
        self.received_messages_frame.add_button.config(state="disabled", text="CAN Log")
        self.received_messages_frame.entry.config(state="disabled")

        self.other_frame = InputFrame(self)
        self.other_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)


        # --- CAN Bus and Logging Initialization ---
        try:
            # Setup logging
            log_filename = f"can_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.asc" 
            log_file_path = Path("logs") / log_filename
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.log_file = open(log_file_path, "a", encoding='utf-8', newline='')
            self.asc_writer = can.ASCWriter(self.log_file)

            # Connect to the CAN bus
            self.bus = can.Bus(interface="slcan", channel=usb_can_path, bitrate=bitrate)
            
            # Setup the notifier to push messages to our queue and log file
            # The CANListener will push to self.can_message_queue
            gui_listener = CANListener(self.can_message_queue)
            
            listeners = [
                gui_listener,         # Puts messages in the queue for the GUI
                self.asc_writer,      # Writes messages to the .asc log file
                can.Printer(),        # Prints messages to the console
            ]
            self.notifier = can.Notifier(self.bus, listeners)
            print("Successfully connected to CAN bus and started logging.")

        except Exception as e:
            # If connection fails, show an error and disable logging
            error_msg = f"Error initializing CAN bus: {e}"
            print(error_msg)
            self.received_messages_frame.log_message(error_msg)
            self.notifier = None
            self.bus = None

        # --- Protocol Handlers ---
        # Schedule the first check of the message queue
        self.after(100, self.process_can_messages)
        # Set the action for when the window is closed
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def process_can_messages(self):
        """
        Checks the queue for new messages and updates the GUI.
        This method is run in the main GUI thread.
        """
        try:
            while not self.can_message_queue.empty():
                msg : can.Message = self.can_message_queue.get_nowait()

                if self.start_timestamp == 0:
                    self.start_timestamp = msg.timestamp
                    timedelta = 0
                else:
                    timedelta = msg.timestamp - self.prev_timestamp
                self.prev_timestamp = msg.timestamp

                timedelta = int(round(timedelta*1_000_000))
                self.message_count += 1
                self.avg_time = (timedelta + self.avg_time * (self.message_count-1)) / self.message_count

                msg.timestamp = msg.timestamp - self.start_timestamp

                # Update the GUI with the new message
                self.received_messages_frame.log_message(str(msg) + "   TimeDiff:   " + str(timedelta) + "  AVG: " + str(self.avg_time))
                
        except queue.Empty:
            # This is expected when the queue is empty
            pass
        finally:
            # Schedule the next check
            self.after(100, self.process_can_messages)

    def on_closing(self):
        """
        This method is called when the user closes the Tkinter window.
        It handles the graceful shutdown of the CAN notifier and bus.
        """
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
        
        self.destroy() # Close the tkinter window


def main():
    # --- Configuration ---
    usb_can_path = "/dev/serial/by-id/usb-WeAct_Studio_USB2CANV1_ComPort_AAA120643984-if00"
    bitrate = 500000

    app = Application(usb_can_path=usb_can_path, bitrate=bitrate)
    app.mainloop()


if __name__ == "__main__":
    main()
