"""
Flask routes for web views and API endpoints.
"""

import os
import re
import json
import socket
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app.auth import (
    authenticate_radius, is_admin_user, login_required, get_current_user,
    is_setup_complete, mark_setup_complete, setup_required
)
from app.radius_file import RadiusFileManager, RadiusUser
from app.radius_clients import RadiusClientsManager, RadiusClient
from app.audit import log_action, get_audit_log

main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)


def get_file_manager():
    """Get the RadiusFileManager instance."""
    return RadiusFileManager(current_app.config['USERS_FILE'])


def get_clients_manager():
    """Get the RadiusClientsManager instance."""
    return RadiusClientsManager(current_app.config['CLIENTS_FILE'])


# ============== Web Views ==============

@main_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """First-run setup page."""
    # If setup is already complete, redirect to login
    if is_setup_complete():
        return redirect(url_for('main.login'))

    manager = get_file_manager()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        errors = []

        if not username:
            errors.append('Username is required')
        if not password:
            errors.append('Password is required')
        if password != confirm_password:
            errors.append('Passwords do not match')
        if len(password) < 8:
            errors.append('Password must be at least 8 characters')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('setup.html')

        # Create the users file if it doesn't exist
        manager.create_file_if_missing()

        # Create the first admin user
        user = RadiusUser(
            username=username,
            password=password,
            comment="Initial admin user",
            disabled=False
        )

        if manager.add_user(user, "setup"):
            # Mark setup as complete
            mark_setup_complete()
            flash(f'Admin user "{username}" created successfully. You can now log in.', 'success')
            current_app.logger.info(f"Setup complete. Admin user created: {username}")
            return redirect(url_for('main.login'))
        else:
            flash(f'User "{username}" already exists', 'error')

    return render_template('setup.html')


@main_bp.route('/')
@setup_required
@login_required
def index():
    """Redirect to dashboard."""
    return redirect(url_for('main.dashboard'))


@main_bp.route('/dashboard')
@setup_required
@login_required
def dashboard():
    """Main dashboard with live sessions and quick stats."""
    # Get user stats
    user_manager = get_file_manager()
    users_list = user_manager.parse_users()
    total_users = len(users_list)
    enabled_users = len([u for u in users_list if not u.disabled])

    # Get client stats
    clients_manager = get_clients_manager()
    clients_list = clients_manager.parse_clients()
    total_clients = len(clients_list)
    clients_dict = {c.ipaddr: c.name for c in clients_list}

    # Get active sessions
    log_dir = current_app.config.get('RADACCT_DIR', '/data/radacct')
    all_records = get_activity_records(log_dir, limit=500)
    active_sessions = get_active_sessions(all_records)

    # Enrich sessions with client names
    for session in active_sessions:
        nas_ip = session.get('NAS-IP-Address', '')
        session['_nas_name'] = clients_dict.get(nas_ip, session.get('NAS-Identifier', nas_ip))

    # Get recent activity (last 10)
    recent_activity = all_records[:10]

    return render_template('dashboard.html',
                           total_users=total_users,
                           enabled_users=enabled_users,
                           total_clients=total_clients,
                           active_sessions=active_sessions,
                           active_count=len(active_sessions),
                           recent_activity=recent_activity)


@main_bp.route('/login', methods=['GET', 'POST'])
@setup_required
def login():
    """Login page."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('login.html')

        # Check if user is an admin
        if not is_admin_user(username):
            flash('Access denied. Admin privileges required.', 'error')
            return render_template('login.html')

        # Authenticate against RADIUS
        if authenticate_radius(username, password):
            session['username'] = username
            session.permanent = True
            next_url = request.args.get('next', url_for('main.index'))
            return redirect(next_url)
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')


@main_bp.route('/logout')
def logout():
    """Logout and clear session."""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('main.login'))


@main_bp.route('/users')
@setup_required
@login_required
def users():
    """Users list page."""
    manager = get_file_manager()
    users_list = manager.parse_users()
    return render_template('users.html', users=users_list)


@main_bp.route('/users/new', methods=['GET', 'POST'])
@setup_required
@login_required
def new_user():
    """Create new user form."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        comment = request.form.get('comment', '').strip()

        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('user_form.html', user=None, action='new')

        manager = get_file_manager()
        user = RadiusUser(
            username=username,
            password=password,
            comment=comment,
            disabled=False
        )

        if manager.add_user(user, get_current_user()):
            flash(f'User {username} created successfully', 'success')
            return redirect(url_for('main.users'))
        else:
            flash(f'User {username} already exists', 'error')

    return render_template('user_form.html', user=None, action='new')


@main_bp.route('/users/<username>/edit', methods=['GET', 'POST'])
@setup_required
@login_required
def edit_user(username):
    """Edit user form."""
    manager = get_file_manager()
    user = manager.get_user(username)

    if not user:
        flash(f'User {username} not found', 'error')
        return redirect(url_for('main.users'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        comment = request.form.get('comment', '').strip()

        # Only update password if provided
        if new_password:
            user.password = new_password
        user.comment = comment

        if manager.update_user(username, user, get_current_user()):
            flash(f'User {username} updated successfully', 'success')
            return redirect(url_for('main.users'))
        else:
            flash(f'Failed to update user {username}', 'error')

    return render_template('user_form.html', user=user, action='edit')


# ============== API Endpoints ==============

@api_bp.route('/users', methods=['GET'])
@login_required
def api_list_users():
    """List all users."""
    manager = get_file_manager()
    users = manager.parse_users()
    return jsonify({
        'users': [u.to_dict() for u in users],
        'total': len(users),
        'enabled': len([u for u in users if not u.disabled]),
        'disabled': len([u for u in users if u.disabled])
    })


@api_bp.route('/users/<username>', methods=['GET'])
@login_required
def api_get_user(username):
    """Get a specific user."""
    manager = get_file_manager()
    user = manager.get_user(username)

    if user:
        return jsonify(user.to_dict())
    return jsonify({'error': 'User not found'}), 404


@api_bp.route('/users', methods=['POST'])
@login_required
def api_create_user():
    """Create a new user."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')
    comment = data.get('comment', '').strip()

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    manager = get_file_manager()
    user = RadiusUser(
        username=username,
        password=password,
        comment=comment,
        disabled=False
    )

    if manager.add_user(user, get_current_user()):
        log_action('create', 'user', username, get_current_user(), {'comment': comment})
        return jsonify({'message': f'User {username} created', 'user': user.to_dict()}), 201
    return jsonify({'error': f'User {username} already exists'}), 409


@api_bp.route('/users/<username>', methods=['PUT'])
@login_required
def api_update_user(username):
    """Update an existing user."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    manager = get_file_manager()
    user = manager.get_user(username)

    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Update fields if provided
    if 'password' in data and data['password']:
        user.password = data['password']
    if 'comment' in data:
        user.comment = data['comment']
    if 'disabled' in data:
        user.disabled = data['disabled']

    if manager.update_user(username, user, get_current_user()):
        changes = []
        if 'password' in data and data['password']:
            changes.append('password')
        if 'comment' in data:
            changes.append('comment')
        log_action('update', 'user', username, get_current_user(), {'changed': changes})
        return jsonify({'message': f'User {username} updated', 'user': user.to_dict()})
    return jsonify({'error': 'Failed to update user'}), 500


@api_bp.route('/users/<username>', methods=['DELETE'])
@login_required
def api_delete_user(username):
    """Delete a user."""
    manager = get_file_manager()

    if manager.delete_user(username, get_current_user()):
        log_action('delete', 'user', username, get_current_user())
        return jsonify({'message': f'User {username} deleted'})
    return jsonify({'error': 'User not found'}), 404


@api_bp.route('/users/<username>/toggle', methods=['POST'])
@login_required
def api_toggle_user(username):
    """Toggle user enabled/disabled status."""
    manager = get_file_manager()
    new_status = manager.toggle_user(username, get_current_user())

    if new_status is not None:
        status_text = 'disabled' if new_status else 'enabled'
        log_action('toggle', 'user', username, get_current_user(), {'new_status': status_text})
        return jsonify({
            'message': f'User {username} {status_text}',
            'disabled': new_status
        })
    return jsonify({'error': 'User not found'}), 404


def docker_api_request(method, endpoint, body=None):
    """Make a request to Docker API via Unix socket using raw HTTP."""
    socket_path = '/var/run/docker.sock'
    if not os.path.exists(socket_path):
        raise FileNotFoundError("Docker socket not available")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5.0)  # 5 second timeout
    sock.connect(socket_path)

    # Build HTTP request - use Connection: close to avoid chunked issues
    body_bytes = json.dumps(body).encode() if body else b''
    request_line = f"{method} {endpoint} HTTP/1.0\r\n"  # HTTP/1.0 forces Connection: close
    headers = f"Host: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(body_bytes)}\r\nConnection: close\r\n\r\n"

    sock.sendall(request_line.encode() + headers.encode() + body_bytes)

    # Read response with timeout
    response = b''
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
    except socket.timeout:
        pass  # Timeout is expected when server closes connection

    sock.close()

    # Parse response
    response_str = response.decode('utf-8', errors='ignore')
    lines = response_str.split('\r\n')
    status_line = lines[0] if lines else ''
    status_code = int(status_line.split()[1]) if len(status_line.split()) > 1 else 0

    # Find body
    body_start = response_str.find('\r\n\r\n')
    body_content = response_str[body_start + 4:] if body_start != -1 else ''

    return {'status_code': status_code, 'body': body_content}


@api_bp.route('/reload', methods=['POST'])
@login_required
def api_reload_radius():
    """Reload FreeRADIUS configuration."""
    container_name = current_app.config['FREERADIUS_CONTAINER']

    try:
        # Send HUP signal to PID 1 in the container via Docker API
        exec_create = docker_api_request(
            'POST',
            f'/containers/{container_name}/exec',
            body={
                'Cmd': ['kill', '-HUP', '1'],
                'AttachStdout': True,
                'AttachStderr': True
            }
        )

        if exec_create['status_code'] != 201:
            return jsonify({'error': 'Failed to create exec instance', 'details': exec_create['body']}), 500

        # Parse exec ID from response
        try:
            exec_data = json.loads(exec_create['body'].strip().split('\n')[-1])
            exec_id = exec_data.get('Id')
        except:
            return jsonify({'error': 'Failed to parse exec response'}), 500

        # Start the exec instance
        exec_start = docker_api_request(
            'POST',
            f'/exec/{exec_id}/start',
            body={'Detach': True}
        )

        if exec_start['status_code'] == 200 or exec_start['status_code'] == 204:
            current_app.logger.info(f"FreeRADIUS reloaded by {get_current_user()}")
            return jsonify({'message': 'FreeRADIUS configuration reloaded'})
        else:
            return jsonify({'error': 'Failed to reload FreeRADIUS', 'details': exec_start['body']}), 500

    except FileNotFoundError:
        return jsonify({'error': 'Docker socket not available'}), 500
    except Exception as e:
        current_app.logger.error(f"Reload error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/status', methods=['GET'])
@login_required
def api_server_status():
    """Get FreeRADIUS server status."""
    container_name = current_app.config['FREERADIUS_CONTAINER']

    try:
        # Get container info
        response = docker_api_request('GET', f'/containers/{container_name}/json')

        if response['status_code'] == 200:
            try:
                container_info = json.loads(response['body'].strip())
                state = container_info.get('State', {})

                return jsonify({
                    'container': container_name,
                    'status': state.get('Status', 'unknown'),
                    'running': state.get('Running', False),
                    'started_at': state.get('StartedAt', ''),
                    'health': state.get('Health', {}).get('Status', 'unknown') if state.get('Health') else 'no healthcheck'
                })
            except:
                return jsonify({'status': 'unknown', 'error': 'Failed to parse container info'})
        else:
            return jsonify({'status': 'not found', 'running': False})

    except FileNotFoundError:
        return jsonify({'error': 'Docker socket not available'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/health', methods=['GET'])
def api_health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'})


# ============== Activity Parsing ==============

def parse_detail_record(lines):
    """Parse a single detail record from FreeRADIUS accounting."""
    record = {}
    for line in lines:
        line = line.strip()
        if line and '=' in line:
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"')
            record[key] = value
    return record


def parse_detail_file(filepath):
    """Parse a FreeRADIUS detail file and return list of records."""
    records = []
    if not os.path.exists(filepath):
        return records

    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Split by timestamp lines (e.g., "Fri Jan  2 00:13:52 2026")
        blocks = re.split(r'\n(?=[A-Z][a-z]{2} [A-Z][a-z]{2} +\d)', content)

        for block in blocks:
            if not block.strip():
                continue

            lines = block.strip().split('\n')
            if len(lines) < 2:
                continue

            # First line is timestamp
            timestamp_str = lines[0].strip()
            try:
                timestamp = datetime.strptime(timestamp_str, '%a %b %d %H:%M:%S %Y')
            except ValueError:
                timestamp = None

            record = parse_detail_record(lines[1:])
            if record:
                record['_timestamp'] = timestamp
                record['_timestamp_str'] = timestamp_str
                records.append(record)

    except Exception as e:
        current_app.logger.error(f"Error parsing detail file: {e}")

    return records


def get_activity_records(log_dir, limit=100):
    """Get activity records from FreeRADIUS accounting logs."""
    all_records = []

    if not os.path.exists(log_dir):
        return all_records

    # Find all detail files in radacct subdirectories
    for nas_dir in os.listdir(log_dir):
        nas_path = os.path.join(log_dir, nas_dir)
        if os.path.isdir(nas_path):
            for detail_file in sorted(os.listdir(nas_path), reverse=True):
                if detail_file.startswith('detail'):
                    filepath = os.path.join(nas_path, detail_file)
                    records = parse_detail_file(filepath)
                    all_records.extend(records)

                    if len(all_records) >= limit * 2:
                        break

    # Sort by timestamp descending and limit
    all_records.sort(key=lambda x: x.get('_timestamp') or datetime.min, reverse=True)
    return all_records[:limit]


# ============== Activity Views ==============

def get_active_sessions(records):
    """Calculate active sessions from records (Start without matching Stop)."""
    sessions = {}  # session_id -> record

    # Process in chronological order (oldest first) to track state
    for record in reversed(records):
        session_id = record.get('Acct-Unique-Session-Id') or record.get('Acct-Session-Id')
        status = record.get('Acct-Status-Type', '')

        if not session_id:
            continue

        if status == 'Start':
            sessions[session_id] = record
        elif status == 'Stop' and session_id in sessions:
            del sessions[session_id]

    return list(sessions.values())


@main_bp.route('/activity')
@setup_required
@login_required
def activity():
    """Activity log page."""
    log_dir = current_app.config.get('RADACCT_DIR', '/data/radacct')
    limit = request.args.get('limit', 100, type=int)
    user_filter = request.args.get('user', '').strip()
    show_active = request.args.get('active', '') == '1'

    # Get more records to calculate active sessions
    all_records = get_activity_records(log_dir, limit=500)

    # Calculate active sessions
    active_sessions = get_active_sessions(all_records)

    # Filter records for display
    if show_active:
        records = active_sessions
    else:
        records = all_records

    # Filter by user if specified
    if user_filter:
        records = [r for r in records if user_filter.lower() in r.get('User-Name', '').lower()]

    records = records[:limit]

    # Get unique users for filter dropdown
    all_users = set(r.get('User-Name', '') for r in all_records if r.get('User-Name'))

    return render_template('activity.html',
                           records=records,
                           users=sorted(all_users),
                           user_filter=user_filter,
                           active_count=len(active_sessions),
                           active_sessions=active_sessions,
                           show_active=show_active)


@api_bp.route('/activity', methods=['GET'])
@login_required
def api_activity():
    """Get activity records."""
    log_dir = current_app.config.get('RADACCT_DIR', '/data/radacct')
    limit = request.args.get('limit', 100, type=int)
    user_filter = request.args.get('user', '').strip()

    records = get_activity_records(log_dir, limit=limit * 2 if user_filter else limit)

    if user_filter:
        records = [r for r in records if user_filter.lower() in r.get('User-Name', '').lower()][:limit]

    # Convert timestamps to strings for JSON
    for record in records:
        if record.get('_timestamp'):
            record['_timestamp'] = record['_timestamp'].isoformat()

    return jsonify({
        'records': records,
        'total': len(records)
    })


# ============== RADIUS Clients Views ==============

@main_bp.route('/clients')
@setup_required
@login_required
def clients():
    """RADIUS clients list page."""
    manager = get_clients_manager()
    clients_list = manager.parse_clients()
    return render_template('clients.html', clients=clients_list)


@main_bp.route('/clients/new', methods=['GET', 'POST'])
@setup_required
@login_required
def new_client():
    """Create new RADIUS client form."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        ipaddr = request.form.get('ipaddr', '').strip()
        secret = request.form.get('secret', '').strip()
        shortname = request.form.get('shortname', '').strip()
        nastype = request.form.get('nastype', '').strip()
        comment = request.form.get('comment', '').strip()

        if not name or not ipaddr or not secret:
            flash('Name, IP address, and secret are required', 'error')
            return render_template('client_form.html', client=None, action='new')

        manager = get_clients_manager()
        client = RadiusClient(
            name=name,
            ipaddr=ipaddr,
            secret=secret,
            shortname=shortname,
            nastype=nastype,
            comment=comment
        )

        if manager.add_client(client, get_current_user()):
            flash(f'Client {name} created successfully', 'success')
            return redirect(url_for('main.clients'))
        else:
            flash(f'Client {name} already exists', 'error')

    return render_template('client_form.html', client=None, action='new')


@main_bp.route('/clients/<name>/edit', methods=['GET', 'POST'])
@setup_required
@login_required
def edit_client(name):
    """Edit RADIUS client form."""
    manager = get_clients_manager()
    client = manager.get_client(name)

    if not client:
        flash(f'Client {name} not found', 'error')
        return redirect(url_for('main.clients'))

    if request.method == 'POST':
        client.ipaddr = request.form.get('ipaddr', '').strip()
        new_secret = request.form.get('secret', '').strip()
        if new_secret:
            client.secret = new_secret
        client.shortname = request.form.get('shortname', '').strip()
        client.nastype = request.form.get('nastype', '').strip()
        client.comment = request.form.get('comment', '').strip()

        if manager.update_client(name, client, get_current_user()):
            flash(f'Client {name} updated successfully', 'success')
            return redirect(url_for('main.clients'))
        else:
            flash(f'Failed to update client {name}', 'error')

    return render_template('client_form.html', client=client, action='edit')


# ============== Active Users View ==============

@main_bp.route('/active')
@setup_required
@login_required
def active_users():
    """Active users page - shows currently connected users."""
    log_dir = current_app.config.get('RADACCT_DIR', '/data/radacct')
    all_records = get_activity_records(log_dir, limit=500)
    active_sessions = get_active_sessions(all_records)

    # Get client info for NAS identification
    clients_manager = get_clients_manager()
    clients = {c.ipaddr: c.name for c in clients_manager.parse_clients()}

    # Enrich active sessions with client names
    for session in active_sessions:
        nas_ip = session.get('NAS-IP-Address', '')
        session['_nas_name'] = clients.get(nas_ip, session.get('NAS-Identifier', nas_ip))

    return render_template('active_users.html',
                           sessions=active_sessions,
                           total=len(active_sessions))


# ============== Statistics View ==============

@main_bp.route('/statistics')
@setup_required
@login_required
def statistics():
    """Authentication statistics page."""
    log_dir = current_app.config.get('RADACCT_DIR', '/data/radacct')
    all_records = get_activity_records(log_dir, limit=1000)

    # Calculate statistics
    stats = {
        'total_records': len(all_records),
        'connections': len([r for r in all_records if r.get('Acct-Status-Type') == 'Start']),
        'disconnections': len([r for r in all_records if r.get('Acct-Status-Type') == 'Stop']),
        'active_sessions': len(get_active_sessions(all_records)),
        'unique_users': len(set(r.get('User-Name', '') for r in all_records if r.get('User-Name'))),
    }

    # User activity breakdown
    user_stats = {}
    for record in all_records:
        user = record.get('User-Name', '')
        if not user:
            continue
        if user not in user_stats:
            user_stats[user] = {'connections': 0, 'disconnections': 0, 'data_bytes': 0}

        if record.get('Acct-Status-Type') == 'Start':
            user_stats[user]['connections'] += 1
        elif record.get('Acct-Status-Type') == 'Stop':
            user_stats[user]['disconnections'] += 1
            # Add data usage
            input_bytes = int(record.get('Acct-Input-Octets', 0) or 0)
            output_bytes = int(record.get('Acct-Output-Octets', 0) or 0)
            input_giga = int(record.get('Acct-Input-Gigawords', 0) or 0) * 4294967296
            output_giga = int(record.get('Acct-Output-Gigawords', 0) or 0) * 4294967296
            user_stats[user]['data_bytes'] += input_bytes + output_bytes + input_giga + output_giga

    # NAS activity breakdown
    nas_stats = {}
    for record in all_records:
        nas = record.get('NAS-Identifier', record.get('NAS-IP-Address', 'Unknown'))
        if nas not in nas_stats:
            nas_stats[nas] = {'connections': 0}
        if record.get('Acct-Status-Type') == 'Start':
            nas_stats[nas]['connections'] += 1

    return render_template('statistics.html',
                           stats=stats,
                           user_stats=user_stats,
                           nas_stats=nas_stats)


# ============== Settings View ==============

@main_bp.route('/settings')
@setup_required
@login_required
def settings():
    """Settings page."""
    config = {
        'radius_server': current_app.config.get('RADIUS_SERVER', 'localhost'),
        'radius_port': current_app.config.get('RADIUS_PORT', 1812),
        'users_file': current_app.config.get('USERS_FILE', ''),
        'clients_file': current_app.config.get('CLIENTS_FILE', ''),
        'radacct_dir': current_app.config.get('RADACCT_DIR', ''),
        'freeradius_container': current_app.config.get('FREERADIUS_CONTAINER', 'freeradius'),
        'admin_group_prefix': current_app.config.get('ADMIN_GROUP_PREFIX', ''),
    }
    return render_template('settings.html', config=config)


# ============== RADIUS Clients API ==============

@api_bp.route('/clients', methods=['GET'])
@login_required
def api_list_clients():
    """List all RADIUS clients."""
    manager = get_clients_manager()
    clients = manager.parse_clients()
    return jsonify({
        'clients': [c.to_dict() for c in clients],
        'total': len(clients)
    })


@api_bp.route('/clients/<name>', methods=['GET'])
@login_required
def api_get_client(name):
    """Get a specific RADIUS client."""
    manager = get_clients_manager()
    client = manager.get_client(name)

    if client:
        return jsonify(client.to_dict())
    return jsonify({'error': 'Client not found'}), 404


@api_bp.route('/clients', methods=['POST'])
@login_required
def api_create_client():
    """Create a new RADIUS client."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    name = data.get('name', '').strip()
    ipaddr = data.get('ipaddr', '').strip()
    secret = data.get('secret', '').strip()

    if not name or not ipaddr or not secret:
        return jsonify({'error': 'Name, ipaddr, and secret are required'}), 400

    manager = get_clients_manager()
    client = RadiusClient(
        name=name,
        ipaddr=ipaddr,
        secret=secret,
        shortname=data.get('shortname', '').strip(),
        nastype=data.get('nastype', '').strip(),
        comment=data.get('comment', '').strip()
    )

    if manager.add_client(client, get_current_user()):
        log_action('create', 'client', name, get_current_user(), {'ipaddr': ipaddr})
        return jsonify({'message': f'Client {name} created', 'client': client.to_dict()}), 201
    return jsonify({'error': f'Client {name} already exists'}), 409


@api_bp.route('/clients/<name>', methods=['PUT'])
@login_required
def api_update_client(name):
    """Update an existing RADIUS client."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    manager = get_clients_manager()
    client = manager.get_client(name)

    if not client:
        return jsonify({'error': 'Client not found'}), 404

    if 'ipaddr' in data:
        client.ipaddr = data['ipaddr']
    if 'secret' in data and data['secret']:
        client.secret = data['secret']
    if 'shortname' in data:
        client.shortname = data['shortname']
    if 'nastype' in data:
        client.nastype = data['nastype']
    if 'comment' in data:
        client.comment = data['comment']

    if manager.update_client(name, client, get_current_user()):
        changes = [k for k in ['ipaddr', 'secret', 'shortname', 'nastype', 'comment'] if k in data]
        log_action('update', 'client', name, get_current_user(), {'changed': changes})
        return jsonify({'message': f'Client {name} updated', 'client': client.to_dict()})
    return jsonify({'error': 'Failed to update client'}), 500


@api_bp.route('/clients/<name>', methods=['DELETE'])
@login_required
def api_delete_client(name):
    """Delete a RADIUS client."""
    manager = get_clients_manager()

    if manager.delete_client(name, get_current_user()):
        log_action('delete', 'client', name, get_current_user())
        return jsonify({'message': f'Client {name} deleted'})
    return jsonify({'error': 'Client not found'}), 404


# ============== Session Management API ==============

@api_bp.route('/sessions/<session_id>/disconnect', methods=['POST'])
@login_required
def api_disconnect_session(session_id):
    """Disconnect an active session (send CoA Disconnect-Request)."""
    # This would require sending a RADIUS Disconnect-Request to the NAS
    # For now, return a placeholder response
    # TODO: Implement actual RADIUS CoA/Disconnect
    return jsonify({
        'message': 'Disconnect request sent',
        'session_id': session_id,
        'note': 'CoA not yet implemented - requires RADIUS Disconnect support on NAS'
    })


@api_bp.route('/active', methods=['GET'])
@login_required
def api_active_sessions():
    """Get currently active sessions."""
    log_dir = current_app.config.get('RADACCT_DIR', '/data/radacct')
    all_records = get_activity_records(log_dir, limit=500)
    active_sessions = get_active_sessions(all_records)

    # Convert timestamps for JSON
    for session in active_sessions:
        if session.get('_timestamp'):
            session['_timestamp'] = session['_timestamp'].isoformat()

    return jsonify({
        'sessions': active_sessions,
        'total': len(active_sessions)
    })


# ============== Server-Sent Events ==============

@api_bp.route('/events')
@login_required
def sse_events():
    """Server-Sent Events endpoint for real-time updates."""
    import time

    def generate():
        log_dir = current_app.config.get('RADACCT_DIR', '/data/radacct')
        last_sessions = {}
        last_activity_count = 0

        while True:
            try:
                # Get current sessions
                all_records = get_activity_records(log_dir, limit=500)
                current_sessions = get_active_sessions(all_records)

                # Build session map
                current_map = {}
                for s in current_sessions:
                    sid = s.get('Acct-Unique-Session-Id') or s.get('Acct-Session-Id')
                    if sid:
                        current_map[sid] = s

                # Check for new sessions
                for sid, session in current_map.items():
                    if sid not in last_sessions:
                        # Convert timestamp for JSON
                        session_data = dict(session)
                        if session_data.get('_timestamp'):
                            session_data['_timestamp'] = session_data['_timestamp'].isoformat()
                        session_data['id'] = sid
                        session_data['username'] = session.get('User-Name', 'Unknown')
                        yield f"event: session_start\ndata: {json.dumps(session_data)}\n\n"

                # Check for ended sessions
                for sid in list(last_sessions.keys()):
                    if sid not in current_map:
                        yield f"event: session_stop\ndata: {json.dumps({'id': sid})}\n\n"

                # Check for new activity
                if len(all_records) != last_activity_count:
                    yield f"event: activity_update\ndata: {json.dumps({'count': len(all_records)})}\n\n"
                    last_activity_count = len(all_records)

                last_sessions = current_map

            except Exception as e:
                current_app.logger.error(f"SSE error: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

            time.sleep(5)  # Check every 5 seconds

    from flask import Response
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


# ============== Audit Log API ==============

@api_bp.route('/audit', methods=['GET'])
@login_required
def api_audit_log():
    """Get audit log entries."""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    target_type = request.args.get('type')
    action = request.args.get('action')

    entries = get_audit_log(
        limit=min(limit, 200),  # Cap at 200
        offset=offset,
        target_type=target_type,
        action=action
    )

    return jsonify({
        'entries': entries,
        'count': len(entries),
        'limit': limit,
        'offset': offset
    })
