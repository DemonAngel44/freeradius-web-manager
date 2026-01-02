"""
FreeRADIUS users file parser and writer.

Handles the standard FreeRADIUS users file format:

# Comment for user
username Cleartext-Password := "password"
    Framed-Protocol = PPP,
    Service-Type = Framed-User

# DISABLED: username - reason
"""

import re
import os
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RadiusUser:
    username: str
    password: str
    comment: str = ""
    disabled: bool = False
    attributes: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            'username': self.username,
            'password': self.password,
            'comment': self.comment,
            'disabled': self.disabled,
            'attributes': self.attributes
        }


class RadiusFileManager:
    """Manages FreeRADIUS users file operations."""

    DEFAULT_ATTRIBUTES = {
        'Framed-Protocol': 'PPP',
        'Service-Type': 'Framed-User'
    }

    def __init__(self, file_path: str):
        self.file_path = file_path

    def _backup_file(self):
        """Create a backup of the users file before modifications."""
        if os.path.exists(self.file_path):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{self.file_path}.backup_{timestamp}"
            shutil.copy2(self.file_path, backup_path)
            return backup_path
        return None

    def parse_users(self) -> List[RadiusUser]:
        """Parse the FreeRADIUS users file and return list of users."""
        users = []

        if not os.path.exists(self.file_path):
            return users

        with open(self.file_path, 'r') as f:
            content = f.read()

        # Split into blocks (user entries)
        lines = content.split('\n')
        current_comment = ""
        current_user = None
        current_attributes = {}

        for line in lines:
            line_stripped = line.strip()

            # Skip empty lines
            if not line_stripped:
                if current_user:
                    # End of user entry
                    users.append(RadiusUser(
                        username=current_user['username'],
                        password=current_user['password'],
                        comment=current_comment.strip(),
                        disabled=current_user.get('disabled', False),
                        attributes=current_attributes
                    ))
                    current_user = None
                    current_attributes = {}
                    current_comment = ""
                continue

            # Check for disabled user comment
            disabled_match = re.match(r'^#\s*DISABLED:\s*(\S+)\s*-?\s*(.*)?$', line_stripped)
            if disabled_match:
                username = disabled_match.group(1)
                reason = disabled_match.group(2) or ""
                users.append(RadiusUser(
                    username=username,
                    password="",  # Password not stored for disabled users in comment form
                    comment=reason.strip(),
                    disabled=True,
                    attributes={}
                ))
                current_comment = ""
                continue

            # Regular comment line
            if line_stripped.startswith('#'):
                if current_user is None:
                    current_comment = line_stripped[1:].strip()
                continue

            # Check for user definition line
            # Format: username Cleartext-Password := "password"
            user_match = re.match(
                r'^(\S+)\s+Cleartext-Password\s*:=\s*"([^"]*)"',
                line_stripped
            )
            if user_match:
                current_user = {
                    'username': user_match.group(1),
                    'password': user_match.group(2),
                    'disabled': False
                }
                continue

            # Check for attribute line (indented)
            if line.startswith((' ', '\t')) and current_user:
                # Parse attribute: Name = Value or Name = Value,
                attr_match = re.match(r'^\s*(\S+)\s*=\s*(\S+),?\s*$', line_stripped)
                if attr_match:
                    attr_name = attr_match.group(1)
                    attr_value = attr_match.group(2)
                    current_attributes[attr_name] = attr_value

        # Don't forget the last user if file doesn't end with blank line
        if current_user:
            users.append(RadiusUser(
                username=current_user['username'],
                password=current_user['password'],
                comment=current_comment.strip(),
                disabled=current_user.get('disabled', False),
                attributes=current_attributes
            ))

        return users

    def get_user(self, username: str) -> Optional[RadiusUser]:
        """Get a specific user by username."""
        users = self.parse_users()
        for user in users:
            if user.username == username:
                return user
        return None

    def _format_user_entry(self, user: RadiusUser) -> str:
        """Format a user entry for the users file."""
        lines = []

        if user.disabled:
            comment_part = f" - {user.comment}" if user.comment else ""
            lines.append(f"# DISABLED: {user.username}{comment_part}")
        else:
            if user.comment:
                lines.append(f"# {user.comment}")
            lines.append(f'{user.username} Cleartext-Password := "{user.password}"')

            # Add attributes
            attributes = user.attributes if user.attributes else self.DEFAULT_ATTRIBUTES
            attr_lines = []
            for name, value in attributes.items():
                attr_lines.append(f"    {name} = {value}")

            # Add commas to all but the last attribute
            for i, attr_line in enumerate(attr_lines):
                if i < len(attr_lines) - 1:
                    lines.append(attr_line + ",")
                else:
                    lines.append(attr_line)

        return '\n'.join(lines)

    def save_users(self, users: List[RadiusUser], admin_user: str = "system"):
        """Save users list to the file."""
        self._backup_file()

        # Generate file content
        lines = [
            "# FreeRADIUS Users File",
            f"# Last modified: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by {admin_user}",
            ""
        ]

        for user in users:
            lines.append(self._format_user_entry(user))
            lines.append("")  # Blank line between entries

        content = '\n'.join(lines)

        with open(self.file_path, 'w') as f:
            f.write(content)

    def add_user(self, user: RadiusUser, admin_user: str = "system") -> bool:
        """Add a new user."""
        users = self.parse_users()

        # Check if user already exists
        for existing in users:
            if existing.username == user.username:
                return False

        users.append(user)
        self.save_users(users, admin_user)
        return True

    def update_user(self, username: str, updated_user: RadiusUser, admin_user: str = "system") -> bool:
        """Update an existing user."""
        users = self.parse_users()

        for i, user in enumerate(users):
            if user.username == username:
                users[i] = updated_user
                self.save_users(users, admin_user)
                return True

        return False

    def delete_user(self, username: str, admin_user: str = "system") -> bool:
        """Delete a user."""
        users = self.parse_users()
        original_count = len(users)

        users = [u for u in users if u.username != username]

        if len(users) < original_count:
            self.save_users(users, admin_user)
            return True

        return False

    def toggle_user(self, username: str, admin_user: str = "system") -> Optional[bool]:
        """Toggle user enabled/disabled status. Returns new status or None if user not found."""
        users = self.parse_users()

        for i, user in enumerate(users):
            if user.username == username:
                users[i].disabled = not users[i].disabled
                self.save_users(users, admin_user)
                return users[i].disabled

        return None

    def has_users(self) -> bool:
        """Check if any users exist in the file."""
        return len(self.parse_users()) > 0

    def file_exists(self) -> bool:
        """Check if the users file exists."""
        return os.path.exists(self.file_path)

    def create_file_if_missing(self):
        """Create the users file if it doesn't exist."""
        if not os.path.exists(self.file_path):
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, 'w') as f:
                f.write("# FreeRADIUS Users File\n")
                f.write(f"# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
