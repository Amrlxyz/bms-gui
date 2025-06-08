
import cantools
from cantools.database.can import Message, Signal, Database, Node
from pathlib import Path



def add_bms_cell_messages(db: Database, base_id):
    """Generates a list of similar messages with unique IDs and uniquely named signals."""
    
    num_cells = 16
    num_segments = 7





    for cell in range(num_cells): 
        for seg in range(num_segments):

            
            
            signals = [
                Signal(
                    name        = f"CELL_{seg}x{cell}_Voltage", 
                    start       = 0, 
                    length      = 16, 
                    byte_order  = 'little_endian', 
                    is_signed   = True,
                    unit        = 'V'
                ),
                Signal(
                    name        = f"CELL_{seg}x{cell}_Temps", 
                    start       = 16, 
                    length      = 16, 
                    byte_order  = 'little_endian', 
                    is_signed   = True,
                    unit        = 'V'
                ),
                Signal(
                    name        = f"CELL_{seg}x{cell}_isDischarging", 
                    start       = 32, 
                    length      = 1, 
                    byte_order  = 'little_endian', 
                    is_signed   = True,
                    unit        = 'V'
                ),
                Signal(

                )
            ]

            message = Message(
                name                = f"CELL_{seg}x{cell}_MSG", 
                frame_id            = base_id + (seg*num_cells) + cell,
                signals             = signals,
                length              = 8, 
                is_extended_frame   = True,
                senders             = ["BMS"]
            )

            db.messages.append(message)
            
    db.refresh()


def save_dbc(db, filename='output.dbc'):
    """Save a cantools database to a DBC file."""
    cantools.database.dump_file(db, filename=filename, database_format="dbc")


def add_inverter_dbc(db: Database, filename):
    try:
        db.add_dbc_file(filename)
    except Exception as e:
        print("Error importing inverter DBC: ", e)




# Create an empty CAN database
dbc = Database(nodes=[Node("shit"), Node("BMS")])

add_inverter_dbc(dbc, "./hv500_can2_map_v24_EID_custom.dbc")

print(dbc.get_message_by_frame_id(0xc14, True))


# cell_base_id = 0x077000

# add_bms_cell_messages(db=dbc, base_id=cell_base_id)

# # Step 4: Save to file
# save_dbc(dbc, 'bms_can_database.dbc')
