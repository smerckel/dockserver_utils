import asyncio
import aionotify
import os

from dockserver_utils import filewatcher
import logging

logger = logging.getLogger(__name__)


class AsynchronousFileDecompressorAionotify(filewatcher.AsynchronousDirectoryMonitorBase):

    def __init__(self, top_directory):
        super().__init__(top_directory)
        self.watcher: None|aionotify.Watcher=None
        self.handled_files: list[str] = []
        self.alias_mapping: dict[str, str] = {}

    def is_copied(self, path:str, change: int) -> bool:
        copied = False
        if path not in self.handled_files and change == aionotify.Flags.CREATE:
            self.handled_files.append(path)
        elif path in self.handled_files and change == aionotify.Flags.CLOSE_WRITE:
            self.handled_files.remove(path)
            copied = True
        logger.debug(f"path: {path}, change: {change} copied?: {copied}")
        return copied

    def is_to_be_processed(self, path: str) -> bool:
        return True
    
    async def process_file(self, path:str, change: int) -> int:
        logger.debug(f"path: {path}, change: {change}")
        await asyncio.sleep(1)

    async def setup_watcher(self):
        self.watcher = aionotify.Watcher()
        for root, dirs, files in os.walk(self.top_directory):
            if 'from-glider' in dirs:
                alias = os.path.basename(root)
                path = os.path.join(root, 'from-glider')
                if alias!='unknown':
                    self.watcher.watch(alias=alias, path=path,
                                       flags=aionotify.Flags.CREATE|aionotify.Flags.CLOSE_WRITE)
                    self.alias_mapping[alias] = path
                    logger.debug(f"Added watcher for {alias}.")
        # todo think of something to handle when new gliders are added.
        await self.watcher.setup()

        
    async def watch_directory(self) -> None:
        await self.setup_watcher()
        while True:
            event = await self.watcher.get_event()
            path = os.path.join(self.alias_mapping[event.alias], event.name)
            if self.is_copied(path, event.flags) and self.is_to_be_processed(path):
                logger.debug(f"{path} is to be processed.")
            
        
        logger.debug("watch_directory")
        
fw = AsynchronousFileDecompressorAionotify('/var/local/dockserver/gliders')

logging.basicConfig(level=logging.WARNING)
logger.setLevel(logging.DEBUG)

asyncio.run(fw.run())





# import os
# import asyncio
# import aionotify

# # Setup the watcher
# watcher = aionotify.Watcher()
# watcher.watch(alias='logs', path='/var/local/dockserver/gliders/bornsim_001/from-glider', flags=aionotify.Flags.CREATE|aionotify.Flags.CLOSE_WRITE)

# async def work():
#     await watcher.setup()
#     for _i in range(10):
#         # Pick the 10 first events
#         event = await watcher.get_event()
#         print(event)
#     watcher.close()

# asyncio.run(work())

