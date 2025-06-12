from abc import ABC, abstractmethod
import asyncio
import argparse
import logging
import typing

import serial_asyncio
from watchfiles import awatch, Change

from . import filewatcher

COMMS_NOERROR = 0
COMMS_ERROR_SERIAL = 1
COMMS_ERROR_TCP = 2

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
        logger.info(f"Starting connection {self.device} <-> {self.host}:{self.port}.")
        tasks, transports = await self.initialise_connection()
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
        self.host: string = host
        self.port: int = port 
        self.active_connections: list[str] = []
        
    def is_to_be_processed(self, path: str, change: int) -> bool:
        """Checker to determine if a path should be processed

        Parameters
        ----------
        path : str
            path name

        change : int
            integer indication the change (1 added, 2 modified, 3 deleted)

        Returns
        -------
        bool
            True if processing is required.
        """
        if change == Change.added or change == Change.deleted:
            return path in self.devices
        return False

    async def process_file(self, device: str, change: int) -> int | bool:
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
        logger.debug(f"device:{device} change:{change}")
        if change == 1 and device not in self.active_connections:
            self.active_connections.append(device)
            # Use a asynchronous serial connection
            serial2tcp = Serial2TCP(device, self.host, self.port)
            result = await serial2tcp.run()
            logger.debug("Serial instance cleaned up.")
            logger.debug(f"Result : {result}.")
            self.active_connections.remove(device)
            return result
        return 0 # all well
    
    
logger = logging.getLogger(__name__)



    # async def create_socat_instance(self, device):
    #     logger.debug("Creating instance")
    #     task = await asyncio.create_subprocess_exec("/usr/bin/socat",
    #                                                 f"FILE:{device},b115200,raw,echo=0",
    #                                                 f"TCP:localhost:{self.port}",
    #                                                 stdout=asyncio.subprocess.PIPE,
    #                                                 stderr=asyncio.subprocess.PIPE)
    #     logger.debug(f"socat instance Created (pid: {task.pid}).")
    #     await task.wait()
    #     async for line in task.stdout:
    #         logger.debug(f"stdout: {line}")
    #     async for line in task.stderr:
    #         logger.debug(f"stderr: {line}")
    #     logger.debug(f"Socat exit code : {task.returncode}")
    #     return task




    
