"""
Audit logging for tracking changes to users and clients.
"""

import os
import json
from datetime import datetime
from threading import Lock

# File-based audit log
AUDIT_LOG_FILE = '/data/audit_log.json'
MAX_ENTRIES = 1000  # Keep last 1000 entries

_lock = Lock()


def get_audit_log_path():
    """Get the path to the audit log file."""
    # Use environment variable or default
    return os.environ.get('AUDIT_LOG_FILE', AUDIT_LOG_FILE)


def log_action(action, target_type, target_name, user, details=None):
    """
    Log an action to the audit log.

    Args:
        action: The action performed (create, update, delete, toggle, login, etc.)
        target_type: The type of target (user, client, system)
        target_name: The name/identifier of the target
        user: The user who performed the action
        details: Optional additional details as a dict
    """
    entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'action': action,
        'target_type': target_type,
        'target_name': target_name,
        'user': user,
        'details': details or {}
    }

    log_path = get_audit_log_path()

    with _lock:
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(log_path), exist_ok=True)

            # Read existing entries
            entries = []
            if os.path.exists(log_path):
                try:
                    with open(log_path, 'r') as f:
                        entries = json.load(f)
                except (json.JSONDecodeError, IOError):
                    entries = []

            # Add new entry at the beginning
            entries.insert(0, entry)

            # Trim to max entries
            entries = entries[:MAX_ENTRIES]

            # Write back
            with open(log_path, 'w') as f:
                json.dump(entries, f, indent=2)

        except Exception as e:
            # Log error but don't fail the main operation
            print(f"Audit log error: {e}")


def get_audit_log(limit=100, offset=0, target_type=None, action=None, user=None):
    """
    Retrieve audit log entries.

    Args:
        limit: Maximum number of entries to return
        offset: Number of entries to skip
        target_type: Filter by target type
        action: Filter by action
        user: Filter by user

    Returns:
        List of audit log entries
    """
    log_path = get_audit_log_path()

    with _lock:
        try:
            if not os.path.exists(log_path):
                return []

            with open(log_path, 'r') as f:
                entries = json.load(f)

        except (json.JSONDecodeError, IOError):
            return []

    # Apply filters
    if target_type:
        entries = [e for e in entries if e.get('target_type') == target_type]
    if action:
        entries = [e for e in entries if e.get('action') == action]
    if user:
        entries = [e for e in entries if e.get('user') == user]

    # Apply pagination
    return entries[offset:offset + limit]


def clear_audit_log():
    """Clear the audit log (admin only)."""
    log_path = get_audit_log_path()

    with _lock:
        try:
            if os.path.exists(log_path):
                os.remove(log_path)
        except IOError as e:
            print(f"Error clearing audit log: {e}")
