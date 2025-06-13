# Atlassian User Suspend CLI

CLI tool for bulk suspend/restore operations on cloud Atlassian (Jira/Confluence) users via API.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Atlassian Organization Admin rights
- API key (create without scope in [Atlassian Admin](https://admin.atlassian.com) → Settings → API keys)

### Setup & First Run
```bash
# 1. Clone and setup
git clone https://github.com/sumlin/atlassian-user-suspend-cli.git
cd atlassian-user-suspend-cli

# 2. Configure credentials
make setup
vim .env  # Add your ORG_ID and API_KEY

# 3. Get users CSV file
# Go to Atlassian Admin → Directory → Users → Export users (CSV format)
# Save as users.csv in project directory

# 4. Test and run (auto-creates environment if needed)
make run-test                         # Test API connection
make run-show-users                   # View all users
make run-suspend-dry                  # Test suspend (safe)

# Or start interactive shell (auto-creates environment if needed)
make shell
```

> 📖 **Need more details?** See [USAGE.md](USAGE.md) for comprehensive guide.

## 📦 Installation

**Quick setup with Makefile**
```bash
make setup     # Creates .env from template
make shell     # Creates venv, installs dependencies and activate venv
```

**Manual installation** 
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# OR: venv\Scripts\activate.bat  # Windows
pip install -r requirements.txt
cp .env-example .env
```

## 🔧 Basic Usage

### Testing & Viewing
```bash
make status                # Check project status
make test                  # Test API connection
make run-test              # Test API connection (in virtual environment)
make run-show-users        # Show all users (in virtual environment)
make run-search EMAIL=user@example.com    # Search specific user
```

### Safe Operations
```bash
make run-suspend-dry       # Test suspend operation (dry-run, safe)

# Or direct script usage (in activated environment):
./atlassian-user-suspend-cli.py suspend --dry-run    # Test suspend
./atlassian-user-suspend-cli.py restore --test       # Test restore
```

### Production Operations
```bash
# Use make shell (automatically activates environment):
make shell
./atlassian-user-suspend-cli.py suspend --non-interactive
./atlassian-user-suspend-cli.py restore --csv departed_users.csv
```

## 📁 Getting Users CSV File

**From Atlassian Admin Console:**
1. Go to [Atlassian Admin](https://admin.atlassian.com) → **Directory** → **Users**
2. Click **Export users** button (top right)
3. Choose **CSV format**
4. Download and save as `users.csv` in project directory
5. Optionally edit CSV to include only users you want to process

**CSV Format:**
```csv
email,User id,User name,User status
john.doe@company.com,712020:abc123,John Doe,Active
jane.smith@company.com,,Jane Smith,Active
```
- **email** (required) - User email address
- **User id** (optional) - Account ID for faster processing
- **User name** (optional) - Display name
- **User status** (optional) - Active/Inactive for filtering

The order and presence of other columns are not important - there is no need to delete the other columns.

## 🔑 Getting Credentials

1. **Organization ID**: Get from Atlassian Admin URL: `https://admin.atlassian.com/o/YOUR-ORG-ID/overview`
2. **API Key**: Create in [Atlassian Admin](https://admin.atlassian.com) → Settings → API keys (⚠️ **without scope!**)

## ⚡ Quick Examples

```bash
# Emergency: suspend all users from old domain
make run-show-users --filter @oldcompany.com > users.txt

# Create CSV from output or download it from Atlassian Web UI, then:
make shell
./atlassian-user-suspend-cli.py suspend --csv users.csv --dry-run

# Automated bulk processing
./atlassian-user-suspend-cli.py suspend --non-interactive --delay 1.0

# Restore previously suspended users  
./atlassian-user-suspend-cli.py restore --all --non-interactive
```

## 📚 Documentation

- **[USAGE.md](USAGE.md)** - Complete usage guide with examples
- **[.env-example](.env-example)** - Configuration template
- **[users.csv-example](users.csv-example)** - CSV format example

## 🔒 Security Notes

- Never commit `.env` file (contains API keys)
- Always use `--dry-run` first for safety
- API keys are automatically masked in logs
- Store keys in password manager

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

---

> 💡 **Pro tip**: Start with `make run-suspend-dry` for safe experimentation!