import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # RADIUS server settings
    RADIUS_SERVER = os.environ.get('RADIUS_SERVER', 'localhost')
    RADIUS_PORT = int(os.environ.get('RADIUS_PORT', 1812))
    RADIUS_SECRET = os.environ.get('RADIUS_SECRET', '')

    # FreeRADIUS users file path
    USERS_FILE = os.environ.get('USERS_FILE', '/etc/raddb/mods-config/files/authorize')

    # FreeRADIUS clients file path
    CLIENTS_FILE = os.environ.get('CLIENTS_FILE', '/etc/raddb/clients.conf')

    # Only users with this prefix can log in as admin (empty = any authenticated user)
    ADMIN_GROUP_PREFIX = os.environ.get('ADMIN_GROUP_PREFIX', '')

    # Setup marker file - if exists, setup is complete
    SETUP_COMPLETE_FILE = os.environ.get('SETUP_COMPLETE_FILE', '/data/.setup_complete')

    # Docker container name for FreeRADIUS (for reload command)
    FREERADIUS_CONTAINER = os.environ.get('FREERADIUS_CONTAINER', 'freeradius')

    # FreeRADIUS accounting log directory
    RADACCT_DIR = os.environ.get('RADACCT_DIR', '/var/log/freeradius/radacct')

    # Session settings
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
