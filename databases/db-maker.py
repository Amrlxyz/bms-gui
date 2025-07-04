
import cantools
from cantools.database.can import Message, Signal, Database, Node
from cantools.database.conversion import LinearConversion, LinearIntegerConversion, IdentityConversion
from pathlib import Path



def add_bms_cell_messages(db: Database, base_id):
    """Generates a list of similar messages with unique IDs and uniquely named signals."""
    
    num_cells = 16
    num_segments = 7

    # int16 range = -32,768 to 32,767
    voltage_conversion = LinearConversion(0.001, 0, False)
    voltageDiff_conversion = LinearConversion(1, 0, False)
    temp_conversion = LinearConversion(0.01, 0, False)
    flag_conversion = IdentityConversion(False) # This is the default for signal 

    for seg in range(num_segments): 
        seg += 1 # Change to 1 indexing for names

        signals = [
            Signal(
                name        = f"SEG_{seg}_IC_Voltage", 
                conversion  = voltage_conversion,
                start       = 0, 
                length      = 32, 
                byte_order  = 'little_endian', 
                is_signed   = True,
                unit        = 'V'
            ),
            Signal(
                name        = f"SEG_{seg}_IC_Temp", 
                conversion  = temp_conversion,
                start       = 32, 
                length      = 16, 
                byte_order  = 'little_endian', 
                is_signed   = True,
                unit        = 'degC'
            ),
            Signal(
                name        = f"SEG_{seg}_isCommsError",
                start       = 48, 
                length      = 1, 
            ),
            Signal(
                name        = f"SEG_{seg}_isFaultDetected",
                start       = 49,
                length      = 1, 
            ),
        ]

        message = Message(
            name                = f"SEG_{seg}_MSG", 
            frame_id            = base_id + (7*num_cells) + (seg-1),
            signals             = signals,
            length              = 8, 
            is_extended_frame   = True,
            senders             = ["BMS"]
        )

        db.messages.append(message)


        for cell in range(num_cells):
           
            cell += 1 # Change to 1 indexing for names
            
            signals = [
                Signal(
                    name        = f"CELL_{seg}x{cell}_Voltage", 
                    conversion  = voltage_conversion,
                    start       = 0, 
                    length      = 16, 
                    byte_order  = 'little_endian', 
                    is_signed   = True,
                    unit        = 'V'
                ),
                Signal(
                    name        = f"CELL_{seg}x{cell}_VoltageDiff", 
                    conversion  = voltageDiff_conversion,
                    start       = 16, 
                    length      = 16, 
                    byte_order  = 'little_endian', 
                    is_signed   = True,
                    unit        = 'mV'
                ),
                Signal(
                    name        = f"CELL_{seg}x{cell}_Temp", 
                    conversion  = temp_conversion,
                    start       = 32, 
                    length      = 16, 
                    byte_order  = 'little_endian', 
                    is_signed   = True,
                    unit        = 'degC'
                ),
                Signal(
                    name        = f"CELL_{seg}x{cell}_isDischarging",
                    start       = 48, 
                    length      = 1, 
                ),
                Signal(
                    name        = f"CELL_{seg}x{cell}_isFaultDetected",
                    start       = 49,
                    length      = 1, 
                ),
            ]

            message = Message(
                name                = f"CELL_{seg}x{cell}_MSG", 
                frame_id            = base_id + ((seg-1)*num_cells) + (cell-1),
                signals             = signals,
                length              = 8, 
                is_extended_frame   = True,
                senders             = ["BMS"]
            )

            db.messages.append(message)
            
    pack_voltage_conversion = LinearConversion(0.000_001, 0, False)
    current_conversion = LinearConversion(0.001, 0, False)

    signals = [
        Signal(
            name        = f"BMS_Pack_Voltage", 
            conversion  = pack_voltage_conversion,
            start       = 0, 
            length      = 32, 
            byte_order  = 'little_endian', 
            is_signed   = True,
            unit        = 'V'
        ),
        Signal(
            name        = f"BMS_Pack_Current", 
            conversion  = current_conversion,
            start       = 32, 
            length      = 32, 
            byte_order  = 'little_endian', 
            is_signed   = True,
            unit        = 'A'
        ),
    ]

    message = Message(
        name                = f"PACK_MSG", 
        frame_id            = base_id + (num_segments * num_cells) + num_segments,
        signals             = signals,
        length              = 8, 
        is_extended_frame   = True,
        senders             = ["BMS"]
    )

    db.messages.append(message)

    signals = [
        Signal(
            name        = f"BMS_MSTR_isCommsError",
            start       = 0, 
            length      = 1, 
        ),
        Signal(
            name        = f"BMS_MSTR_isFaultDetected",
            start       = 1,
            length      = 1, 
        ),
    ]

    message = Message(
        name                = f"PACK_STATUS_MSG", 
        frame_id            = base_id + (num_segments * num_cells) + num_segments + 1,
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
dbc = Database(nodes=[Node("BMS")])

add_inverter_dbc(dbc, "./hv500_can2_map_v24_EID_custom.dbc")

# print(dbc.get_message_by_frame_id(0xc14, True))


# 0x00XX14 (XX -> 0x00 to 0x24) for the inverter
cell_base_id = 0xB000


add_bms_cell_messages(db=dbc, base_id=cell_base_id)
save_dbc(dbc, 'bms_can_database.dbc')
