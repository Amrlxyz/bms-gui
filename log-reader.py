import can
import cantools
from cantools.database.can import Message, Signal, Database, Node
from pprint import pp
from pathlib import Path


log_file = "logs/can_log_20250703_135123.asc"
db_filepath = "databases/bms_can_database.dbc"

enable_save_fig = False
enable_live_fig = True      # Make sure only few plots are enabled

# Leave empty if no name filter is needed
only_include_msg_name = "CELL_5x10"

# Unwanted Signals Filter
signal_names_filter = [
    "isFault",
    "isComms",
    "Diff",
    "isDischarging",
    # "Temp",
    # "Voltage"
]


time_range = [900, 1000]
yaxis_range = []

db: Database = cantools.database.load_file(db_filepath)
data_log = {}
for msg in db.messages:
    if only_include_msg_name in msg.name:
        filtered_signals = [signal for signal in msg.signals if not any(filt in signal.name for filt in signal_names_filter)]  # Filters unwanted signals
        data_log[msg.name] = {
            "values": {signal.name: [] for signal in filtered_signals},
            "timestamps": []
        }

data_units = {signal.name: signal.unit for msg in db.messages for signal in msg.signals}

# pp(data_log)

for msg in can.LogReader(log_file):
    # print(msg)
    try:
        decoded = db.decode_message(msg.arbitration_id, msg.data)
        msg_name = db.get_message_by_frame_id(msg.arbitration_id).name
        
        timestamp = msg.timestamp
        
        if msg_name in data_log:
            data_log[msg_name]["timestamps"].append(timestamp)

            for signal_name, value in decoded.items():
                if signal_name in data_log[msg_name]["values"]:
                    data_log[msg_name]["values"][signal_name].append(value)
                
    except KeyError: # Unknown message ID
        print("Unknown Message ID", msg)
        pass
    except Exception as e:
        print(f"Error decoding or processing message: {e}")


# Code used for plotting

# import matplotlib
# matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt

def plot(data_log):
    for msg_name, data in data_log.items():
        timestamps = data["timestamps"]

        if not timestamps:
            continue

        signals = list(data["values"].keys())
        num_signals = len(signals)

        fig, axs = plt.subplots(num_signals, 1, figsize=(12, 3 * num_signals), sharex=True)
        fig.suptitle(f'CAN Analysis: {msg_name}', fontsize=16)

        # If only one subplot, axs is not a list
        if num_signals == 1:
            axs = [axs]

        for i, signal_name in enumerate(signals):
            ax = axs[i]
            values = data["values"][signal_name]
            unit = data_units.get(signal_name, '')
            label = f'{signal_name} [{unit}]' if unit else signal_name

            ax.plot(timestamps, values, 'o-', markersize=2, label=label)
            ax.set_ylabel(label)
            ax.grid(True)
            if yaxis_range:
                ax.set_ylim(yaxis_range)

        axs[-1].set_xlabel("Time")
        plt.xlim(time_range)

        if enable_live_fig:
            plt.tight_layout(rect=[0, 0, 1, 0.96])  # Make room for suptitle
            plt.show()

        if enable_save_fig:
            filename = f'can_subplot_{msg_name.replace(" ", "_")}.png'
            results_path = Path("results") / filename
            results_path.parent.mkdir(parents=True, exist_ok=True)
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            plt.savefig(results_path, dpi=150, bbox_inches='tight')
            print(f'Saved plot: {results_path}')
            plt.close()



plot(data_log)