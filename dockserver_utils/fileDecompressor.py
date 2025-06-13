from abc import ABC, abstractmethod
import asyncio
import os
from collections import namedtuple
import logging
import re
import shutil

from watchfiles import awatch, Change

import dbdreader.decompress

try:
    from . import filewatcher
except Exception:
    import filewatcher



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

    def parse_filename_line(self, s: str) -> str|None:
        try:
            k, v = s.split(":")
        except ValueError:
            return None
        else:
            return v.strip()
            
    def retrieve_filename_mapping(self, filename: str, max_lines: int = 13) -> dict[str, str]:
        # this should work for dbd and mlg files and their friends.
        keys: list[str] = ["the8x3_filename", "full_filename"]
        filenames: dict[str,str|None] = {}
        with open(filename, 'rb') as fp:
            for i, line in enumerate(fp):
                logger.debug(f"i: {i}, line: {line}")
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
                            s = self.parse_filename_line(ascii_line)
                            logger.debug(f"Found s={s}")
                            filenames[k] = s
                if len(filenames)==2:
                    break
        if len(filenames)==2 and not None in filenames.values():
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
    

class AsynchronousFileDecompressor(filewatcher.AsynchronousDirectoryMonitorBase):

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

    def is_to_be_processed(self, path: str, change: int) -> bool:
        if change != Change.added:
            return False
        file_properties = self.get_file_properties(path)
        if file_properties is None:
            logger.debug(f"is_to_be_processed(): no fileproperties")
            return False
        if file_properties.extension in AsynchronousFileDecompressor.EXTENSIONS and \
           file_properties.directory == "from-glider":
            regex_match = False
            for k, v in AsynchronousFileDecompressor.REGEXES.items():
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
            

    async def process_file(self, path: str, change: int) -> int:
        file_properties = self.get_file_properties(path)
        decompressed_filename = self.file_decompressor.decompress(path)
        if decompressed_filename and file_properties.extension not in [".ccc", ".CCC"]:
            # decompression was successful, and of dbd or mlg type. Now rename the file.
            renamed_file = self.file_renamer.rename(decompressed_filename)
            file_properties_renamed = self.get_file_properties(renamed_file)
            logger.info(f"Decompressed and renamed {file_properties.full_base_filename} to {file_properties_renamed.full_base_filename}")
        elif decompressed_filename:
            # successfully decompressed a cache file.
            file_properties_decompressed = self.get_file_properties(decompressed_filename)
            logger.info(f"Decompressed and renamed {file_properties.full_base_filename} to {file_properties_decompressed.full_base_filename}")
            
if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    async def main():
        file_renamer = DBDMLGFileRenamer() 
        fdc = AsynchronousFileDecompressor(top_directory="/var/local/dockserver/gliders",
                                           file_renamer = file_renamer)
        await fdc.run()

    asyncio.run(main())
else:

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
