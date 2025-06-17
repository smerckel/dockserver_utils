import abc
import argparse
import asyncio
import logging
import os
import sys
import toml


from . import serial2tcp
from . import fileDecompressor

class Config(abc.ABC):
    def __init__(self):
        super().__init__()
        self.config = {}
        self.set_defaults()
        
    @abc.abstractmethod
    def set_defaults(self):
        pass
    
    def readToml(self, filename: str) -> {}:
        if not os.path.exists(filename):
            return {}
        with open(filename, 'r') as fp:
            config = toml.load(fp)
        for k, v in config.items():
            self.config[k] = v
        return self.config

    def writeToml(self, filename: str, comments: str=''):
        with open(filename, 'w') as fp:
            if comments:
                fp.write(comments)
            toml.dump(self.config, fp)

class serialTCPConnectorConfig(Config):

    def __init__(self):
        super().__init__()
        
    def set_defaults(self):
        default_config = dict(TCP=dict(server="localhost",
                                       port=8181),
                              Serial=dict(devices=['/dev/ttyUSB0',
                                                   '/dev/ttyUSB1',
                                                   '/dev/ttyUSB2']
                                          )
                              )
        for k,v in default_config.items():
            self.config[k] = v
                              
                                                   
def serialTCPConnector():
    log_level = logging.DEBUG
    logging.basicConfig(level=logging.WARNING)
    serial2tcp.logger.setLevel(log_level)
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)

    config = serialTCPConnectorConfig()
    parser = argparse.ArgumentParser(
        description='A serial to tcp data forwarder to use with Teledyne\'s dockserver software',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    s = 'List (comma-separated, no spaces) of serial devices to forward. Example --devices=/dev/ttyUSB0,/dev/ttyUSB1'
    parser.add_argument('-d', '--devices', help=s,
                        type=str, default=",".join(config.config['Serial']['devices']))
    parser.add_argument('-s', '--server', help='Host name of dockserver',
                        type=str, default=config.config['TCP']['server'])
    parser.add_argument('-p', '--port', help='Dockserver TCP port for incoming network connections',
                        type=int, default=config.config['TCP']['port'])
    parser.add_argument('-f', '--configuration_file', help='Reads configuration file.')

    args = parser.parse_args()

    # Read Configuration files, first, globally, then locally
    local_config_path = '.config/dockserver_utils'
    os.makedirs(os.path.join(os.environ['HOME'], local_config_path), exist_ok=True)
                
    config.readToml('/etc/dockserver_utils/serialTCPConnector-config.toml')
    local_config_filename = os.path.join(os.environ['HOME'], local_config_path, 'Connector-config.toml')
    if not config.readToml(local_config_filename):
        comments="""# Local configuration for serialTCPConnector.
# Modify as per your needs.

"""
        config.writeToml(local_config_filename, comments=comments)


    # apply settings in supplied config file, if available.
    if args.configuration_file:
        if not config.readToml(args.configuration_file):
            with open('/dev/stderr', 'w') as fp:
                fp.write(f"Error opening configuration file {args.configuration_file}.")
            sys.exit(1)

    logger.info(f"Configuration:")
    logger.info("-"*20)
    logger.info(f"Serial devices:")
    for i, s in enumerate(args.devices.split(",")):
        logger.info(f"\t{i:2d} {s}")
    logger.info(f"Server {args.server}:{args.port}")

    logger.info("Waiting for connections...")
    serial_device_forwarder = serial2tcp.SerialDeviceForwarder(top_directory='/dev/',
                                                               devices = args.devices.split(","),
                                                               host = args.server,
                                                               port = args.port)
    asyncio.run(serial_device_forwarder.start())


def fileDecompressorHelper():
    log_level = logging.DEBUG
    logging.basicConfig(level=logging.WARNING)
    fileDecompressor.logger.setLevel(log_level)
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)


    
    s = """A helper program for older Teledyne WebbResearch's dockserver programs to
handle compressded glider files automatically."""
    parser = argparse.ArgumentParser(
        description=s,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('-d', '--directory', help='Top directory to monitor',
                        type=str, default="/var/local/dockserver/gliders")
    args = parser.parse_args()

    file_renamer = fileDecompressor.DBDMLGFileRenamer()
    logger.info(f"Started monitoring for any compressed binary glider data files to arrive.")
    logger.info(f"The top directory is set to {args.directory}.")
    fdc = fileDecompressor.AsynchronousFileDecompressorAionotify(top_directory=args.directory,
                                                                 file_renamer = file_renamer)
    asyncio.run(fdc.run())
