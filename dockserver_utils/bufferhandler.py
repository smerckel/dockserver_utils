from abc import ABC, abstractmethod
import arrow
import asyncio
from collections import deque
import logging
import typing
import re

from .constants import CARRIER_DETECT_UNDEFINED, CARRIER_DETECT_YES, CARRIER_DETECT_NO




class Timer(object):

    def __init__(self, timeout: float = 300.):
        self.timeout = timeout
        self._elapsed = 0.
        self._dt = 1
        self._task = asyncio.create_task(self.run())
        self._active = True
        logger.debug("Timer started...")
        
    def reset(self) -> None:
        self._elapsed = 0.
        self._active = True

    def disable_until_reset(self):
        self._active = False
        
    async def run(self) -> None:
        while True:
            await asyncio.sleep(self._dt)
            self._elapsed += self._dt
            
    async def close(self) -> None:
        # Cancel the task and wait for it to finish
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        logger.debug("Timer closed.")

    @property
    def is_timed_out(self) -> bool:
        return self._active  and  (self._elapsed > self.timeout)
    

class BaseParser(ABC):

    def __init__(self):
        self.name = self.__class__.__name__
    
    @abstractmethod
    def parse(self, s) -> [str, typing.Any]:
        pass

    
class VehicleNameParser(BaseParser):
    def __init__(self):
        super().__init__()
        # Vehicle Name: sebastian
        self.regex = re.compile(r"Vehicle Name: (\w+)")
        
    def parse(self, s):
        result = self.regex.match(s)
        if result:
            return self.name, result.group(1)
        else:
            return self.name, None


class GliderLABDOSParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.regex = re.compile(r"Glider(LAB|DOS)")
        
    def parse(self, s) -> [str, typing.Any]:
        result = self.regex.match(s)
        if result:
            return self.name, result.groups(0)
        else:
            return self.name, None

class GPSTimeParser(BaseParser):
    def __init__(self):
        super().__init__()
        #Curr Time: Mon Jul  7 16:40:19 2025 MT:  176064
        self.regex = re.compile(r"Curr Time: (\w+) (\w+) +(\d+) +(\d+):(\d+):(\d+) (\d+) MT: +(\d+)")
        
    def parse(self, s) -> [str, typing.Any]:
        result = self.regex.match(s)
        if result:
            month, day, hh, mm, ss, year = [result.group(i) for i in range(2, 8)]
            s = f"{day} {month} {year} {hh} {mm} {ss}"
            tm = arrow.get(s, 'D MMM YYYY HH mm ss',  tzinfo='UTC')
            return self.name, tm.timestamp()
        else:
            return self.name, None

class GPSLatLonParser(BaseParser):
    def __init__(self):
        super().__init__()
        #GPS Location:  5231.957 N   718.577 E measured      1.856 secs ago
        self.regex = re.compile(r"GPS Location: +(\d+\.\d+) N ([-]?\d+\.\d+) E measured +(\d+\.\d+) secs ago")
                                
    def parse(self, s) -> [str, typing.Any]:
        result = self.regex.match(s)
        if result:
            lat, lon, ago = [result.group(i) for i in range(1, 4)]
            return self.name, (float(lat), float(lon))
        else:
            return self.name, None



class MenuParser(BaseParser):
    def __init__(self):
        super().__init__()
        
        self.regex = re.compile(r"Hit Control-R to RESUME the mission")
                                
    def parse(self, s) -> [str, typing.Any]:
        result = self.regex.match(s)
        if result:
            return self.name, True
        else:
            return self.name, None

        
  
class DisconnectEventParser(BaseParser):
    def __init__(self):
        super().__init__()
        #self.regex = re.compile(r"(surface_\d+: Waiting for final GPS fix.|.* LOG FILE OPENED)")
        self.regex = re.compile(r"(surface_\d+: Waiting for final GPS fix.|Megabytes available n CF file system)")
                 
    def parse(self, s) -> [str, typing.Any]:
        result = self.regex.match(s)
        if result:
            return self.name, True
        else:
            return self.name, None
        

        
class BufferHandler(object):

    def __init__(self, carrier_dectect: int = CARRIER_DETECT_UNDEFINED):
        logger.info(f"Using BufferHandler for dialogue processing.")
        self.queue = asyncio.Queue()
        self._task = asyncio.create_task(self.process())
        self.parsers = [VehicleNameParser(),
                        GliderLABDOSParser(),
                        GPSTimeParser(),
                        GPSLatLonParser(),
                        MenuParser(),
                        DisconnectEventParser()]
        self.memory = dict()
        self._buffer = ""
        self.memory["connection"] = carrier_dectect
        self.memory["running"] = False
        self.timer = Timer()
        self.line_buffer = deque([], maxlen=5)

    
    async def send(self, data) -> None:
        try:
            s = data.decode()
        except:
            logger.debug("Failed to decode string")
        else:
            await self.queue.put(s)

            
    def clear_buffer(self) -> str:
        try:
            index = self._buffer.index('\n')
        except ValueError:
            s = ""
        else:
            s = self._buffer[:index]
            self._buffer = self._buffer[index + 1:]
        return s

    def clear_memory(self) -> None:
        keys_to_clear = [k for k in self.memory.keys() if not k in ["connection", "VehicleName", "running"]]
        for k in keys_to_clear:
            self.memory.pop(k)

    def connect(self):
        self.memory["connection"] = CARRIER_DETECT_YES
        self.timer.disable_until_reset()

    def disconnect(self):
        self.memory["connection"] = CARRIER_DETECT_NO
        self.timer.reset()

    async def callback(self, command):
        match command:
            case "connect":
                self.connect()
                mesg = f"Device {command}ed."
            case "disconnect":
                self.disconnect()
                mesg = f"Device {command}ed."
            case "status":
                match self.memory["connection"]:
                    case 0: #CARRIER_DETECT_UNDEFINED:
                        mesg = "Connection status undefined"
                    case 1: #CARRIER_DETECT_YES:
                        mesg = "Device is connected."
                    case 2: #CARRIER_DETECT_NO:
                        mesg = "Device is not connected."
            case _:
                mesg = f"Command {command} unprocessed."        

        return mesg
    
    async def process(self) -> None:
        logger.debug("Starting BufferHandler.process()...")
        try:
            while True:
                try:
                    line = await asyncio.wait_for(self.queue.get(), timeout=1.)
                except asyncio.TimeoutError:
                    if self.timer.is_timed_out:
                        self.memory["connection"] = CARRIER_DETECT_NO
                        self.clear_memory()
                    continue
                else:
                    if line:
                        self._buffer += line
                        while True: # process all parts from the buffer that end in \n
                            s = self.clear_buffer()
                            if not s: # empty buffer.
                                break
                            self.line_buffer.append(s)
                            for p in self.parsers:
                                k, v = p.parse(s)
                                if v is not None:
                                    self.memory[k] = v
                                    if k in ["VehicleNameParser", "GliderLABDOSParser"]:
                                        self.timer.reset()
                                        self.memory["connection"] = CARRIER_DETECT_YES
                                    elif k == "MemoryParser":
                                        self.memory["running"] = True
                                    if k =="GliderLABDOSParser":
                                        self.memory["running"] = False
                                    elif k in ["DisconnectEventParser"]:
                                        self.memory["connection"] = CARRIER_DETECT_NO
                                        self.memory["running"] = False
                                        self.clear_memory()
                if self.memory["running"]:
                    self.timer.reset()
                logger.debug(self.memory)
                                
        except asyncio.CancelledError:
            pass # got cancelled.
        logger.debug("Exiting process().")
        
    async def close(self) -> None:
        # Cancel the task and wait for it to finish
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    @property
    def cd(self) -> bool:
        carrier_dectect = self.memory["connection"]
        if carrier_dectect == CARRIER_DETECT_UNDEFINED:
            carrier_dectect = CARRIER_DETECT_YES # Give control by default.
        return carrier_dectect==CARRIER_DETECT_YES
        
class DummyBufferHandler(object):
    def __init__(self):
        logger.info("Using DummyBufferHandler for dialogue processing.")
        
    async def send(self, *p) -> None:
        return

    async def close(self) -> None:
        return
    
    @property
    def cd(self) -> int:
        return CARRIER_DETECT_YES

    async def callback(self, *p) -> None:
        logger.debug("DUMMY Callback called.")
        return 
    
logger = logging.getLogger(__name__)

    
