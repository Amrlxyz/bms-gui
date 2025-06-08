from pathlib import Path
import datetime
import time
import can


usb_can_path = "/dev/serial/by-id/usb-WeAct_Studio_USB2CANV1_ComPort_AAA120643984-if00"
bitrate = 500000

import tkinter as tk
from tkinter import ttk

def main():

    log_filename = f"can_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log" 
    
    log_file_dir = Path("logs") / log_filename
    log_file_dir.parent.mkdir(parents=True, exist_ok=True) # Create the log folder if not yet existed

    app = Application()

    with (
        can.Bus(interface="slcan", channel=usb_can_path, bitrate=bitrate) as bus,
        open(log_file_dir, "a", encoding='utf-8', newline='') as log_file
    ):

        print_listener = can.Printer()
        # log_writer_listener = can.CanutilsLogWriter(log_file)
        asc_writer_listener = can.ASCWriter(log_file)
        app_listen = app

        
        notifier = can.Notifier(bus, [print_listener, asc_writer_listener, app_listen])

        app.mainloop()

        notifier.stop()



        



class InputForm(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.entry = ttk.Entry(self)
        self.entry.grid(row=0, column=0, sticky="ew")

        self.entry.bind("<Return>", self.add_to_list)

        self.entry_btn = ttk.Button(self, text="Add", command=self.add_to_list)
        self.entry_btn.grid(row=0, column=1)

        self.entry_btn2 = ttk.Button(self, text="Clear", command=self.clear_list)
        self.entry_btn2.grid(row=0, column=2)

        self.text_list = tk.Listbox(self)
        self.text_list.grid(row=1, column=0, columnspan=3, sticky="nsew")


    def add_to_list(self, _event=None):
        text = self.entry.get()
        if text:
            self.text_list.insert(tk.END, text)
            self.entry.delete(0, tk.END)

    def clear_list(self):
        self.text_list.delete(0, tk.END)


class Application(tk.Tk, can.Listener):
    def __init__(self):
        super().__init__()
        self.title("Simple App")

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=3)
        self.rowconfigure(0, weight=1)

        self.frame = InputForm(self)
        self.frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        frame2 = InputForm(self)
        frame2.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

    def on_message_received(self, msg):
        self.frame.text_list.insert(tk.END, msg)
    
    # def on_error(self, exc):
    #     print("Error: " + str(exc))










    


if __name__ == "__main__":
    main()
