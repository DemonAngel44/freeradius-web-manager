"""
RADIUS authentication module.

Authenticates admin users against the FreeRADIUS server.
"""

import socket
from functools import wraps
from flask import session, redirect, url_for, request, current_app, flash
from pyrad.client import Client
from pyrad.dictionary import Dictionary
from pyrad import packet
import os


# Minimal RADIUS dictionary for authentication
RADIUS_DICT = """
ATTRIBUTE	User-Name		1	string
ATTRIBUTE	User-Password		2	string
ATTRIBUTE	NAS-IP-Address		4	ipaddr
ATTRIBUTE	NAS-Port		5	integer
ATTRIBUTE	Service-Type		6	integer
ATTRIBUTE	Framed-Protocol		7	integer
ATTRIBUTE	NAS-Identifier		32	string
"""


def get_radius_dictionary():
    """Get or create a RADIUS dictionary."""
    dict_path = '/tmp/radius_dictionary'
    if not os.path.exists(dict_path):
        with open(dict_path, 'w') as f:
            f.write(RADIUS_DICT)
    return Dictionary(dict_path)


def authenticate_radius(username: str, password: str) -> bool:
    """
    Authenticate a user against the RADIUS server.

    Args:
        username: The username to authenticate
        password: The password to verify

    Returns:
        True if authentication successful, False otherwise
    """
    try:
        server = current_app.config['RADIUS_SERVER']
        port = current_app.config['RADIUS_PORT']
        secret = current_app.config['RADIUS_SECRET'].encode()

        if not secret:
            current_app.logger.error("RADIUS_SECRET not configured")
            return False

        # Create RADIUS client
        client = Client(
            server=server,
            authport=port,
            secret=secret,
            dict=get_radius_dictionary()
        )
        client.timeout = 5

        # Create authentication request
        req = client.CreateAuthPacket(code=packet.AccessRequest)
        req["User-Name"] = username
        req["User-Password"] = req.PwCrypt(password)
        req["NAS-Identifier"] = "freeradius-web-manager"

        # Send request and get response
        reply = client.SendPacket(req)

        if reply.code == packet.AccessAccept:
            current_app.logger.info(f"RADIUS auth successful for user: {username}")
            return True
        else:
            current_app.logger.warning(f"RADIUS auth failed for user: {username}")
            return False

    except socket.timeout:
        current_app.logger.error(f"RADIUS server timeout: {server}:{port}")
        return False
    except Exception as e:
        current_app.logger.error(f"RADIUS authentication error: {str(e)}")
        return False


def is_admin_user(username: str) -> bool:
    """Check if the username is an admin user (has ADM- prefix by default)."""
    prefix = current_app.config.get('ADMIN_GROUP_PREFIX', 'ADM-')
    return username.startswith(prefix)


def login_required(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            if request.is_json:
                return {'error': 'Authentication required'}, 401
            return redirect(url_for('main.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user() -> str:
    """Get the currently logged in username."""
    return session.get('username', 'anonymous')
