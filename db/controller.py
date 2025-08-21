from db.connect import DB
from db.users import Users
from db.avds import Avds

class Controller:
    """Controlador para manejar operaciones con la base de datos (users y avds)."""
    
    def __init__(self, db_name: str = "./db/surviral_insta.db"):
        self.db = DB(db_name)
        self.users = Users(self.db)
        self.avds = Avds(self.db)
    
    def create_avd(self, avd_name: str) -> bool:
        """Crea un nuevo AVD en la base de datos.
        
        Args:
            avd_name (str): Nombre único del AVD.
        
        Returns:
            bool: True si se creó exitosamente.
        """
        return self.avds.create(avd_name)
    
    def add_user(self, user: str, password: str, key: str = None, new_password: str = None) -> bool:
        """Agrega un usuario a la base de datos, asignando un AVD disponible (con menos de 5 usuarios).
        
        Args:
            user (str): Nombre de usuario.
            password (str): Contraseña.
            key (str, optional): Clave.
            new_password (str, optional): Nueva contraseña.
        
        Returns:
            bool: True si se agregó exitosamente, False si ya existía.
        """
        # Verificar si el usuario ya existe
        existing_user = self.users.read_by_user(user)
        if existing_user:
            print(f"Alerta: El usuario '{user}' ya está registrado y no se volverá a registrar.")
            return False
        
        # Encontrar un AVD activo con menos de 5 usuarios
        available_avd = None
        for avd in self.avds.read_all():
            avd_name, status, _ = avd
            if status == 'active':
                count = len([u for u in self.users.read_all() if u[4] == avd_name])  # Índice 4: avd_name
                if count < 5:
                    available_avd = avd_name
                    break
        
        if not available_avd:
            # Crear un nuevo AVD si no hay disponible
            new_avd_name = f"avd_{len(self.avds.read_all()) + 1:03d}"
            self.create_avd(new_avd_name)
            available_avd = new_avd_name
        
        # Agregar el usuario
        created = self.users.create(user, password, key, new_password, available_avd)
        
        # Verificar si se alcanzó el límite y actualizar status a 'completed'
        count = len([u for u in self.users.read_all() if u[4] == available_avd])
        if count >= 5:
            self.avds.update(available_avd, 'completed')
        
        return created
    
    def add_users(self, users_list: list):
        """Agrega múltiples usuarios desde una lista (e.g., desde Excel).
        
        Args:
            users_list (list): Lista de diccionarios con datos de usuarios ({'user':, 'password':, 'key':, 'new_password':}).
        """
        for user_data in users_list:
            self.add_user(
                user_data['user'],
                user_data['password'],
                user_data.get('key'),
                user_data.get('new_password')
            )
    
    def get_all_users(self) -> list:
        """Obtiene todos los usuarios de la base de datos.
        
        Returns:
            list: Lista de tuplas con los registros de usuarios.
        """
        return self.users.read_all()
    
    def close(self):
        """Cierra la conexión a la base de datos."""
        self.users.close()