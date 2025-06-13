#!/bin/bash
# Script for launching interactive shell with activated virtual environment

if [ ! -d "venv" ]; then
    make activate
fi

echo "🚀 Starting interactive shell with activated virtual environment..."
echo "📝 Available commands:"
echo "   ./test_connection.py"
echo "   ./atlassian-user-suspend-cli.py show-cloud-users"
echo "   ./atlassian-user-suspend-cli.py search user@example.com"
echo "   ./atlassian-user-suspend-cli.py suspend --dry-run"
echo ""
echo "💡 Type 'exit' to quit"
echo ""

# Activate virtual environment and start new shell
source venv/bin/activate && exec $SHELL
