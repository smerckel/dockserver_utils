[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# dockserver-utils

The python module dockserver-utils is a collection of utilities that
provides some work-arounds issues with old style dockserver software
from Teledyne WebbResearch.


## serialTCPFwd

This is a python script that allows gliders that connect via serial
devices to the dockserver (either via FreeWave or a direct cable in
case of simulators) to appear as a glider connecting to a network
socket. This circumvents issues with the original java implementation
of the dockserver software that did not handle serial connections
properly.

The serialTCPFwd script looks at a list of default serial
devices, and when they appear because the user connects a serial
device, the connection gets forwarded to the default TCP port at which
the dockserver listens for incoming connections. If, during start-up
of the serialTCPFwd script, serial devices that it should handle are
already present, they are forwarded automatically.

SerialTCPFwd will die if it loses the connection to the
dockserver. It can handle the coming and going of serial devices,
however.

### Usage

```
usage: serialTCPFwd [-h] [-d DEVICES] [-s SERVER] [-p PORT]
                    [-f CONFIGURATION_FILE] [-o SERIAL_OPTIONS]

A serial to tcp data forwarder to use with Teledyne's dockserver software

options:
  -h, --help            show this help message and exit
  -d DEVICES, --devices DEVICES
                        List (comma-separated, no spaces) of serial devices to
                        forward. Example --devices=/dev/ttyUSB0,/dev/ttyUSB1
                        (default:
                        /dev/ttyS0,/dev/ttyUSB0,/dev/ttyUSB1,/dev/ttyUSB2)
  -s SERVER, --server SERVER
                        Host name of dockserver (default: localhost)
  -p PORT, --port PORT  Dockserver TCP port for incoming network connections
                        (default: 8181)
  -f CONFIGURATION_FILE, --configuration_file CONFIGURATION_FILE
                        Reads configuration file. (default: None)
  -o SERIAL_OPTIONS, --serial-options SERIAL_OPTIONS
                        Options to specific serial connections (default:
                        /dev/ttyS0=direct)
```

The option `-d` specifies the serial devices that should be taken care of. They don't need to be present at the time of starting the script. 

Forward connections are redirected to localhost by default, but can be sent to any host using the `-s` option.

The default port that the localhost or remote server is expected to listen to for incoming iridium connections is 8181. This can be overriden by the `-p` option.

Some devices that are connected, such as the shoebox simulator,  doesn't have a carrier detect signal. That means that even though the device is connected, the data are
not forwarded to the local or remote server. To ignore the monitoring of a carrier detect signal, a serial device port can be configured as a direct connection. For example, by 
specifying `-o /dev/ttyS0=direct`.

All settings can also be set in a toml configuration file, which lives by default in `$HOME/.config/dockserver_utils/serialTCPFwd-config.toml`.

An example is given below:

```
# Local configuration for serialTCPFwd.
# Modify as per your needs.

[TCP]
server = "localhost"
port = 8181

[Serial]
devices = [ "/dev/ttyS0", "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2",]

[Serial.options]
"/dev/ttyS0" = "direct"
```

## fileDecompressorHelper

The G3 gliders with the new CPU architecture have the capability to compress data files before transmitting them over iridium. The older dockserver software (7.13) cannot handle compressed files.
The script fileDecompressorHelper can be used to decompress and rename downloaded compressed glider data files on the fly. The script works by monitoring all `from-glider` directories in the gliders directory 
tree, and scans for any files to be written with an extension that signifies compression, i.e. any pattern matching `/?c?/`. Every compressed file will be decompressed and except for compressed cache files, the files
are renamed to their long name.

In all probability, the script will be run by a user that has write permission in the `from-glider` directories. For the sake of convenience, a systemd service script is provided in the `data` directory of this package. 
When using systemd service files, it is easiest to install the package system-wide (as root).

The default directory with all glider names to monitor is `/var/local/dockserver/gliders`. This setting can be overriden with the `-d` option.


## Installation

Installation of the software, is done by calling pip from the top directory:

`pip install .`

Note that, when the fileDecompressorHelper script is to be used from a systemd service, it might be more convenient to install the package system-wide:

`sudo pip install .`



---
