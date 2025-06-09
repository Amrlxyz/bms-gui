
import cantools
from cantools.database.can import Message, Signal, Database, Node
from cantools.database.conversion import LinearConversion, LinearIntegerConversion, IdentityConversion

from pathlib import Path
from pprint import pprint

db: Database = cantools.database.load_file("databases/hv500_can2_map_v24_EID_custom.dbc")

for message in db.messages:
    for signal in message.signals:
        pprint(signal.conversion)

