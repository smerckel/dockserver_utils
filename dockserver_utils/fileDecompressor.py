from abc import ABC, abstractmethod
import asyncio
import os
from collections import namedtuple
import logging
import re
import shutil

from watchfiles import awatch, Change
import aionotify

import dbdreader.decompress

from . import filewatcher



FileProperties = namedtuple("FileProperties",
                            ["path",
                             "full_base_filename",
                             "base_filename",
                             "extension",
                             "directory"])

class GliderFileRenamer(ABC):

    @abstractmethod
    def rename(self, filename: str) -> str:
        pass

    def parse_filename_line(self, s: str) -> str:
        try:
            k, v = s.split(":")
        except ValueError:
            return ""
        else:
            return v.strip()
            
    def retrieve_filename_mapping(self, filename: str, max_lines: int = 13) -> dict[str, str]:
        # this should work for dbd and mlg files and their friends.
        keys: list[str] = ["the8x3_filename", "full_filename"]
        filenames: dict[str,str] = {}
        with open(filename, 'rb') as fp:
            for i, line in enumerate(fp):
                if i > 13:
                    break
                try:
                    ascii_line = line.decode()
                except UnicodeDecodeError:
                    pass
                else:
                    for k in keys:
                        logger.debug(f"checking key {k}")
                        if ascii_line.startswith(k):
                            s: str = self.parse_filename_line(ascii_line)
                            logger.debug(f"Found s={s}")
                            if s:
                                filenames[k] = s
                if len(filenames)==2:
                    break
        if len(filenames)==2:
            return filenames
        else:
            return {}

class DBDMLGFileRenamer(GliderFileRenamer):

    def rename(self, filename: str) -> str:
        filename_mapping = self.retrieve_filename_mapping(filename)
        if filename_mapping['the8x3_filename'] in filename:
            new_filename = filename.replace(filename_mapping['the8x3_filename'],
                                            filename_mapping['full_filename'])
        elif filename_mapping['full_filename'] in filename:
            new_filename = filename.replace(filename_mapping['full_filename'],
                                            filename_mapping['the8x3_filename'])
        else:
            # We should never be here.
            raise ValueError('Could not rename file.')
        logger.debug(f"Renaming {filename} to {new_filename}")
        shutil.move(filename, new_filename)
        return new_filename
    

class AsynchronousFileDecompressorBase(filewatcher.AsynchronousDirectoryMonitorBase):

    EXTENSIONS: list[str] = ".dcd .ecd .mcd .ncb .scd .tcd .mcg .ncg .ccc .DCD .ECD .MCD .NCB .SCD .TCD .MCG .NCG .CCC".split()
    REGEXES: dict[str,re.Pattern] = dict(datafile=re.compile(r"^\d{8}\.(dcd|ecd|mcd|ncd|scd|tcd|DCD|ECD|MCD|NCD|SCD|TCD)$"),
                                         logffile=re.compile(r"^\d{8}\.(mcg|ncg|MCG|NCG)$"),
                                         cachefile=re.compile(r"^[0-9a-fA-F]{8}\.(ccc|CCC)$"))
                                      
    def __init__(self, top_directory: str, file_renamer: GliderFileRenamer=DBDMLGFileRenamer()):
        super().__init__(top_directory)
        self.file_decompressor = dbdreader.decompress.FileDecompressor()
        self.file_renamer = file_renamer
        
        
    def get_file_properties(self, path: str) -> None | FileProperties:
        if os.path.isfile(path):
            full_base_filename = os.path.basename(path)
            base_filename, extension = os.path.splitext(full_base_filename)
            directory = os.path.basename(os.path.dirname(path))
            return FileProperties(path, full_base_filename, base_filename, extension, directory)
        else:
            return None
        
    def is_copied(self, path: str, change: int) -> bool:
        raise NotImplementedError

    
    def is_to_be_processed(self, path: str, flags: int|None=None) -> bool:
        file_properties = self.get_file_properties(path)
        if file_properties is None:
            logger.debug(f"is_to_be_processed(): no fileproperties ({path})")
            return False
        if file_properties.extension in AsynchronousFileDecompressorBase.EXTENSIONS and \
           file_properties.directory == "from-glider":
            regex_match = False
            for k, v in AsynchronousFileDecompressorBase.REGEXES.items():
                regex_match |= bool(v.search(file_properties.full_base_filename))
            if regex_match:
                logger.debug(f"is_to_be_processed(): {path} is a match!")
                return True
            else:
                logger.debug(f"is_to_be_processed(): {path} is not a match! (regex fails)")
                return False
        else:
            logger.debug(f"is_to_be_processed(): {path} is no match.")
            logger.debug(f"     properties: {file_properties}")
            return False
            

    async def process_file(self, path: str, flags: int|None=None) -> int:
        file_properties = self.get_file_properties(path)
        if file_properties is None:
            return 1
        decompressed_filename = self.file_decompressor.decompress(path)
        if decompressed_filename and file_properties.extension not in [".ccc", ".CCC"]:
            # decompression was successful, and of dbd or mlg type. Now rename the file.
            renamed_file = self.file_renamer.rename(decompressed_filename)
            file_properties_renamed = self.get_file_properties(renamed_file)
            if file_properties_renamed is None:
                return 2
            logger.info(f"Decompressed and renamed {file_properties.full_base_filename} to {file_properties_renamed.full_base_filename}")
        elif decompressed_filename:
            # successfully decompressed a cache file.
            file_properties_decompressed = self.get_file_properties(decompressed_filename)
            if file_properties_decompressed is None:
                return 3
            logger.info(f"Decompressed and renamed {file_properties.full_base_filename} to {file_properties_decompressed.full_base_filename}")
        return 0

            
class AsynchronousFileDecompressorWatchfiles(AsynchronousFileDecompressorBase):
                                      
    def __init__(self, top_directory: str, file_renamer: GliderFileRenamer=DBDMLGFileRenamer()):
        super().__init__(top_directory, file_renamer)
        
    def is_copied(self, path: str, change: int) -> bool:
        return change == Change.added # Note this does not work for slow copying.

    ### This method does not do what we want, because watchfiles
    ### cannot detect when a file is being closed. For now rely on aionotify instead.
    async def watch_directory(self) -> None:
        logger.info(f"Started monitoring filesystem under {self.top_directory}.")
        received_error = 0
        async for changes in awatch(self.top_directory):
            for change, path in changes:
                if self.is_copied(path, change) and self.is_to_be_processed(path):
                    received_error = await self.process_file(path)
                    logger.debug(f"process_file({path},{change}) returned {received_error}.")
                    if received_error:
                        s = f"Processing file {path} for change {change} returned an error ({received_error})."
                        logger.info(s)
                        break
            if received_error:
                break
        logger.info(f"Stopped monitoring filesystem under {self.top_directory}.")


        
class AsynchronousFileDecompressorAionotify(AsynchronousFileDecompressorBase):
                                      
    def __init__(self, top_directory: str, file_renamer: GliderFileRenamer=DBDMLGFileRenamer()):
        super().__init__(top_directory, file_renamer)
        self.watcher: aionotify.Watcher
        self.handled_files: list[str] = []

        
    def is_copied(self, path:str, change: int) -> bool:
        copied = False
        if path not in self.handled_files and change == aionotify.Flags.CREATE:
            self.handled_files.append(path)
        elif path in self.handled_files and change == aionotify.Flags.CLOSE_WRITE:
            self.handled_files.remove(path)
            copied = True
        logger.debug(f"path: {path}, change: {change} copied?: {copied}")
        return copied

    async def setup_watcher(self):
        self.watcher = aionotify.Watcher()
        for root, dirs, files in os.walk(self.top_directory):
            if 'from-glider' in dirs:
                alias = os.path.basename(root)
                path = os.path.join(root, 'from-glider')
                if alias!='unknown':
                    self.watcher.watch(alias=alias, path=path,
                                       flags=aionotify.Flags.CREATE|aionotify.Flags.CLOSE_WRITE)
                    logger.debug(f"Added watcher for {alias}.")
        # We also need to take care for when a glider new to the dockserver calls in.
        self.watcher.watch(alias='root', path=self.top_directory, flags=aionotify.Flags.CREATE | aionotify.Flags.ISDIR)
        await self.watcher.setup()

    async def add_new_glider(self, glider:str, path:str) -> bool:
        # give the dockserver some time to create all directories and files for this glider
        await asyncio.sleep(0.5)
        # check if we have a from-glider directory
        wd = os.path.join(path, 'from-glider')
        if glider != 'unknown' and os.path.exists(wd):
            self.watcher.watch(alias=glider, path=wd,
                               flags=aionotify.Flags.CREATE|aionotify.Flags.CLOSE_WRITE)
            return True
        else:
            return False
        
    async def watch_directory(self) -> None:
        await self.setup_watcher()
        while True:
            event = await self.watcher.get_event()
            wd, _ = self.watcher.requests[event.alias]
            path = os.path.join(wd, event.name)
            logger.debug(event)
            if self.is_copied(path, event.flags) and self.is_to_be_processed(path):
                logger.debug(f"{path} is to be processed.")
                received_error = await self.process_file(path)
                logger.debug(f"process_file({path}) returned {received_error}.")
                if received_error:
                    s = f"Processing file {path} for event flags {event.flags} returned an error ({received_error})."
                    logger.info(s)
                    break
            elif event.alias=='root' and event.flags==aionotify.Flags.CREATE | aionotify.Flags.ISDIR:
                result = await self.add_new_glider(event.name, path)
                if result:
                    logger.info(f"New glider ({event.name}) detected.")
                    logger.info(f"Added watcher for {event.name}.")
                else:
                    logger.debug("New directory was created, but seems not to be a glider directory.")
                                
        logger.info(f"Stopped monitoring filesystem under {self.top_directory}.")
    
            

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
