# if not __name__ == '__main__':
#     from pytest import fixture
# else:
#     def fixture(func):
#         def inner():
#             return func()
#         return inner

import asyncio
import os
import pytest
import shutil
import tempfile

from dockserver_utils import fileDecompressor

DATA_DIR = "dockserver_utils/data"

@pytest.fixture
def get_fileProperties_dbd():
    with tempfile.TemporaryDirectory() as tmpdirname:
        shutil.copy(os.path.join(DATA_DIR,'01600001.dbd'), tmpdirname)
        fp = fileDecompressor.FileProperties(path=f'{tmpdirname}/01600001.dbd',
                                             full_base_filename='01600001.dbd',
                                             base_filename='01600001',
                                             extension='.dbd',
                                             directory='from-glider')
        yield fp, tmpdirname

@pytest.fixture
def get_fileProperties_mlg():
    with tempfile.TemporaryDirectory() as tmpdirname:
        shutil.copy(os.path.join(DATA_DIR,'01600000.mlg'), tmpdirname)
        fp = fileDecompressor.FileProperties(path=f'{tmpdirname}/01600000.mlg',
                                             full_base_filename='01600000.mlg',
                                             base_filename='01600000',
                                             extension='.mlg',
                                             directory='from-glider')
        yield fp, tmpdirname

        
@pytest.fixture
def setup_tmpdir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


def test_retrieve_filename_mapping_mlg():
    renamer = fileDecompressor.DBDMLGFileRenamer()
    fn = os.path.join(DATA_DIR,"01600000.mlg")
    mapping = renamer.retrieve_filename_mapping(fn)
    assert mapping['the8x3_filename']=='01600000' and mapping['full_filename'] =='k_999-2023-107-0-0'

def test_retrieve_filename_mapping_dbd():
    renamer = fileDecompressor.DBDMLGFileRenamer()
    fn = os.path.join(DATA_DIR,"01600001.dbd")
    mapping = renamer.retrieve_filename_mapping(fn)
    assert mapping['the8x3_filename']=='01600001' and mapping['full_filename'] =='k_999-2023-107-0-1'

    
def test_retrieve_filename_mapping_exptected_failure():
    renamer = fileDecompressor.DBDMLGFileRenamer()
    fn = os.path.join(DATA_DIR,"daad1b20.cac")
    mapping = renamer.retrieve_filename_mapping(fn)
    assert mapping == {}

def test_rename_dbd(get_fileProperties_dbd):
    file_properties, tmpdirname = get_fileProperties_dbd
    renamer = fileDecompressor.DBDMLGFileRenamer()
    renamer.rename(file_properties.path)
    renamed_file = os.path.join(tmpdirname, "k_999-2023-107-0-1.dbd")
    assert os.path.exists(renamed_file)

def test_rename_mlg(get_fileProperties_mlg):
    file_properties, tmpdirname = get_fileProperties_mlg
    renamer = fileDecompressor.DBDMLGFileRenamer()
    renamer.rename(file_properties.path)
    renamed_file = os.path.join(tmpdirname, "k_999-2023-107-0-0.mlg")
    assert os.path.exists(renamed_file)


async def copy_file(src, dst):
    await asyncio.sleep(0.2)
    shutil.copy(src, dst)
    
@pytest.mark.asyncio
async def test_managing_mcg(setup_tmpdir):
    dst = os.path.join(setup_tmpdir, 'from-glider')
    os.mkdir(dst)
    src = os.path.join(DATA_DIR,"01600001.dcd")
    tasks = []
    tasks.append(asyncio.create_task(copy_file(src, dst)))
    file_renamer = fileDecompressor.DBDMLGFileRenamer()
    fdc = fileDecompressor.AsynchronousFileDecompressor(top_directory=dst,
                                           file_renamer = file_renamer)
    tasks.append(asyncio.create_task(fdc.run()))
    done, pending = await asyncio.wait(tasks, timeout=0.4)
    for _t in pending:
        _t.cancel()
    await asyncio.sleep(0.1)
    available_files = os.listdir(dst)
    assert available_files == ['k_999-2023-107-0-1.dbd', '01600001.dcd']

@pytest.mark.asyncio
async def test_managing_ccc(setup_tmpdir):
    dst = os.path.join(setup_tmpdir, 'from-glider')
    os.mkdir(dst)
    src = os.path.join(DATA_DIR,"daad1b20.ccc")
    tasks = []
    tasks.append(asyncio.create_task(copy_file(src, dst)))
    file_renamer = fileDecompressor.DBDMLGFileRenamer()
    fdc = fileDecompressor.AsynchronousFileDecompressor(top_directory=dst,
                                           file_renamer = file_renamer)
    tasks.append(asyncio.create_task(fdc.run()))
    done, pending = await asyncio.wait(tasks, timeout=0.4)
    for _t in pending:
        _t.cancel()
    await asyncio.sleep(0.1)
    available_files = os.listdir(dst)
    assert available_files == ["daad1b20.cac","daad1b20.ccc"]

    
