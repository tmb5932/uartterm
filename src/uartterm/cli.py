#!/usr/bin/env python3
"""
macOS Command-Line UART Terminal

Implements the attached SRS at a practical level:
- macOS only
- Select from /dev/cu.* devices
- Supported baud rates: 300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200
- Supported data bits: 5, 6, 7, 8
- Supported parity: none, even, odd
- Supported stop bits: 1, 2
- Flow control disabled
- Raw terminal mode for immediate transmit
- Printable ASCII displayed normally
- CR/LF handled appropriately
- Other bytes displayed as replacement character
- One serial connection per program instance
- If disconnected during operation, notify user and retry every 0.5 seconds until Ctrl+C
- If port cannot be opened at startup, print error and terminate
"""

import argparse
import errno
import fcntl
import glob
import os
import selectors
import signal
import sys
import termios
import time
import tty
from dataclasses import dataclass
from typing import List, Optional

class Color:
    RESET = "\033[0m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"

SUPPORTED_BAUDS = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
SUPPORTED_DATA_BITS = [5, 6, 7, 8]
SUPPORTED_PARITY = ["none", "even", "odd"]
SUPPORTED_STOP_BITS = [1, 2]
REPLACEMENT_CHAR = "�"

BAUD_TO_TERM = {
    300: termios.B300,
    1200: termios.B1200,
    2400: termios.B2400,
    4800: termios.B4800,
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
}


@dataclass
class SerialConfig:
    device: str
    baud: int
    data_bits: int
    parity: str
    stop_bits: int

def sys_print(message: str, color: Optional[str] = None, end: str = "\r\n", flush: bool = True):
    if color is not None:
        message = f"{color}{message}{Color.RESET}"
    print(message, file=sys.stderr, end=end, flush=flush)

class TerminalRawMode:
    def __init__(self, fd: int):
        self.fd = fd
        self._old_attrs = None

    def __enter__(self):
        self._old_attrs = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._old_attrs is not None:
            termios.tcsetattr(self.fd, termios.TCSANOW, self._old_attrs)


class UartTerminal:
    def __init__(self, config: SerialConfig):
        self.config = config
        self.serial_fd: Optional[int] = None
        self.selector = selectors.DefaultSelector()
        self.stop_requested = False
        self.stdin_fd = sys.stdin.fileno()

    def request_stop(self, *_args):
        self.stop_requested = True

    def startup_connect(self):
        try:
            self.serial_fd = self._open_serial(self.config)
        except OSError as e:
            sys_print(f"Error: could not open {self.config.device}: {e.strerror or e}", Color.RED)
            sys.exit(1)

    def run(self):
        signal.signal(signal.SIGINT, self.request_stop)
        self.startup_connect()

        sys_print(
            f"Connected to {self.config.device} "
            f"({self.config.baud}, {self.config.data_bits}{self._parity_short()}{self.config.stop_bits}).",
            Color.GREEN,
        )
        sys_print("Press Ctrl+C to exit.\n", Color.CYAN)

        with TerminalRawMode(self.stdin_fd):
            self._register_active_fds()

            while not self.stop_requested:
                try:
                    events = self.selector.select(timeout=0.1)
                except OSError:
                    events = []

                for key, _mask in events:
                    if self.stop_requested:
                        break

                    if key.data == "stdin":
                        if not self._handle_stdin():
                            self._handle_disconnect("Serial connection interrupted.")
                            break
                    elif key.data == "serial":
                        if not self._handle_serial():
                            self._handle_disconnect("Serial connection interrupted.")
                            break

        self._cleanup()
        sys_print("\nDisconnected. Exiting.", Color.YELLOW)

    def _register_active_fds(self):
        self.selector.close()
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.stdin_fd, selectors.EVENT_READ, "stdin")
        if self.serial_fd is not None:
            self.selector.register(self.serial_fd, selectors.EVENT_READ, "serial")

    def _handle_stdin(self) -> bool:
        try:
            data = os.read(self.stdin_fd, 1024)
        except OSError:
            return True

        if not data:
            return True

        # Ctrl+C in raw mode
        if b"\x03" in data:
            self.stop_requested = True
            return True

        if self.serial_fd is None:
            return False

        try:
            os.write(self.serial_fd, data)
            return True
        except OSError:
            return False

    def _handle_serial(self) -> bool:
        if self.serial_fd is None:
            return False

        try:
            data = os.read(self.serial_fd, 1024)
        except OSError as e:
            if e.errno in (errno.EIO, errno.ENXIO, errno.EBADF, errno.ENODEV):
                return False
            return True

        if not data:
            return False

        rendered = self._render_bytes(data)
        try:
            os.write(sys.stdout.fileno(), rendered.encode("utf-8", errors="replace"))
        except OSError:
            pass
        return True

    def _render_bytes(self, data: bytes) -> str:
        out = []
        for b in data:
            if b == 0x0A:
                out.append("\n")
            elif b == 0x0D:
                out.append("\r")
            elif 0x20 <= b <= 0x7E:
                out.append(chr(b))
            else:
                out.append(REPLACEMENT_CHAR)
        return "".join(out)

    def _check_for_exit_keypress(self):
        try:
            events = self.selector.select(timeout=0.05)
        except OSError:
            return

        for key, _mask in events:
            if key.data == "stdin":
                try:
                    data = os.read(self.stdin_fd, 1024)
                except OSError:
                    data = b""

                if b"\x03" in data:
                    self.stop_requested = True
                    return

    def _handle_disconnect(self, message: str):
        sys_print(f"\n{message}", Color.RED)
        self._close_serial()

        while not self.stop_requested:
            sys_print(f"Attempting reconnection to {self.config.device} in 0.5 seconds...", Color.YELLOW)
            start = time.monotonic()

            while (time.monotonic() - start) < 0.5 and not self.stop_requested:
                self._check_for_exit_keypress()

            try:
                self.serial_fd = self._open_serial(self.config)
                sys_print(f"Reconnected to {self.config.device}.", Color.GREEN)
                self._register_active_fds()
                return
            except OSError:
                continue

    def _close_serial(self):
        if self.serial_fd is not None:
            try:
                self.selector.unregister(self.serial_fd)
            except Exception:
                pass
            try:
                os.close(self.serial_fd)
            except OSError:
                pass
            self.serial_fd = None

    def _cleanup(self):
        self._close_serial()
        try:
            self.selector.close()
        except Exception:
            pass

    def _open_serial(self, config: SerialConfig) -> int:
        fd = os.open(config.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)

        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)

        attrs = termios.tcgetattr(fd)

        # attrs = [iflag, oflag, cflag, lflag, ispeed, ospeed, cc
        attrs[0] = 0
        attrs[1] = 0
        attrs[3] = 0

        cflag = termios.CREAD | termios.CLOCAL
        cflag |= self._data_bits_flag(config.data_bits)

        if config.parity == "even":
            cflag |= termios.PARENB
        elif config.parity == "odd":
            cflag |= termios.PARENB | termios.PARODD

        if config.stop_bits == 2:
            cflag |= termios.CSTOPB

        if hasattr(termios, "CRTSCTS"):
            cflag &= ~termios.CRTSCTS

        attrs[2] = cflag
        attrs[6][termios.VMIN] = 1
        attrs[6][termios.VTIME] = 0

        baud_flag = BAUD_TO_TERM[config.baud]
        attrs[4] = baud_flag
        attrs[5] = baud_flag
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)

        return fd

    def _data_bits_flag(self, bits: int) -> int:
        if bits == 5:
            return termios.CS5
        if bits == 6:
            return termios.CS6
        if bits == 7:
            return termios.CS7
        return termios.CS8

    def _parity_short(self) -> str:
        if self.config.parity == "none":
            return "N"
        if self.config.parity == "even":
            return "E"
        return "O"


def list_devices() -> List[str]:
    return sorted(glob.glob("/dev/cu.*"))


def choose_from_list(prompt: str, options: List[str], cast=str):
    while True:
        sys_print(prompt, Color.CYAN)
        for idx, item in enumerate(options, start=1):
            sys_print(f"  {idx}) {item}", Color.CYAN)
        print("> ", end="", file=sys.stderr, flush=True)

        response = input().strip()
        try:
            index = int(response)
            if 1 <= index <= len(options):
                return cast(options[index - 1])
        except ValueError:
            pass

        sys_print("Invalid selection. Please try again.\n", Color.RED)


def choose_value(prompt: str, options: List, cast):
    options_str = ", ".join(str(x) for x in options)
    while True:
        sys_print(f"{prompt} [{options_str}]", Color.CYAN)
        sys_print(">", Color.CYAN, end="", flush=True)
        response = input().strip()
        try:
            value = cast(response)
        except ValueError:
            value = None
        if value in options:
            return value
        sys_print("Invalid selection. Please try again.", Color.RED)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="macOS terminal-based UART terminal")
    parser.add_argument("--device", help="Serial device path, for example /dev/cu.usbserial-0001")
    parser.add_argument("--baud", type=int, choices=SUPPORTED_BAUDS, help="Baud rate")
    parser.add_argument("--data-bits", type=int, choices=SUPPORTED_DATA_BITS, help="Data bits")
    parser.add_argument("--parity", choices=SUPPORTED_PARITY, help="Parity")
    parser.add_argument("--stop-bits", type=int, choices=SUPPORTED_STOP_BITS, help="Stop bits")
    parser.add_argument("--list", action="store_true", help="List available /dev/cu.* devices and exit")
    return parser.parse_args()


def collect_config(args: argparse.Namespace) -> SerialConfig:
    devices = list_devices()

    if args.list:
        if devices:
            for dev in devices:
                print(dev)
        else:
            sys_print("No compatible serial devices found.", Color.RED)
        sys.exit(0)

    if not devices and not args.device:
        sys_print("No compatible serial devices available.", Color.RED)
        sys.exit(1)

    if args.device:
        device = args.device
    else:
        device = choose_from_list("Select a serial device:", devices)

    baud = args.baud if args.baud is not None else choose_value("Select baud rate", SUPPORTED_BAUDS, int)

    # Default to 8N1
    data_bits = args.data_bits if args.data_bits is not None else 8
    parity = args.parity if args.parity is not None else "none"
    stop_bits = args.stop_bits if args.stop_bits is not None else 1

    return SerialConfig(
        device=device,
        baud=baud,
        data_bits=data_bits,
        parity=parity,
        stop_bits=stop_bits,
    )


def main():
    try:
        if sys.platform != "darwin":
            print("Error: this program supports macOS only.", file=sys.stderr)
            sys.exit(1)

        args = parse_args()
        config = collect_config(args)
        app = UartTerminal(config)
        app.run()
    except KeyboardInterrupt:
        sys_print("\nExiting.", Color.YELLOW)
        sys.exit(0)


if __name__ == "__main__":
    main()
