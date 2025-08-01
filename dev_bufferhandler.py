import asyncio
import logging
from dockserver_utils.serial2tcp import BufferHandler
import dockserver_utils.serial2tcp as s2t

with open("/home/lucas/samba/dockserver_gliders/bornsim_001/logs/bornsim_001_network_20250708T094543.log") as fp:
    data = fp.readlines()
    

logging.basicConfig(level=logging.ERROR)
s2t.logger.setLevel(logging.DEBUG)

async def main():
    buffer_handler = BufferHandler()
    for line in data:
        s2t.logger.debug(f"line: {line}")
        await buffer_handler.send(line)
        #await asyncio.sleep(.01)


asyncio.run(main())

