import asyncio
import logging
import os
import sys



from dockserver_utils import serial2tcp


log_level = logging.DEBUG
logging.basicConfig(level=logging.WARNING,
                    format='%(levelname)6s - %(name)s:%(funcName)s():%(lineno)d - %(message)s')

serial2tcp.logger.setLevel(log_level)
logger = logging.getLogger(__name__)
logger.setLevel(log_level)

devices = ['/dev/ttyUSB0',
           '/dev/ttyUSB1',
           '/dev/ttyS0']
devices.remove('/dev/ttyS0')
serial_options = {'/dev/ttyUSB0':'direct,simulateCD'}
server = '10.200.66.34'
port = 8181

logger.info("Waiting for connections...")
serial_device_forwarder = serial2tcp.SerialDeviceForwarder(top_directory='/dev/',
                                                           devices = devices,
                                                           serial_options = serial_options,
                                                           host = server,
                                                           port = port)
asyncio.run(serial_device_forwarder.start())
