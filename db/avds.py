import sqlite3
from typing import List, Tuple
from db.connect import DB

class Avds:
    """Clase para gestionar la tabla 'avds' con operaciones CRUD."""
    
    def __init__(self, db: DB):
        """Inicializa la clase Avds con una instancia de DB.
        
        Args:
            db (DB): Instancia de la clase DB para manejar la conexión.
        """
        self.db = db
        self.db.connect()
        # Crear la tabla 'avds' con las columnas especificadas
        self.db.create_table("avds", '''
            avd_name TEXT PRIMARY KEY,
            status TEXT DEFAULT 'active',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ''')
    
    def create(self, avd_name: str):
        """Crea un nuevo registro en la tabla 'avds'.
        
        Args:
            avd_name (str): Nombre único del AVD (clave primaria).
        
        Returns:
            bool: True si se creó exitosamente, False si el AVD ya existe.
        """
        try:
            self.db.execute_query(
                "INSERT INTO avds (avd_name) VALUES (?)",
                (avd_name,)
            )
            return True
        except sqlite3.IntegrityError:
            return False
    
    def read_all(self) -> List[Tuple]:
        """Lee todos los registros de la tabla 'avds'.
        
        Returns:
            List[Tuple]: Lista de tuplas con los registros.
        """
        return self.db.execute_query("SELECT * FROM avds")
    
    def read_by_avd_name(self, avd_name: str) -> Tuple:
        """Lee un registro por nombre de AVD.
        
        Args:
            avd_name (str): Nombre del AVD a buscar.
        
        Returns:
            Tuple: Registro encontrado o None si no existe.
        """
        result = self.db.execute_query("SELECT * FROM avds WHERE avd_name = ?", (avd_name,))
        return result[0] if result else None
    
    def update(self, avd_name: str, status: str = None):
        """Actualiza un registro en la tabla 'avds'.
        
        Args:
            avd_name (str): Nombre del AVD a actualizar.
            status (str, optional): Nuevo estado (e.g., 'active', 'completed').
        
        Returns:
            bool: True si se actualizó, False si el AVD no existe.
        """
        current = self.read_by_avd_name(avd_name)
        if not current:
            return False
        
        # Usar valor actual si no se proporciona un nuevo status
        status = status if status is not None else current[1]
        
        self.db.execute_query(
            "UPDATE avds SET status = ? WHERE avd_name = ?",
            (status, avd_name)
        )
        return True
    
    def delete(self, avd_name: str) -> bool:
        """Elimina un registro de la tabla 'avds'.
        
        Args:
            avd_name (str): Nombre del AVD a eliminar.
        
        Returns:
            bool: True si se eliminó, False si el AVD no existe.
        """
        if not self.read_by_avd_name(avd_name):
            return False
        self.db.execute_query("DELETE FROM avds WHERE avd_name = ?", (avd_name,))
        return True
    
    def close(self):
        """Cierra la conexión a la base de datos."""
        self.db.close()