from abc import ABC, abstractmethod
import asyncio
import argparse
import logging
import os
import sys
import typing

import serial_asyncio
serial_asyncio.serial.serialutil.SerialException

import aionotify

from . import filewatcher

COMMS_NOERROR = 0
COMMS_ERROR_SERIAL = 1
COMMS_ERROR_TCP = 2
COMMS_ERROR_SERIAL_INITIALISATION = 3
COMMS_ERROR_TCP_INITIALISATION = 4


# Buffer size of StreamReaders.
READBUFFER = 256

# We need to replace \n by \r if we use nc as dockserver.
# This breaks (sometimes) the binary data transfer. So in production
# we should do NO translation!
TRANSLATE_TCP_TO_SERIAL_INPUT = False

class Serial2TCP(object):
    """ Class for bidirection relaying of binary data between a serial port and a TCP port

    Parameters
    ----------
    device : string
        path of serial device
    host : string
        hostname of TCP server
    port : int
        TCP port number of server
    """
    def __init__(self, device: str, host: str, port: int):
        self.device = device
        self.host = host
        self.port = port
        
    async def read_from_serial(self,
                               ser_reader: asyncio.StreamReader,
                               tcp_writer: asyncio.StreamWriter) -> None:
        """ Mono-directional communication : reading from serial; writing to TCP

        Asyncio coroutine.
        
        Parameters
        ----------
        ser_reader : asyncio.StreamReader
            stream reader for serial device
        tcp_writer : asyncio.StreamWriter
            stream writer for TCP connection

        """
        while True:
            try:
                data = await ser_reader.read(READBUFFER)
            except serial_asyncio.serial.SerialException:
                tcp_writer.close()
                await tcp_writer.wait_closed()
                logger.debug("Encounter a reading problem in read_from_serial(). Closed down TCP writer...")
                break
            if not data:
                break
            # Send the message
            tcp_writer.write(data)
            await tcp_writer.drain()
        logger.debug("Exiting from read_from_serial().")
        
    async def write_to_serial(self,
                              ser_writer: asyncio.StreamWriter,
                              tcp_reader: asyncio.StreamReader) -> None:
        """ Mono-directional communication : reading from TCP; writing to serial

        Asyncio coroutine.
        
        Parameters
        ----------
        ser_writer : asyncio.StreamWriter
            stream writer for serial device
        tcp_reader : asyncio.StreamReader
            stream reader for TCP connection

        """ 
        while True:
            data = await tcp_reader.read(READBUFFER)
            if not data:
                break
            if TRANSLATE_TCP_TO_SERIAL_INPUT:
                s = "Serial input translation active. Do NOT do this in production!"
                logger.warning(s)
                data = data.replace(b"\n", b"\r")          
            ser_writer.write(data)
            await ser_writer.drain()
        logger.debug("Exiting from write_to_serial().")
            
    
    async def initialise_connection(self) -> tuple[dict[str, asyncio.Task], 
                                                   dict[str,
                                                        dict[str, asyncio.StreamWriter|asyncio.StreamReader]
                                                        ]
                                                   ]:
        """ Establishes connection to serial device and TCP server.

        Asyncio coroutine.

        """
        #await asyncio.sleep(1)
        ser_reader, ser_writer = \
            await serial_asyncio.open_serial_connection(url=self.device,
                                                        baudrate=115200,
                                                        bytesize=8,
                                                        parity='N',
                                                        stopbits=1,
                                                        timeout=0,
                                                        reset_input_buffer=True)
        tcp_reader, tcp_writer = \
            await asyncio.open_connection(self.host, self.port)
        read_task = asyncio.create_task(self.read_from_serial(ser_reader, tcp_writer))
        write_task = asyncio.create_task(self.write_to_serial(ser_writer, tcp_reader))
        tasks = dict(read=read_task, write=write_task)
        transports = dict(read=dict(reader=ser_reader, writer=tcp_writer),
                          write=dict(writer=ser_writer, reader=tcp_reader))
        return tasks, transports
        
        
    async def run(self) -> int:
        """ Entry method

        Asyncio.coroutine.

        Returns
        -------
        int | bool
            Error value (COMMS_NOERROR, COMMS_ERROR_SERIAL, COMMS_ERROR_TCP)
        
        
        This method sets up the connection between serial and tcp for both
        directions by creating a task for each communication direction.
        Both tasks are awaited until one of them fails. This can occur because
        of the TCP server disappeared or the serial device disappeared.
        The reason of failure is set to the return value.
        An attempt is made to cancel the remaining active task and close any writers.
        
        """
        logger.debug(f"Starting connection {self.device} <-> {self.host}:{self.port}.")
        try:
            tasks, transports = await self.initialise_connection()
        except serial_asyncio.serial.serialutil.SerialException as e:
            logger.error(f"Error occured: {e.args[-1]}")
            return COMMS_ERROR_SERIAL_INITIALISATION
        except Exception as e:
            logger.error(f"Error occured: {type(e)}")
            return COMMS_ERROR_TCP_INITIALISATION
        
        logger.info(f"Started connection {self.device} <-> {self.host}:{self.port}.")
        # Wait for one of the tasks to complete (return by catching execption).
        done, pending = await asyncio.wait(tasks.values(),
                                           return_when=asyncio.FIRST_COMPLETED)
        logger.debug("One task completed. Closing down....")
        result = COMMS_NOERROR
        if tasks['write'] in pending: # serial connection gave up
            ser_writer = transports['write']['writer']
            ser_writer.close()
            try:
                await ser_writer.wait_closed()
            except serial_asyncio.serial.SerialException:
                pass
            logger.debug("Serial writer closed.")
            if not tasks['write'].cancelled():
                tasks['write'].cancel()
                await asyncio.sleep(0.3)
            result = COMMS_ERROR_SERIAL
        elif tasks['read'] in pending: # tcp connection gave up
            tcp_writer = transports['read']['writer']
            tcp_writer.close()
            await tcp_writer.wait_closed()
            logger.debug("TCP writer closed.")
            if not tasks['read'].cancelled():
                tasks['read'].cancel()
                await asyncio.sleep(0.3)
            result = COMMS_ERROR_TCP
        status = [i.cancelled() for i in pending]
        logger.debug(f"All pending tasks are cancelled: {all(status)}")
        logger.info(f"Closed connection {self.device} <-> {self.host}:{self.port}.")
        return result

    
class SerialDeviceForwarder(filewatcher.AsynchronousDirectoryMonitorBase):
    """ Monitor to forward Serial to TCP connections

    Parameters
    ----------
    top_directory : str
        path to the directory in which all files and files in subdirectories are monitored.

    devices : list[str]
        list of device names that are to be redirectored.

    port : int
        tcp port number to redirect any serial connections to.
    """

    def __init__(self, top_directory: str, devices: list = [str], host: str = "localhost", port: int = 8181):
        super().__init__(top_directory)
        self.devices: list[str] = devices
        self.host: str = host
        self.port: int = port
        self.watcher: None|aionotify.Watcher=None
        self.active_connections: list[str] = []
        self.tasks: list[asyncio.Task] = []
        
    def is_to_be_processed(self, path: str, flags: int) -> bool:
        """Checker to determine if a path should be processed

        Parameters
        ----------
        path : str
            path name

        flags : int
            integer indication the change CREATE or DELETE

        Returns
        -------
        bool
            True if processing is required.
        """
        logger.debug(f"is_to_be_processed(): path: {path} flags:{flags} test: {flags == aionotify.Flags.CREATE}")
        if flags == aionotify.Flags.CREATE:
            return path in self.devices
        return False

    async def process_file(self, device: str, flags:int) -> int | bool:
        """ Coroutine for taking action for device file

        Parameters
        ----------
        device : str
            string with device filename

        change : int
            change type (added (1) / deleted (3)

        Returns
        -------
        None

        """
        logger.debug(f"device:{device} flags:{flags}")
        if flags == aionotify.Flags.CREATE and device not in self.active_connections:
            await asyncio.sleep(0.5) # give udev time to setup the device.
            result = await self.handle_connection(device)
            return result
        return 0 # all well
    

    async def handle_connection(self, device: str) -> int | bool:
        """ Handles a single serial <-> tcp connection

        Parameters
        ----------
        device: str
            device name (path)

        Returns
        -------
        int | bool:
            Error code. {0 ,COMMS_NOERROR, False}, COMMS_ERROR_SERIAL, or COMMS_ERROR_TCP.
        """
        self.active_connections.append(device)
        # Use a asynchronous serial connection
        serial2tcp = Serial2TCP(device, self.host, self.port)
        result = await serial2tcp.run()
        logger.debug("Serial instance cleaned up.")
        logger.debug(f"Result : {result}.")
        self.active_connections.remove(device)
        return result


    async def setup_watcher(self):
        self.watcher = aionotify.Watcher()
        alias: str = 'dev'
        path: str = self.top_directory
        self.watcher.watch(alias=alias,
                           path=path,
                           flags=aionotify.Flags.CREATE|aionotify.Flags.DELETE)
        self.alias_mapping[alias] = path
        logger.debug(f"Added watcher for {self.top_directory}.")
        await self.watcher.setup()

        
    async def watch_directory(self) -> int:
        await self.setup_watcher()
        logger.debug("watch_directory(): Starting loop...")
        while True:
            event = await self.watcher.get_event()
            logger.debug(event)
            path = os.path.join(self.alias_mapping[event.alias], event.name)
            if self.is_to_be_processed(path, event.flags):
                logger.debug(f"{path} is to be processed. Flags: {event.flags}.")
                received_error = await self.process_file(path, event.flags)
                logger.debug(f"process_file({path}) returned {received_error}.")
                if received_error:
                    s = f"Processing file {path} for change {event.flags} returned an error ({received_error})."
                    logger.info(s)
                    break
            else:
                logger.debug(f"{path}:{event.flags} is not marked to be processed.")    
        logger.info(f"Stopped monitoring filesystem under {self.top_directory}.")
        return received_error

    async def start(self) -> None:
        """ Custom entry point, which checks for already existing serial ports
            and handles these if configured so.
        """
        for device in self.devices:
            if os.path.exists(device):
                _t = asyncio.create_task(self.handle_connection(device))
                self.tasks.append(_t)
        self.tasks.append(asyncio.create_task(self.run(),name="main"))
        tasks = self.tasks
        while tasks:
            done, pending = await asyncio.wait(tasks,
                                               return_when=asyncio.FIRST_COMPLETED)
            tasks = [_t for _t in pending]

            # if the done task is "main" then just end the
            # program. Server quitted. This will also happen if the
            # task is not main, and the comms error is
            # COMMS_ERROR_TCP. In all other cases discard the done
            # task and continue awaiting the pending ones. Last one
            # standing is always main.
            mesg = ''
            for _t in done:
                logger.error(f"Error occured in task {_t.get_name()} with result: {_t.result()}.")
                if _t.get_name() == "main":
                    errorno = _t.result()
                    if errorno==COMMS_ERROR_SERIAL:
                        mesg = "Serial communication error. Unspecified"
                    elif errorno==COMMS_ERROR_SERIAL_INITIALISATION:
                        mesg = "Could not initialise serial device."
                    elif errorno==COMMS_ERROR_TCP_INITIALISATION:
                        mesg = "Could not initialise connection to server."
                elif _t.get_name() != "main" and _t.result() == COMMS_ERROR_TCP:
                    # server must have disappeared when an established
                    # connection already existed.
                    errorno = _t.result()
                    mesg = "Exiting due to lost connection to server."
                if mesg:
                    with open("/dev/stderr", "w") as fp:
                        fp.write(f"Fatal error: {mesg}\n")
                    sys.exit(errorno)
                
logger = logging.getLogger(__name__)




    
