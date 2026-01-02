# FreeRADIUS Web Manager

A lightweight web interface for managing FreeRADIUS users via flat files. No database required.

## Features

- **First-Run Setup** - Create your first admin account through the web interface
- **RADIUS Authentication** - Admin login via RADIUS authentication
- **User Management** - Add, edit, enable/disable, delete users
- **Flat File Storage** - Works directly with FreeRADIUS users file (no database)
- **Lightweight** - Single container, minimal dependencies (~50MB)
- **Secure** - HTTPS ready, RADIUS-authenticated access

## Quick Start

### Using Docker Compose

```bash
# Clone the repository
git clone https://github.com/DemonAngel44/freeradius-web-manager.git
cd freeradius-web-manager

# Configure environment
cp .env.example .env
# Edit .env with your RADIUS server settings

# Start the container
docker-compose up -d
```

### First-Run Setup

On first access, you'll be prompted to create an admin account:

1. Navigate to `http://your-server:5000`
2. Enter a username and password for your admin account
3. This account is created in the FreeRADIUS users file
4. Log in with the credentials you just created

After setup, all authentication goes through RADIUS.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key for sessions | (required for production) |
| `RADIUS_SERVER` | FreeRADIUS server IP | `localhost` |
| `RADIUS_PORT` | RADIUS authentication port | `1812` |
| `RADIUS_SECRET` | RADIUS shared secret | (required) |
| `USERS_FILE` | Path to FreeRADIUS users file | `/etc/raddb/mods-config/files/authorize` |
| `ADMIN_GROUP_PREFIX` | Username prefix for admin access (optional) | (empty = any user) |
| `FREERADIUS_CONTAINER` | Docker container name for reload | `freeradius` |
| `SETUP_COMPLETE_FILE` | Path to setup marker file | `/data/.setup_complete` |

## Configuration

### FreeRADIUS Users File

The application manages the standard FreeRADIUS users file format:

```
# Comment for user
username Cleartext-Password := "password"
    Framed-Protocol = PPP,
    Service-Type = Framed-User
```

### Admin Access Restriction (Optional)

By default, any user who can authenticate via RADIUS can access the management interface. To restrict access to specific users, set `ADMIN_GROUP_PREFIX`:

```bash
# Only users starting with "admin-" can log in
ADMIN_GROUP_PREFIX=admin-
```

### Docker Volume Setup

The container needs access to your FreeRADIUS configuration:

```yaml
volumes:
  radius_config:
    external: true
    name: your_freeradius_config_volume
```

## API Endpoints

All API endpoints require authentication.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/users` | List all users |
| GET | `/api/users/<username>` | Get user details |
| POST | `/api/users` | Create new user |
| PUT | `/api/users/<username>` | Update user |
| DELETE | `/api/users/<username>` | Delete user |
| POST | `/api/users/<username>/toggle` | Enable/disable user |
| POST | `/api/reload` | Reload FreeRADIUS config |
| GET | `/api/health` | Health check |

## Development

### Local Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run development server
python run.py
```

### Project Structure

```
freeradius-web-manager/
├── app/
│   ├── __init__.py       # Flask app factory
│   ├── auth.py           # RADIUS authentication
│   ├── radius_file.py    # Users file parser/writer
│   ├── routes.py         # API and view routes
│   └── templates/        # HTML templates
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── config.py
└── run.py
```

## Security Considerations

- Always run behind HTTPS in production (use nginx-proxy-manager or similar)
- Use a strong `SECRET_KEY` in production
- RADIUS shared secret should be strong and kept secure
- Consider using `ADMIN_GROUP_PREFIX` to limit admin access
- All changes are logged with timestamp and admin username
- The first-run setup can only be used once

## Resetting Setup

To reset the first-run setup:

```bash
# Remove the setup marker file
docker exec freeradius-web-manager rm /data/.setup_complete

# Optionally clear all users
docker exec freeradius-web-manager rm /data/authorize
```

## License

MIT License - See [LICENSE](LICENSE) for details.
