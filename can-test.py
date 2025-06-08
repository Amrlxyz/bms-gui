# import can

# with can.Bus(interface="slcan", channel="/dev/serial/by-id/usb-WeAct_Studio_USB2CANV1_ComPort_AAA120643984-if00", bitrate=500000) as bus:
    
#     for msg in bus:
#         print(msg)

# try:
#     bus = can.Bus(interface="slcan", channel="/dev/serial/by-id/usb-WeAct_Studio_USB2CANV1_ComPort_AAA120643984-if00", bitrate=500000)

#     for msg in bus:
#         print(msg)

# except KeyboardInterrupt:
#     bus.shutdown()



import time
import can

def main():

    # with can.Bus(interface="virtual", receive_own_messages=True) as bus:
    with can.Bus(interface="slcan", channel="/dev/serial/by-id/usb-WeAct_Studio_USB2CANV1_ComPort_AAA120643984-if00", bitrate=500000) as bus:

        with open("demofile.txt", "w") as f:

            print_listener = can.Printer()
            print_listener_file = can.Printer(f)

            notifier = can.Notifier(bus, [print_listener, print_listener_file])

            bus.send(can.Message(arbitration_id=1, is_extended_id=True))
            bus.send(can.Message(arbitration_id=2, is_extended_id=True))
            bus.send(can.Message(arbitration_id=1, is_extended_id=False))

            time.sleep(1.0)

            notifier.stop()



if __name__ == "__main__":

    main()



