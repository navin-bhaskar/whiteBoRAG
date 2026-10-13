# /// script
# requires-python = ">=3.9"
# dependencies = ["pyserial"]
# ///
"""Send one line to the ESP32-CAM and print what it says back.

    uv run ESP32-cam/firmware/tools/serial_cmd.py COM5 snap --seconds 15
    uv run ESP32-cam/firmware/tools/serial_cmd.py COM5 --seconds 60   # listen only

DTR and RTS are held low so opening the port neither resets the board nor
puts it in the bootloader (the ESP32-CAM-MB wires them to EN and IO0).
"""

import argparse
import sys
import time

import serial


def main():
    p = argparse.ArgumentParser()
    p.add_argument("port")
    p.add_argument("command", nargs="?", default="", help="line to send; omit to only listen")
    p.add_argument("--seconds", type=float, default=10.0, help="how long to print output")
    args = p.parse_args()

    port = serial.Serial()
    port.port = args.port
    port.baudrate = 115200
    port.timeout = 0.2
    port.dtr = False
    port.rts = False
    port.open()
    try:
        time.sleep(0.3)
        port.reset_input_buffer()
        if args.command:
            port.write((args.command + "\n").encode())
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            line = port.readline()
            if line:
                sys.stdout.write(line.decode("utf-8", "replace"))
                sys.stdout.flush()
    finally:
        port.close()


if __name__ == "__main__":
    main()
