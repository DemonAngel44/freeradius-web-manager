# FreeRADIUS Web Manager

A lightweight web interface for managing FreeRADIUS users via flat files. No database required.

## Features

- **RADIUS Authentication** - Admin login via existing RADIUS accounts
- **User Management** - Add, edit, enable/disable, delete users
- **Flat File Storage** - Works directly with FreeRADIUS users file (no database migration)
- **Lightweight** - Single container, minimal dependencies (~50MB)
- **Secure** - HTTPS ready, RADIUS-authenticated access

## Quick Start

### Using Docker Compose

```bash
# Clone the repository
git clone https://github.com/yourusername/freeradius-web-manager.git
cd freeradius-web-manager

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start the container
docker-compose up -d
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key for sessions | (required) |
| `RADIUS_SERVER` | FreeRADIUS server IP | `localhost` |
| `RADIUS_PORT` | RADIUS authentication port | `1812` |
| `RADIUS_SECRET` | RADIUS shared secret | (required) |
| `USERS_FILE` | Path to FreeRADIUS users file | `/etc/raddb/mods-config/files/authorize` |
| `ADMIN_GROUP_PREFIX` | Username prefix for admin access | `ADM-` |
| `FREERADIUS_CONTAINER` | Docker container name for reload | `freeradius` |

## Configuration

### FreeRADIUS Users File

The application manages the standard FreeRADIUS users file format:

```
# Comment for user
username Cleartext-Password := "password"
    Framed-Protocol = PPP,
    Service-Type = Framed-User
```

### Admin Access

Only users with usernames starting with `ADMIN_GROUP_PREFIX` (default: `ADM-`) can log into the management interface. These users authenticate against the RADIUS server itself.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/users` | List all users |
| GET | `/api/users/<username>` | Get user details |
| POST | `/api/users` | Create new user |
| PUT | `/api/users/<username>` | Update user |
| DELETE | `/api/users/<username>` | Delete user |
| POST | `/api/users/<username>/toggle` | Enable/disable user |
| POST | `/api/reload` | Reload FreeRADIUS config |

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

- Always run behind HTTPS (use nginx-proxy-manager or similar)
- RADIUS shared secret should be strong and kept secure
- Only ADM-* users can access the management interface
- All changes are logged with timestamp and admin username

## License

MIT License - See [LICENSE](LICENSE) for details.
