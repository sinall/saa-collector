#!/bin/bash
# Collector Backend Development Server Startup Script

# Get the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate pyenv environment
if command -v pyenv >/dev/null 2>&1; then
    if pyenv versions | grep -q "collector-env"; then
        echo "Activating pyenv environment: collector-env (Python 3.12.3)..."
        eval "$(pyenv init -)"
        pyenv activate collector-env
    else
        echo "Warning: pyenv environment 'collector-env' not found."
        echo "Please create it first: pyenv install 3.12.3 && pyenv virtual 3.12.3 collector-env"
        exit 1
    fi
else
    echo "Error: pyenv not found. Please install pyenv first."
    echo "Visit: https://github.com/pyenv/pyenv#installation"
    exit 1
fi

# Load environment variables
if [ -f ".envs/development.env" ]; then
    echo "Loading environment variables from .envs/development.env..."
    set -a
    source .envs/development.env
    set +a
else
    echo "Error: .envs/development.env file not found."
    echo "Please create it first."
    exit 1
fi

# Set Django settings module
export DJANGO_SETTINGS_MODULE=config.settings.development

# Start Django development server
echo "Starting Django development server on http://127.0.0.1:8000"
echo "Press Ctrl+C to stop the server"
echo ""

python manage.py runserver
