import sqlite3
from typing import List, Dict, Tuple
from db.connect import DB

class Users:
    """Clase para gestionar la tabla 'users' con operaciones CRUD."""
    
    def __init__(self, db: DB):
        """Inicializa la clase Users con una instancia de DB.
        
        Args:
            db (DB): Instancia de la clase DB para manejar la conexión.
        """
        self.db = db
        self.db.connect()
        # Crear la tabla 'users' con las columnas especificadas
        self.db.create_table("users", '''
            user TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            key TEXT,
            new_password TEXT,
            avd_name TEXT,
            status TEXT DEFAULT 'active',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ''')
    
    def create(self, user: str, password: str, key: str = None, new_password: str = None, avd_name: str = None):
        """Crea un nuevo registro en la tabla 'users'.
        
        Args:
            user (str): Nombre de usuario (clave primaria).
            password (str): Contraseña.
            key (str, optional): Clave.
            new_password (str, optional): Nueva contraseña.
            avd_name (str, optional): Nombre del AVD asociado.
        
        Returns:
            bool: True si se creó exitosamente, False si el usuario ya existe.
        """
        try:
            self.db.execute_query(
                "INSERT INTO users (user, password, key, new_password, avd_name) VALUES (?, ?, ?, ?, ?)",
                (user, password, key, new_password, avd_name)
            )
            return True
        except sqlite3.IntegrityError:
            return False
    
    def read_all(self) -> List[Tuple]:
        """Lee todos los registros de la tabla 'users'.
        
        Returns:
            List[Tuple]: Lista de tuplas con los registros.
        """
        return self.db.execute_query("SELECT * FROM users")
    
    def read_by_user(self, user: str) -> Tuple:
        """Lee un registro por nombre de usuario.
        
        Args:
            user (str): Nombre de usuario a buscar.
        
        Returns:
            Tuple: Registro encontrado o None si no existe.
        """
        result = self.db.execute_query("SELECT * FROM users WHERE user = ?", (user,))
        return result[0] if result else None
    
    def update(self, user: str, password: str = None, key: str = None, new_password: str = None, avd_name: str = None, status: str = None):
        """Actualiza un registro en la tabla 'users'.
        
        Args:
            user (str): Nombre de usuario a actualizar.
            password (str, optional): Nueva contraseña.
            key (str, optional): Nueva clave.
            new_password (str, optional): Nueva contraseña.
            avd_name (str, optional): Nuevo AVD asociado.
            status (str, optional): Nuevo estado (e.g., 'active', 'inactive').
        
        Returns:
            bool: True si se actualizó, False si el usuario no existe.
        """
        current = self.read_by_user(user)
        if not current:
            return False
        
        # Usar valores actuales si no se proporcionan nuevos
        avd_name = avd_name if avd_name is not None else current[4]
        status = status if status is not None else current[5]
        new_password = new_password if new_password is not None else current[3]
        key = key if key is not None else current[2]
        password = password if password is not None else current[1]
        
        self.db.execute_query(
            "UPDATE users SET password = ?, key = ?, new_password = ?, avd_name = ?, status = ? WHERE user = ?",
            (password, key, new_password, avd_name, status, user)
        )
        return True
    
    def delete(self, user: str) -> bool:
        """Elimina un registro de la tabla 'users'.
        
        Args:
            user (str): Nombre de usuario a eliminar.
        
        Returns:
            bool: True si se eliminó, False si el usuario no existe.
        """
        if not self.read_by_user(user):
            return False
        self.db.execute_query("DELETE FROM users WHERE user = ?", (user,))
        return True
    
    def close(self):
        """Cierra la conexión a la base de datos."""
        self.db.close()