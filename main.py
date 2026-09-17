"""Punto de entrada de la aplicación.

La lógica principal vive en main_original.py para mantener un único módulo
de aplicación y evitar duplicar funciones entre entry points.
El acceso normal al sistema se realiza mediante inicio.py, que configura
la sesión y los permisos del usuario antes de crear la interfaz.
"""

from main_original import *  # noqa: F401,F403
