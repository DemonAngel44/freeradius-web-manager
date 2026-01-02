"""
RADIUS clients configuration file manager.
Handles reading/writing clients.conf file.
"""

import os
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RadiusClient:
    """Represents a RADIUS client (NAS device)."""
    name: str
    ipaddr: str
    secret: str
    shortname: str = ""
    nastype: str = ""
    comment: str = ""

    def to_dict(self):
        return {
            'name': self.name,
            'ipaddr': self.ipaddr,
            'secret': self.secret,
            'shortname': self.shortname or self.name,
            'nastype': self.nastype,
            'comment': self.comment
        }


class RadiusClientsManager:
    """Manages FreeRADIUS clients.conf file."""

    def __init__(self, clients_file: str):
        self.clients_file = clients_file

    def parse_clients(self) -> List[RadiusClient]:
        """Parse clients.conf and return list of clients."""
        clients = []

        if not os.path.exists(self.clients_file):
            return clients

        with open(self.clients_file, 'r') as f:
            content = f.read()

        # Parse client blocks
        # Format: client NAME { ... }
        pattern = r'#\s*([^\n]*)\nclient\s+(\S+)\s*\{([^}]+)\}'
        alt_pattern = r'client\s+(\S+)\s*\{([^}]+)\}'

        # First try to find clients with comments
        for match in re.finditer(pattern, content):
            comment = match.group(1).strip()
            name = match.group(2)
            block = match.group(3)
            client = self._parse_client_block(name, block, comment)
            if client:
                clients.append(client)

        # Then find clients without comments
        for match in re.finditer(alt_pattern, content):
            name = match.group(1)
            # Skip if already found
            if any(c.name == name for c in clients):
                continue
            block = match.group(2)
            client = self._parse_client_block(name, block, "")
            if client:
                clients.append(client)

        return clients

    def _parse_client_block(self, name: str, block: str, comment: str) -> Optional[RadiusClient]:
        """Parse a client block and return RadiusClient."""
        ipaddr = ""
        secret = ""
        shortname = ""
        nastype = ""

        for line in block.strip().split('\n'):
            line = line.strip()
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"')

                if key == 'ipaddr':
                    ipaddr = value
                elif key == 'secret':
                    secret = value
                elif key == 'shortname':
                    shortname = value
                elif key == 'nastype':
                    nastype = value

        if ipaddr and secret:
            return RadiusClient(
                name=name,
                ipaddr=ipaddr,
                secret=secret,
                shortname=shortname,
                nastype=nastype,
                comment=comment
            )
        return None

    def get_client(self, name: str) -> Optional[RadiusClient]:
        """Get a specific client by name."""
        clients = self.parse_clients()
        for client in clients:
            if client.name == name:
                return client
        return None

    def add_client(self, client: RadiusClient, modified_by: str = "") -> bool:
        """Add a new client. Returns False if client already exists."""
        clients = self.parse_clients()

        # Check if client already exists
        if any(c.name == client.name for c in clients):
            return False

        # Build client block
        client_block = self._build_client_block(client)

        # Append to file
        with open(self.clients_file, 'a') as f:
            f.write(f"\n{client_block}")

        return True

    def update_client(self, name: str, client: RadiusClient, modified_by: str = "") -> bool:
        """Update an existing client."""
        if not os.path.exists(self.clients_file):
            return False

        with open(self.clients_file, 'r') as f:
            content = f.read()

        # Find and replace client block
        # Match with optional comment
        pattern = rf'(#[^\n]*\n)?client\s+{re.escape(name)}\s*\{{[^}}]+\}}'

        if not re.search(pattern, content):
            return False

        new_block = self._build_client_block(client)
        new_content = re.sub(pattern, new_block, content)

        with open(self.clients_file, 'w') as f:
            f.write(new_content)

        return True

    def delete_client(self, name: str, modified_by: str = "") -> bool:
        """Delete a client."""
        if not os.path.exists(self.clients_file):
            return False

        with open(self.clients_file, 'r') as f:
            content = f.read()

        # Match client block with optional preceding comment
        pattern = rf'\n?(#[^\n]*\n)?client\s+{re.escape(name)}\s*\{{[^}}]+\}}'

        if not re.search(pattern, content):
            return False

        new_content = re.sub(pattern, '', content)

        with open(self.clients_file, 'w') as f:
            f.write(new_content)

        return True

    def _build_client_block(self, client: RadiusClient) -> str:
        """Build a client configuration block."""
        lines = []

        if client.comment:
            lines.append(f"# {client.comment}")

        lines.append(f"client {client.name} {{")
        lines.append(f"    ipaddr = {client.ipaddr}")
        lines.append(f"    secret = {client.secret}")

        if client.shortname:
            lines.append(f"    shortname = {client.shortname}")
        if client.nastype:
            lines.append(f"    nastype = {client.nastype}")

        lines.append("}")

        return '\n'.join(lines)

    def create_file_if_missing(self):
        """Create clients.conf if it doesn't exist."""
        if not os.path.exists(self.clients_file):
            os.makedirs(os.path.dirname(self.clients_file), exist_ok=True)
            with open(self.clients_file, 'w') as f:
                f.write("# FreeRADIUS clients configuration\n\n")
                f.write("client localhost {\n")
                f.write("    ipaddr = 127.0.0.1\n")
                f.write("    secret = testing123\n")
                f.write("}\n")
