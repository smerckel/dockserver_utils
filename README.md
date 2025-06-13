[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# dockserver-utils

The python module dockserver-utils is a collection of utilities that
provides some work-arounds issues with old style dockserver software
from Teledyne WebbResearch.


## serialTCPConnection

This is a python script that allows gliders that connect via serial
devices to the dockserver (either via FreeWave or a direct cable in
case of simulators) to appear as a glider connecting to a network
socket. This circumvents issues with the original java implementation
of the dockserver software that did not handle serial connections
properly.

The serialTCPConnection script looks at a list of default serial
devices, and when they appear because the user connects a serial
device, the connection gets forwarded to the default TCP port at which
the dockserver listens for incoming connections. If, during start-up
of the serialTCPConnection, serial devices that it should handle are
already present, they are forwarded automatically.

SerialTCPConnection will die if it loses the connection to the
dockserver. It can handle the coming and going of serial devices,
however.

## Installation

Installation of the software, for now, is done by calling pip from the top directory:

`pip install .`

---
