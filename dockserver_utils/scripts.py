import argparse
import asyncio
import logging
from . import serial2tcp

def serialTCPConnector():
    log_level = logging.DEBUG
    logging.basicConfig(level=logging.WARNING)
    serial2tcp.logger.setLevel(log_level)
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    logger.info("Waiting for connections...")
    serial_device_forwarder = serial2tcp.SerialDeviceForwarder('/dev/', ['/dev/ttyUSB0', '/dev/ttyUSB1'])
    asyncio.run(serial_device_forwarder.run())
