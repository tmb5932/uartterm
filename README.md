# macOS UART Terminal

This is a terminal-based UART tool for macOS only.

## To Install

Requires Python 3.6 or higher.

To install, clone the repository and navigate to the project directory.

Once cloned, simply run the install.sh script to automatically add a symlink to the executable to `/usr/local/bin/uartterm` for easy access from anywhere in the terminal.

The installer will most likely require your admin password, so be prepared to enter it when prompted.

```bash
./install.sh
```

Once ran, simply open a new terminal window and you should be able to run `uartterm` from anywhere.

## Usage

```
usage: uartterm [-h] [--device DEVICE] [--baud {300,1200,2400,4800,9600,19200,38400,57600,115200}] [--data-bits {5,6,7,8}] [--parity {none,even,odd}]
                [--stop-bits {1,2}] [--list]

macOS terminal-based UART terminal

options:
  -h, --help            show this help message and exit
  --device DEVICE       Serial device path, for example /dev/cu.usbserial-0001
  --baud {300,1200,2400,4800,9600,19200,38400,57600,115200}
                        Baud rate
  --data-bits {5,6,7,8}
                        Data bits
  --parity {none,even,odd}
                        Parity
  --stop-bits {1,2}     Stop bits
  --list                List available /dev/cu.* devices and exit
```


## To use straight as Python

Interactive mode:
```bash
python3 cli.py
```

List serial devices:
```bash
python3 src/uartterm/cli.py --list
```

Fully specified:
```bash
python3 src/uartterm/cli.py   --device /dev/cu.usbserial-0001   --baud 115200   --data-bits 8   --parity none   --stop-bits 1
```
