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

CARRIER_DETECT_UNDEFINED = 0
CARRIER_DETECT_YES = 1
CARRIER_DETECT_NO = 2        
        
    
class Serial2TCP(object):
    """ Class for bidirection relaying of binary data between a serial port and a TCP port

    Parameters
    ----------
    device : str
        path of serial device
    serial_option : str
        option applied to serial device
    host : string
        hostname of TCP server
    port : int
        TCP port number of server
    """
    def __init__(self,
                 device: str,
                 serial_option:str,
                 host: str,
                 port: int):
        self.device: str = device
        self.serial_option: str = serial_option
        self.host: str = host
        self.port: int = port
        
        self.ser_reader: asyncio.StreamReader | None = None
        self.ser_writer: asyncio.StreamWriter | None = None
        self.tcp_reader: asyncio.StreamReader | None = None
        self.tcp_writer: asyncio.StreamWriter | None = None

        if serial_option == 'direct':
            self.carrier_detect_status: int = CARRIER_DETECT_YES
        else:
            self.carrier_detect_status: int = CARRIER_DETECT_UNDEFINED
        
    async def initialise_serial_connection(self):
        """ Establishes connection to serial device and TCP server.

        Asyncio coroutine.

        """
        ser_reader, ser_writer = \
            await serial_asyncio.open_serial_connection(url=self.device,
                                                        baudrate=115200,
                                                        bytesize=8,
                                                        parity='N',
                                                        stopbits=1,
                                                        timeout=0,
                                                        reset_input_buffer=True)
        self.ser_reader = ser_reader
        self.ser_writer = ser_writer

    async def initialise_tcp_connection(self) -> int:
        """ Establishes connection to TCP server.

        Asyncio coroutine.

        """
        try:
            tcp_reader, tcp_writer = \
                await asyncio.open_connection(self.host, self.port)
        except (Exception, OSError) as e:
            logger.debug(f"Could not connect to {self.host}:{self.port}")
            return COMMS_ERROR_TCP_INITIALISATION
        else:
            self.tcp_reader = tcp_reader
            self.tcp_writer = tcp_writer
            logger.info(f"TCP connection to {self.host}:{self.port} established for {self.device}.")
            return COMMS_NOERROR
        
    async def close_tcp_connection(self):
        """ Closes connection to TCP server.

        Asyncio coroutine.

        """
        self.tcp_writer.close()
        await self.tcp_writer.wait_closed()
        logger.debug(f"Closed TCP connection ({self.device}).")
        # Do NOT forget!
        self.tcp_reader = None
        self.tcp_writer = None

    async def check_if_server_is_up(self) -> int:
        """ Checks briefly if server is contactable.

        Returns
        -------
        int
            Errorno of connection attempt {COMMS_NOERROR, COMMS_ERROR_TCP_INITIALISATION}
        """
        result = await self.initialise_tcp_connection()
        if result:
            await asyncio.sleep(0.5)
            await self.close_tcp_connection()
        return result
    
    @property
    def has_tcp_backend(self):
        return not (self.tcp_writer is None)

    async def ser_data_filter(self, data: bytes|None=None) -> int:
        # Here we can decide when to open or close a tcp connection.
        # For now just open one if not already done.
        # If argument is None, then this method is called before any data has arrived yet.
        result = COMMS_NOERROR
        return result
        # depending on the data we get, we may also call await self.close_tcp_connection()
        
    async def tcp_data_filter(self, data: bytes) -> int:
        # Here we can decide what we do depending on info from the glider.
        return COMMS_NOERROR

        
            
    async def ser_read_to_tcp_write(self) -> int:
        """ Mono-directional communication : reading from serial; writing to TCP

        Asyncio coroutine.
        
        """
        errorno = COMMS_NOERROR
        data = None
        try:
            while True:
                try:
                    data = await self.ser_reader.read(READBUFFER)
                except serial_asyncio.serial.SerialException:
                    errorno = COMMS_ERROR_SERIAL
                    break
                if not data:
                    break
                errorno = await self.ser_data_filter()
                if errorno != COMMS_NOERROR:
                    break
                # Send the message only if there is a tcp backend
                if self.has_tcp_backend:
                    self.tcp_writer.write(data)
                    try:
                        await self.tcp_writer.drain()
                    except ConnectionResetError:
                        errorno = COMMS_ERROR_TCP
                        break
        finally:
            if self.has_tcp_backend:
                try:
                    self.tcp_writer.close()
                    await self.tcp_writer.wait_closed()
                except:
                    pass #ignore any errors at this stage.
        logger.debug(f"Exiting with {errorno} (device={self.device}).")
        return errorno

    async def monitor_carrier_detect(self) -> int:
        errorno = COMMS_NOERROR
        try:
            while True:
                try:
                    carrier_detect = self.ser_writer._transport.serial.cd
                except (OSError, AttributeError):
                    errrorno = COMMS_ERROR_SERIAL
                    break
                if carrier_detect:
                    _status = CARRIER_DETECT_YES
                else:
                    _status = CARRIER_DETECT_NO
                if _status != self.carrier_detect_status:
                    self.carrier_detect_status = _status
                    logger.debug(f"Carrier detect: {_status} for {self.device}")
                    if _status == CARRIER_DETECT_YES and not self.has_tcp_backend:
                        errorno = await self.initialise_tcp_connection()                            
                        if errorno: # Connection error.
                            break
                    elif _status == CARRIER_DETECT_NO and self.has_tcp_backend:
                        await self.close_tcp_connection()
                await asyncio.sleep(0.1)
        finally:
            logger.debug(f"monitor_carrier_detect(): cleaning up writers...")
            try:
                self.ser_writer.close()
                await self.ser_writer.wait_closed()
            except:
                pass # ignore any errors at this stage.
        logger.debug(f"Exiting with {errorno} (device={self.device}).")
        return errorno
    
    async def tcp_read_to_ser_write(self) -> int:
        """ Mono-directional communication : reading from TCP; writing to serial

        Asyncio coroutine.
        
        """
        errorno = COMMS_NOERROR
        data = None
        try:
            while True:
                if self.has_tcp_backend:
                    try:
                        data = await self.tcp_reader.read(READBUFFER)
                    except Exception as e:
                        logger.debug(f"IDENTIFY ERROR: {type(e)}")
                        errorno=COMMS_ERROR_TCP
                        break
                    if data:
                        self.ser_writer.write(data)
                        try:
                            await self.ser_writer.drain()
                        except Exception as e:
                            logger.debug(f"Identify Error: {e}")
                            errorno = COMMS_ERROR_SERIAL
                            break
                        errorno = await self.tcp_data_filter(data)
                        if errorno:
                            break
                    else:
                        # We don't have any data. We don't need to do
                        # anything but to avoid taking this while loop
                        # 100% processor time. Just sleep for a second.
                        await asyncio.sleep(1) #
                    
                elif not self.has_tcp_backend and self.carrier_detect_status==CARRIER_DETECT_YES:
                    # we have a carrier but no server access.
                        result = COMMS_ERROR_TCP
                        break
                else:
                    # no carrier/TCP conn. let's hope for better times.
                    await asyncio.sleep(1)
                
        finally:
            # this block is executed when the while loop breaks, or if the task is cancelled
            logger.debug(f"tcp_read_to_ser_write(): cleaning up writers...")
            self.ser_writer.close()
            await self.ser_writer.wait_closed()
        logger.debug(f"Exiting with {errorno} (device={self.device}).")
        return errorno

    
        
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

        errorno = await self.check_if_server_is_up()
        if errorno: # we could not connect. Give up.
            logger.debug("Server can NOT be contacted.")
            return errorno
        else:
            logger.debug("Server can be contacted.")
            
        try:
            await self.initialise_serial_connection()
        except serial_asyncio.serial.serialutil.SerialException as e:
            logger.error(f"Error occured: {e.args[-1]}")
            return COMMS_ERROR_SERIAL_INITIALISATION
        logger.info(f"Serial device {self.device} connected.")

        tasks: dict[str, asyncio.Task] = {}
        if not self.serial_option == 'direct':
            tasks["CD_monitor"] = asyncio.create_task(self.monitor_carrier_detect(), name="CD_monitor")
        tasks["ser_to_tcp"] = asyncio.create_task(self.ser_read_to_tcp_write(), name="ser_to_tcp")
        tasks["tcp_to_ser"] = asyncio.create_task(self.tcp_read_to_ser_write(), name="tcp_to_ser")
        
        
        # Wait for one of the tasks to complete (return by catching execption).
        done, pending = await asyncio.wait(tasks.values(),
                                           return_when=asyncio.FIRST_COMPLETED)
        logger.debug("One task completed. Closing down....")

        errorno = COMMS_NOERROR
        for _t in done:
            logger.debug(f"Done task {_t.get_name()} returned {_t.result()} (device: {self.device}).")            
            errorno |= _t.result()
        for _t in pending:
            logger.debug(f"Pending task: {_t.get_name()} (device: {self.device}).")

            
        # pending tasks will be taken down automatically because of errors that will occur in them too.
        await asyncio.wait(pending, timeout=1)
        still_pending = []
        for _t in pending:
            if _t.done():
                continue
            logger.debug(f"Task {_t.get_name()} got not canceled. Try again.")
            _t.cancel()
            still_pending.append(_t)
        if still_pending:
            await asyncio.wait(still_pending, timeout=15)
        for _t in still_pending:
            if not _t.done():
                logger.debug(f"Task {_t.get_name()} still not canceled.")
            
        logger.info(f"Closed connection {self.device} <-> {self.host}:{self.port}.")
        logger.debug(f"Connection for {self.device} returns {errorno}.")
        return errorno

    
class SerialDeviceForwarder(filewatcher.AsynchronousDirectoryMonitorBase):
    """ Monitor to forward Serial to TCP connections

    Parameters
    ----------
    top_directory : str
        path to the directory in which all files and files in subdirectories are monitored.

    devices : list[str]
        list of device names that are to be redirectored.
    serial_options : dict (default={})
        dictionary of options applied to devices
    port : int
        tcp port number to redirect any serial connections to.
    """

    def __init__(self,
                 top_directory: str,
                 devices: list[str],
                 serial_options: dict[str,str]={}, 
                 host: str = "localhost",
                 port: int = 8181):
        super().__init__(top_directory)
        self.devices: list[str] = devices
        self.serial_options: dict[str,str] = serial_options
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

        flags : int
            bit banged integer with aionotify.Flags

        Returns
        -------
        0

        """
        logger.debug(f"device:{device} flags:{flags}")
        if flags == aionotify.Flags.CREATE and device not in self.active_connections:
            await asyncio.sleep(0.5) # give udev time to setup the device.
            self.tasks.append(asyncio.create_task(self.handle_connection(device)))
        return 0
    

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
        try:
            serial_option = self.serial_options[device]
        except KeyError:
            serial_option = ""
        serial2tcp = Serial2TCP(device, serial_option, self.host, self.port)
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
        logger.debug(f"Added watcher for {self.top_directory}.")
        await self.watcher.setup()

        
    async def watch_directory(self) -> int:
        await self.setup_watcher()
        logger.debug("watch_directory(): Starting loop...")
        while True:
            event = await self.watcher.get_event()
            logger.debug(event)
            wd, _ = self.watcher.requests[event.alias]
            path = os.path.join(wd, event.name)
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
        self.tasks.append(asyncio.create_task(self.run(),name="watch_directory"))
        tasks = self.tasks
        while tasks:
            done, pending = await asyncio.wait(tasks,
                                               return_when=asyncio.FIRST_COMPLETED)
            for _t in done:
                self.tasks.remove(_t)
            tasks = self.tasks

            # if the done task is "main" then just end the
            # program. Server quitted. This will also happen if the
            # task is not main, and the comms error is
            # COMMS_ERROR_TCP. In all other cases discard the done
            # task and continue awaiting the pending ones. Last one
            # standing is always main.

            mesg = ''
            for _t in done:
                errorno = _t.result()
                if errorno:
                    logger.debug(f"Error occured in task {_t.get_name()} with result: {_t.result()}.")
                if errorno==COMMS_ERROR_TCP_INITIALISATION:
                        mesg = "Could not initialise connection to server."
                elif errorno==COMMS_ERROR_TCP:
                    mesg = "Exiting due to lost connection to server."
                elif _t.get_name() == "watch_directory":
                    if errorno:
                        mesg = f"Main task (watch_directory) ended with error {errorno}."
                    else:
                        mesg = f"Main task (watch_directory) ended normally."
            if mesg:
                break
            
        logger.error(mesg)
        with open("/dev/stderr", "w") as fp:
            fp.write(f"Fatal error: {mesg}\n")
        sys.exit(errorno)
                
logger = logging.getLogger(__name__)




    
