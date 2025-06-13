# Detailed Usage Guide - Atlassian User Suspend CLI

## Getting Started

### Step 1: Setup Environment
```bash
make setup          # Create .env file from template
make shell          # Create virtual environment, install dependencies and activate venv
# Alternative: make activate + run source manually
```

### Step 2: Get Credentials

**Organization ID:**
1. Go to [Atlassian Admin Console](https://admin.atlassian.com)
2. Look at URL: `https://admin.atlassian.com/o/YOUR-ORG-ID/overview`
3. Copy `YOUR-ORG-ID` from the URL

**API Key:**
1. In Atlassian Admin → **Settings** → **API keys**
2. Click **Create API key**
3. **⚠️ IMPORTANT**: Do **NOT** select any scope! Leave scopes empty
4. Copy and save the API key securely

**Configure .env file:**
```bash
vim .env  # Add your credentials:
# ORG_ID=your-organization-id
# API_KEY=your-api-key
```

### Step 3: Get Users CSV
1. In Atlassian Admin → **Directory** → **Users**
2. Click **Export users** (top right)
3. Choose **CSV format**
4. Download and save as `users.csv` in project directory
5. Optionally edit CSV to include only users you want to process

### Step 4: Test Connection
```bash
make run-test       # Test API connection and permissions
```

## CSV File Format

### Required Columns
- `email` - User email address (required)

### Optional Columns
The tool automatically detects these columns with flexible naming:

**User ID** (speeds up processing):
- `User id`, `user_id`, `account_id`, `Account ID`
- Format: `712020:account-id` or just `account-id`

**User Name** (for display):
- `User name`, `user_name`, `name`, `Name`

**Status** (for filtering):
- `User status`, `user_status`, `status`, `Status`

### Example CSV
```csv
email,User id,User name,User status
john.doe@example.com,712020:abc123,John Doe,Active
jane.smith@example.com,,Jane Smith,Active
mike.wilson@example.com,712020:def456,Mike Wilson,Inactive
```

### Status Filtering Logic

**For `suspend` command:**
- ✅ Processes: `Active` users + empty status
- ❌ Skips: `Inactive`, `Suspended`, `Disabled` users

**For `restore` command:**
- ✅ Processes: `Inactive`, `Suspended`, `Disabled` users only
- ❌ Skips: `Active` users + empty status

**With `--all` flag:**
- Processes ALL users regardless of status

## Commands Reference

### Environment Setup Commands
```bash
make setup                 # Create .env file from template
make activate # or shell   # Create virtual environment and install dependencies
```

### Testing Commands
```bash
make test                  # Test API connection
make run-test              # Test API connection (in virtual environment)
```

### Running Commands (in virtual environment)
```bash
make run-show-users        # Show all users
make run-search EMAIL=user@example.com  # Search specific user
make run-suspend-dry       # Test suspend operation (dry-run)
```

### Maintenance Commands
```bash
make clean                 # Clean logs and cache files
make status                # Check project status
```

### Script Commands (need activated environment)
```bash
# View users
./atlassian-user-suspend-cli.py show-cloud-users
./atlassian-user-suspend-cli.py show-cloud-users --filter @company.com
./atlassian-user-suspend-cli.py search user@example.com

# Suspend operations
./atlassian-user-suspend-cli.py suspend --dry-run      # Safe testing
./atlassian-user-suspend-cli.py suspend --test         # First user only
./atlassian-user-suspend-cli.py suspend                # Real operation
./atlassian-user-suspend-cli.py suspend --all          # Ignore status
./atlassian-user-suspend-cli.py suspend --csv custom.csv

# Restore operations
./atlassian-user-suspend-cli.py restore --dry-run
./atlassian-user-suspend-cli.py restore --all
./atlassian-user-suspend-cli.py restore --csv suspended_users.csv

# Additional options
./atlassian-user-suspend-cli.py suspend --non-interactive --delay 1.0
```

## Common Workflows

### 1. Daily User Cleanup
```bash
# 1. View users needing suspension
make run-show-users                    # Show all users first

# 2. Create CSV with specific users
echo "email" > cleanup.csv
echo "user1@oldcompany.com" >> cleanup.csv
echo "user2@oldcompany.com" >> cleanup.csv

# 3. Test operation safely
make run-suspend-dry                   # OR use custom CSV:
# ./atlassian-user-suspend-cli.py suspend --csv cleanup.csv --dry-run

# 4. Execute if tests pass 
make shell                             # Automatically activates environment if needed
./atlassian-user-suspend-cli.py suspend --csv cleanup.csv --non-interactive
```

### 2. Emergency Restore
```bash
# 1. Identify suspended users
make run-show-users                    # Show all users and check statuses

# 2. Create restore CSV (extract suspended users)
# ... manual or script process

# 3. Restore quickly
make shell                             # Automatically activates environment if needed
./atlassian-user-suspend-cli.py restore --csv emergency_restore.csv --all --non-interactive
```

### 3. Bulk Processing
```bash
# For large operations
./atlassian-user-suspend-cli.py suspend --non-interactive --delay 1.0

# For very large organizations
./atlassian-user-suspend-cli.py suspend --delay 2.0 --non-interactive
```

## Safety Features

### Dry-Run Mode
```bash
./atlassian-user-suspend-cli.py suspend --dry-run
```
- Tests all operations without making changes
- Shows exactly what would happen
- Validates CSV data and permissions

### Test Mode
```bash
./atlassian-user-suspend-cli.py suspend --test
```
- Processes only first user from CSV
- Useful for testing with real data
- Combines well with dry-run: `--test --dry-run`

### Resume Operations
If operation is interrupted:
1. Script saves progress automatically
2. On restart, offers to continue from last processed user
3. Choose 'yes' to resume or 'no' to start over

## Troubleshooting

### Connection Issues
```bash
# Test basic connection
make test                              # Simple connection test
make run-test                          # Full test in virtual environment  

# Debug mode
DEBUG=true make run-test

# Check specific user
make run-search EMAIL=problematic@example.com

# Verify organization access
make run-show-users                    # Show all users to verify access
```

### Common Errors

**HTTP 401 - Authentication Error:**
- Check API key validity in .env file
- Ensure key is not expired

**HTTP 403 - Insufficient Permissions:**
- Verify Organization Admin rights
- Ensure API key created by admin user

**HTTP 404 - User Not Found:**
- Check account_id format in CSV
- Verify user belongs to your organization
- Use `make run-show-users` to get correct account_id

**Rate Limit Exceeded:**
- Increase delay: `--delay 2.0`
- Script automatically handles with delays

### Performance Tuning
- Use account_id in CSV to skip user lookups
- Adjust delay based on your organization size
- Process in smaller batches for very large operations

## Automation

### Cron Job Example
```bash
# Weekly cleanup (Monday 9 AM)
0 9 * * 1 cd /path/to/script && ./atlassian-user-suspend-cli.py suspend --csv weekly_departures.csv --non-interactive
```

### Batch Processing Script
```bash
#!/bin/bash
# Process multiple departments
for dept in marketing sales support; do
    echo "Processing $dept..."
    ./atlassian-user-suspend-cli.py suspend --csv ${dept}_departures.csv --non-interactive --delay 1.0
    sleep 10
done
```

## Best Practices

### Safety First
1. **Always test with `--dry-run` first**
2. **Use `--test` for single user validation**
3. **Keep backups of user lists**
4. **Review logs after operations**

### Efficiency
1. **Include account_id in CSV when possible**
2. **Process during off-peak hours**
3. **Use appropriate delays for your organization size**
4. **Split large operations into batches**

### Security
1. **Protect .env file (never commit to git)**
2. **Rotate API keys regularly**
3. **Use minimum required permissions**
4. **Monitor operation logs**

All operations are logged in `logs/` directory with timestamps and success/failure status for each user.