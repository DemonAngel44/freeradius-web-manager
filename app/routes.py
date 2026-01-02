"""
Flask routes for web views and API endpoints.
"""

import subprocess
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app.auth import (
    authenticate_radius, is_admin_user, login_required, get_current_user,
    is_setup_complete, mark_setup_complete, setup_required
)
from app.radius_file import RadiusFileManager, RadiusUser

main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)


def get_file_manager():
    """Get the RadiusFileManager instance."""
    return RadiusFileManager(current_app.config['USERS_FILE'])


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
    """Main dashboard - redirect to users list."""
    return redirect(url_for('main.users'))


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
        return jsonify({'message': f'User {username} updated', 'user': user.to_dict()})
    return jsonify({'error': 'Failed to update user'}), 500


@api_bp.route('/users/<username>', methods=['DELETE'])
@login_required
def api_delete_user(username):
    """Delete a user."""
    manager = get_file_manager()

    if manager.delete_user(username, get_current_user()):
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
        return jsonify({
            'message': f'User {username} {status_text}',
            'disabled': new_status
        })
    return jsonify({'error': 'User not found'}), 404


@api_bp.route('/reload', methods=['POST'])
@login_required
def api_reload_radius():
    """Reload FreeRADIUS configuration."""
    container_name = current_app.config['FREERADIUS_CONTAINER']

    try:
        # Try to reload FreeRADIUS via docker exec
        result = subprocess.run(
            ['docker', 'exec', container_name, 'kill', '-HUP', '1'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            current_app.logger.info(f"FreeRADIUS reloaded by {get_current_user()}")
            return jsonify({'message': 'FreeRADIUS configuration reloaded'})
        else:
            current_app.logger.error(f"FreeRADIUS reload failed: {result.stderr}")
            return jsonify({'error': 'Failed to reload FreeRADIUS', 'details': result.stderr}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Reload command timed out'}), 500
    except FileNotFoundError:
        return jsonify({'error': 'Docker not available'}), 500
    except Exception as e:
        current_app.logger.error(f"Reload error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/health', methods=['GET'])
def api_health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'})
