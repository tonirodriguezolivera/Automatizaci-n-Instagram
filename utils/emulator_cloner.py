import os
import re
import shutil
import aiofiles
import asyncio
from pathlib import Path

class EmulatorCloner:
    # Datos estáticos
    #AVD_DIR = '/home/customer/.android/avd/'
    AVD_DIR = Path.home() / ".android" / "avd"
    #BASE_NAME = 'Pixel4_API31_PlayStore'
    BASE_NAME = 'Nexus_5_API_31'
    BASE_AVD = os.path.join(AVD_DIR, BASE_NAME + '.avd')
    BASE_INI = os.path.join(AVD_DIR, BASE_NAME + '.ini')

    @staticmethod
    async def verify_base_files() -> None:
        """
        Verifica asíncronamente que existan los archivos base.
        
        :raises ValueError: Si el directorio base o el archivo .ini no existen.
        """
        if not os.path.isdir(EmulatorCloner.BASE_AVD):
            raise ValueError(f"El directorio base '{EmulatorCloner.BASE_AVD}' no existe.")
        if not os.path.isfile(EmulatorCloner.BASE_INI):
            raise ValueError(f"El archivo base '{EmulatorCloner.BASE_INI}' no existe.")
    
    @staticmethod
    async def list_avd_files() -> list:
        """
        Lista asíncronamente todos los archivos y directorios en la ruta de AVD.
        
        :return: Lista de nombres de archivos y directorios.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, os.listdir, EmulatorCloner.AVD_DIR)
    
    @staticmethod
    async def get_existing_clones() -> list:
        """
        Detecta asíncronamente los clones existentes basados en el patrón '{BASE_NAME}_CloneN.avd'.
        
        :return: Lista de números de clones existentes (e.g., [1, 2, 3]).
        """
        clones = []
        pattern = re.compile(rf"{re.escape(EmulatorCloner.BASE_NAME)}_Clone(\d+)\.avd")
        files = await EmulatorCloner.list_avd_files()
        for item in files:
            item_path = os.path.join(EmulatorCloner.AVD_DIR, item)
            loop = asyncio.get_event_loop()
            is_dir = await loop.run_in_executor(None, os.path.isdir, item_path)
            if is_dir:
                match = pattern.match(item)
                if match:
                    clones.append(int(match.group(1)))
        return sorted(clones)
    
    @staticmethod
    async def get_next_clone_num() -> int:
        """
        Obtiene asíncronamente el siguiente número de clone disponible.
        
        :return: Siguiente número (e.g., si existen 1,2,3, retorna 4).
        """
        existing = await EmulatorCloner.get_existing_clones()
        if not existing:
            return 1
        return max(existing) + 1
    
    @staticmethod
    async def clone_emulator() -> str:
        """
        Realiza la clonación del emulador de forma asíncrona:
        - Copia el directorio .avd base al nuevo nombre.
        - Copia el archivo .ini base al nuevo nombre.
        - Modifica el archivo .ini clonado actualizando 'path' y 'path.rel'.
        
        :return: Nombre del nuevo clone (e.g., 'Pixel4_API31_PlayStore_Clone4').
        """
        await EmulatorCloner.verify_base_files()
        
        num = await EmulatorCloner.get_next_clone_num()
        new_name = f"{EmulatorCloner.BASE_NAME}_Clone{num}"
        new_avd = os.path.join(EmulatorCloner.AVD_DIR, new_name + '.avd')
        new_ini = os.path.join(EmulatorCloner.AVD_DIR, new_name + '.ini')
        
        # Copia el directorio .avd
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, shutil.copytree, EmulatorCloner.BASE_AVD, new_avd)
        
        # Copia el archivo .ini
        await loop.run_in_executor(None, shutil.copy, EmulatorCloner.BASE_INI, new_ini)
        
        # Modifica el archivo .ini
        async with aiofiles.open(new_ini, 'r') as f:
            lines = await f.readlines()
        
        new_lines = []
        for line in lines:
            if line.startswith('path='):
                new_lines.append(f"path={os.path.join(EmulatorCloner.AVD_DIR, new_name + '.avd')}\n")
            elif line.startswith('path.rel='):
                new_lines.append(f"path.rel=avd/{new_name}.avd\n")
            else:
                new_lines.append(line)
        
        async with aiofiles.open(new_ini, 'w') as f:
            await f.writelines(new_lines)
        
        return new_name