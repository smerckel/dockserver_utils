from abc import ABC, abstractmethod
import asyncio
import logging
import typing

from watchfiles import awatch, Change

logger = logging.getLogger(__name__)

class AsynchronousDirectoryMonitorBase(ABC):
    """Abstract Base Class for monitoring the activity of a directory structure.

    The base class defines the following API:

    run() *aysncio coroutine* as the entry point

    if any directory or file is added, modified or deleted, the path
    and its change attribute will be send to

    is_to_be_processed() *asyncio coroutine* *needs to be subclassed*

    In here logic can be implemented whether the file should be processed or not.

    If is_to_be_processed() returns True, the file is handled in

    process_file() *asyncio coroutine*.

    This method is also to be subclassed.
    """
    
    def __init__(self, top_directory: str):
        self.top_directory = top_directory

    @abstractmethod
    def is_to_be_processed(self, path: str, change: int) -> bool:
        pass

    @abstractmethod
    async def process_file(self, path: str, change: int) -> int:
        pass

    async def watch_directory(self) -> None:
        logger.info(f"Started monitoring filesystem under {self.top_directory}.")
        received_error = 0
        async for changes in awatch(self.top_directory):
            for change, path in changes:
                if self.is_to_be_processed(path, change):
                    received_error = await self.process_file(path, change)
                    if received_error:
                        s = f"Processing file {path} for change {change} returned an error ({received_error})."
                        logger.info(s)
                        break
            if received_error:
                break
        logger.info(f"Stopped monitoring filesystem under {self.top_directory}.")
            
    async def run(self) -> None:
        ''' Asynchronous entry method
        '''
        await self.watch_directory()


    



    


    
