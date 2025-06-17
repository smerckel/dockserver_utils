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
        self.top_directory:str = top_directory
        self.alias_mapping: dict[str, str] = {}
        
    @abstractmethod
    def is_to_be_processed(self, path: str, flags: int|None=None) -> bool:
        pass

    @abstractmethod
    async def process_file(self, path: str, flags: int|None=None) -> int:
        pass

    @abstractmethod
    async def watch_directory(self) -> None:
        pass
    
    async def run(self) -> None:
        ''' Asynchronous entry method
        '''
        await self.watch_directory()


    



    


    
