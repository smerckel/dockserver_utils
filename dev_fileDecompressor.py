import asyncio
import logging
import os
import sys



from dockserver_utils import fileDecompressor


log_level = logging.DEBUG
logging.basicConfig(level=logging.WARNING)
fileDecompressor.logger.setLevel(log_level)
logger = logging.getLogger(__name__)
logger.setLevel(log_level)


    
file_renamer = fileDecompressor.DBDMLGFileRenamer()
logger.info(f"Started monitoring for any compressed binary glider data files to arrive.")
logger.info(f"The top directory is set to /var/local/dockserver/gliders.")
fdc = fileDecompressor.AsynchronousFileDecompressorAionotify(top_directory='/var/local/dockserver/gliders',
                                                             file_renamer = file_renamer)
asyncio.run(fdc.run())
