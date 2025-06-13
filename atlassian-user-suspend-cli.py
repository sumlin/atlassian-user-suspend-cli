#!/usr/bin/env python3
"""Atlassian User Manager - Managing users in cloud Jira/Confluence"""

import os
import sys
import json
import time
import csv
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol, TypeAlias
from dataclasses import dataclass, asdict, field
from collections import Counter
from contextlib import contextmanager

import click
import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import box
from rich.progress import Progress, TaskID

load_dotenv()

# Configure logging
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f'user_manager_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Type aliases for Python 3.11
OperationResult: TypeAlias = tuple[bool, str, str | None, str | None]
ProcessingResults: TypeAlias = list['ProcessingResult']

# CSV column mappings from documentation
OPTIONAL_CSV_COLUMNS = {
    'user_id': ['User id', 'user_id', 'account_id', 'Account ID'],
    'user_name': ['User name', 'user_name', 'name', 'Name'],
    'user_status': ['User status', 'user_status', 'status', 'Status']
}


@dataclass
class Config:
    """Application configuration from environment"""
    api_base_url: str = field(
        default_factory=lambda: os.getenv("API_BASE_URL", "https://api.atlassian.com")
    )
    org_id: str = field(default_factory=lambda: os.getenv("ORG_ID", ""))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", ""))
    timeout: int = field(default_factory=lambda: int(os.getenv("TIMEOUT", "30")))
    default_csv: str = field(default_factory=lambda: os.getenv("DEFAULT_CSV_FILE", "users.csv"))
    default_delay: float = field(default_factory=lambda: float(os.getenv("DEFAULT_DELAY", "0.5")))
    logs_dir: str = field(default_factory=lambda: os.getenv("LOGS_DIR", "logs"))
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "3")))
    retry_delay: float = field(default_factory=lambda: float(os.getenv("RETRY_DELAY", "1.0")))
    non_interactive: bool = field(
        default_factory=lambda: os.getenv("NON_INTERACTIVE", "false").lower() == "true"
    )
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")


config = Config()



def find_csv_column(headers: list[str], possible_names: list[str]) -> str | None:
    """Find column by possible names (case insensitive)"""
    headers_lower = [col.lower().strip() for col in headers]

    for name in possible_names:
        name_lower = name.lower().strip()
        if name_lower in headers_lower:
            # Return original column name
            original_index = headers_lower.index(name_lower)
            return headers[original_index]
    return None


@dataclass
class Directory:
    """Directory model"""
    directory_id: str
    name: str


@dataclass
class User:
    """User model"""
    email: str
    account_id: str | None = None
    name: str | None = None
    status: str | None = None
    account_type: str | None = None
    directory_id: str | None = None

    def to_row(self) -> list[str]:
        """Format for table display"""
        if self.status == "active":
            status_display = "[green]active[/green]"
        elif self.status == "suspended":
            status_display = "[yellow]suspended[/yellow]"
        elif self.status == "deactivated":
            status_display = "[red]deactivated[/red]"
        elif self.status is None or self.status == "":
            status_display = "[dim]unknown[/dim]"
        else:
            status_display = f"[red]{self.status}[/red]"

        account_display = self.account_id or "—"

        dir_display = "—"
        if self.directory_id:
            dir_display = self.directory_id[:8] + "..."

        return [
            self.email,
            self.name or "—",
            account_display,
            status_display,
            self.account_type or "—",
            dir_display
        ]


@dataclass
class ProcessingResult:
    """Operation result"""
    email: str
    account_id: str | None
    success: bool
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    lifecycle_action: str | None = None
    access_action: str | None = None
    user_obj: Optional['User'] = None


class AtlassianAPIError(Exception):
    pass


class AuthenticationError(AtlassianAPIError):
    pass


class RateLimitError(AtlassianAPIError):
    pass


class UserRepositoryProtocol(Protocol):
    """Protocol for user repository"""

    def get_directories(self) -> list[Directory]:
        """Get organization directories"""
        ...

    def get_all_users(self) -> list[User]:
        """Get all organization users"""
        ...

    def find_user(self, email: str) -> User | None:
        """Find user by email"""
        ...

    def update_user_status(self, account_id: str, operation: str, message: str) -> OperationResult:
        """Update user status"""
        ...


class AtlassianUserRepository:
    """Atlassian API implementation"""

    STATUS_CODES = {
        204: (True, "successful"),
        400: (False, "invalid request"),
        401: (False, "authentication error"),
        403: (False, "insufficient permissions"),
        404: (False, "not found"),
        429: (False, "RATE_LIMIT")
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with retries"""
        last_error = None
        for attempt in range(config.max_retries):
            try:
                response = self.session.request(
                    method, url, timeout=config.timeout, **kwargs
                )
                if config.debug:
                    logger.debug(f"{method} {url} -> {response.status_code}")
                    if response.text:
                        logger.debug(f"Response: {response.text[:200]}...")
                if response.status_code == 429 and attempt < config.max_retries - 1:
                    time.sleep(config.retry_delay * (attempt + 1))
                    continue
                return response
            except requests.RequestException as e:
                last_error = e
                if attempt < config.max_retries - 1:
                    time.sleep(config.retry_delay)
        raise AtlassianAPIError(
            f"Network error after {config.max_retries} attempts: {last_error}"
        )

    def verify_credentials(self) -> bool:
        """Verify API access"""
        response = self._request(
            "GET",
            f"{config.api_base_url}/admin/v2/orgs/{config.org_id}/directories"
        )
        if response.status_code == 401:
            raise AuthenticationError("Invalid API key")
        elif response.status_code == 403:
            raise AuthenticationError(
                "Insufficient permissions. Organization Admin rights required"
            )
        elif response.status_code == 404:
            raise AuthenticationError(f"Organization {config.org_id} not found")
        elif response.status_code == 200:
            return True
        else:
            raise AtlassianAPIError(f"HTTP {response.status_code}: {response.text}")

    def get_directories(self) -> list[Directory]:
        """Get organization directories"""
        response = self._request(
            "GET",
            f"{config.api_base_url}/admin/v2/orgs/{config.org_id}/directories"
        )
        if response.status_code != 200:
            raise AtlassianAPIError(
                f"Failed to get directories: HTTP {response.status_code}"
            )

        directories = []
        for dir_data in response.json().get("data", []):
            directories.append(Directory(
                directory_id=dir_data.get("directoryId"),
                name=dir_data.get("name")
            ))
        return directories

    def get_all_users(self) -> list[User]:
        """Get all organization users"""
        users = []
        directories = self.get_directories()

        if not directories:
            raise AtlassianAPIError("No directories found in organization")

        for directory in directories:
            dir_id = directory.directory_id
            cursor = None
            page = 1

            while True:
                params = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor

                resp = self._request(
                    "GET",
                    f"{config.api_base_url}/admin/v2/orgs/{config.org_id}/directories/{dir_id}/users",
                    params=params
                )

                if resp.status_code != 200:
                    raise AtlassianAPIError(f"Failed to get users: HTTP {resp.status_code}")

                data = resp.json()
                page_users = data.get("data", [])

                if config.debug:
                    logger.debug(f"Directory {dir_id}: page {page}, got {len(page_users)} users")

                for user_data in page_users:
                    users.append(User(
                        email=user_data.get("email", ""),
                        account_id=user_data.get("accountId"),
                        name=user_data.get("name"),
                        status=user_data.get("status"),
                        account_type=user_data.get("accountType"),
                        directory_id=dir_id
                    ))

                # Check for next page - API v2 provides cursor in links.next
                links = data.get("links", {})
                if links and links.get("next"):
                    cursor = links.get("next")
                    page += 1
                    time.sleep(0.1)
                else:
                    if config.debug:
                        logger.debug(f"Directory {dir_id}: no more pages, total {len(users)} users")
                    break

        return users

    def find_user(self, email: str) -> User | None:
        """Find user by email"""
        directories = self.get_directories()

        for directory in directories:
            dir_id = directory.directory_id
            cursor = None

            while True:
                params = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor

                resp = self._request(
                    "GET",
                    f"{config.api_base_url}/admin/v2/orgs/{config.org_id}/directories/{dir_id}/users",
                    params=params
                )

                if resp.status_code != 200:
                    continue

                data = resp.json()

                for user_data in data.get("data", []):
                    if user_data.get("email", "").lower() == email.lower():
                        return User(
                            email=user_data.get("email", ""),
                            account_id=user_data.get("accountId"),
                            name=user_data.get("name"),
                            status=user_data.get("status"),
                            account_type=user_data.get("accountType"),
                            directory_id=dir_id
                        )

                # Check for next page
                links = data.get("links", {})
                if links and links.get("next"):
                    cursor = links.get("next")
                else:
                    break

        return None

    def update_user_status(
            self, account_id: str, operation: str, message: str = "API operation"
    ) -> OperationResult:
        """Update user status (suspend/restore)"""
        ops = {
            'suspend': {
                'lifecycle': f"{config.api_base_url}/users/{account_id}/manage/lifecycle/disable",
                'access': (
                    f"{config.api_base_url}/admin/v1/orgs/{config.org_id}/directory/users/"
                    f"{account_id}/suspend-access"
                ),
                'actions': ('disabled', 'suspended')
            },
            'restore': {
                'lifecycle': f"{config.api_base_url}/users/{account_id}/manage/lifecycle/enable",
                'access': (
                    f"{config.api_base_url}/admin/v1/orgs/{config.org_id}/directory/users/"
                    f"{account_id}/restore-access"
                ),
                'actions': ('enabled', 'restored')
            }
        }

        op_config = ops[operation]
        lifecycle_action = access_action = None
        messages = []

        # Lifecycle operation
        try:
            resp = self._request("POST", op_config['lifecycle'], json={"message": message})
            success, msg = self.STATUS_CODES.get(
                resp.status_code, (False, f"HTTP {resp.status_code}")
            )
            if msg == "RATE_LIMIT":
                raise RateLimitError("Rate limit exceeded")
            if success:
                lifecycle_action = op_config['actions'][0]
                messages.append(f"Lifecycle {lifecycle_action}")
            else:
                messages.append(f"Lifecycle: {msg}")
        except RateLimitError:
            raise
        except Exception as e:
            messages.append(f"Lifecycle error: {str(e)}")

        # Access operation
        try:
            resp = self._request("POST", op_config['access'])
            success, msg = self.STATUS_CODES.get(
                resp.status_code, (False, f"HTTP {resp.status_code}")
            )
            if msg == "RATE_LIMIT":
                raise RateLimitError("Rate limit exceeded")
            if success:
                access_action = op_config['actions'][1]
                messages.append(f"Access {access_action}")
            else:
                messages.append(f"Access: {msg}")
        except RateLimitError:
            raise
        except Exception as e:
            messages.append(f"Access error: {str(e)}")

        overall_success = bool(lifecycle_action or access_action)
        return overall_success, " | ".join(messages), lifecycle_action, access_action


class OutputFormatter:
    """Unified output formatting"""

    def __init__(self):
        self.console = Console()

    def user_table(
            self, users: list[User], title: str = "Users",
            directories: list[Directory] | None = None
    ) -> None:
        """Display users table"""
        if directories:
            dir_info = ", ".join([f"{d.name} ({d.directory_id[:8]}...)" for d in directories])
            self.console.print(f"[dim]Directories: {dir_info}[/dim]")

        table = Table(
            title=title,
            show_lines=False,
            box=box.ROUNDED,
            expand=True,
            width=min(self.console.width - 2, 300)
        )

        columns = ["Email", "Name", "Account ID", "Status", "Type", "Dir"]
        for col in columns:
            table.add_column(col)

        for user in sorted(users, key=lambda x: x.email):
            table.add_row(*user.to_row())

        self.console.print(table)

        stats = Counter(u.status or 'unknown' for u in users)
        active = stats.get('active', 0)
        suspended = stats.get('suspended', 0)
        deactivated = stats.get('deactivated', 0)
        unknown = stats.get('unknown', 0)

        self.console.print(
            f"\n📊 Statistics: "
            f"✓ Active: [green]{active}[/green] | "
            f"⏸ Suspended: [yellow]{suspended}[/yellow] | "
            f"✗ Deactivated: [red]{deactivated}[/red] | "
            f"? Unknown: [dim]{unknown}[/dim] | "
            f"📋 Total: [blue]{len(users)}[/blue]"
        )

    def user_details(self, user: User) -> None:
        """Display user details"""
        self.console.print(f"\n✓ [bold green]User found![/bold green]")
        self.console.print(f"   Email: [cyan]{user.email}[/cyan]")
        self.console.print(f"   Account ID: [yellow]{user.account_id}[/yellow]")
        self.console.print(f"   Name: [magenta]{user.name or 'N/A'}[/magenta]")

        if user.status == "active":
            status_color = "green"
        elif user.status == "suspended":
            status_color = "yellow"
        elif user.status == "deactivated":
            status_color = "red"
        else:
            status_color = "dim"

        self.console.print(f"   Status: [{status_color}]{user.status or 'unknown'}[/{status_color}]")
        self.console.print(f"   Type: [blue]{user.account_type}[/blue]")

        if user.directory_id:
            self.console.print(f"   Directory ID: [dim]{user.directory_id}[/dim]")

    def operation_stats(self, results: ProcessingResults, operation: str, dry_run: bool) -> None:
        """Display operation statistics"""
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        self.console.print(f"\n{'=' * 50}")
        self.console.print(f"[bold]📊 FINAL STATISTICS - {operation.upper()}:[/bold]")

        if dry_run:
            self.console.print(f"✓ Ready for operation: [green]{successful}[/green]")
            self.console.print(f"✗ Check problems: [red]{failed}[/red]")
        else:
            lifecycle_count = sum(1 for r in results if r.lifecycle_action)
            access_count = sum(1 for r in results if r.access_action)

            if operation == "suspend":
                action_word = "suspended"
            else:  # restore
                action_word = "restored"

            self.console.print(f"✓ Successfully {action_word}: [green]{successful}[/green]")

            if lifecycle_count:
                action = "disabled" if operation == "suspend" else "enabled"
                self.console.print(f"   └─ Lifecycle {action}: [cyan]{lifecycle_count}[/cyan]")

            if access_count:
                action = "suspended" if operation == "suspend" else "restored"
                self.console.print(f"   └─ Access {action}: [cyan]{access_count}[/cyan]")

            self.console.print(f"✗ Failed to process: [red]{failed}[/red]")

        self.console.print(f"📋 Total processed: [blue]{len(results)}[/blue]")
        self.console.print("=" * 50)

        if failed > 0:
            self.console.print("\n[bold yellow]💡 Error resolution recommendations:[/bold yellow]")
            self.console.print("1. Check API key permissions (Organization Admin rights required)")
            self.console.print("2. Ensure user domain is verified")
            self.console.print("3. Check account_id correctness in CSV file")
            self.console.print("4. Use show-cloud-users command for verification")


class UserManager:
    """Main user management class"""

    def __init__(self, repo: UserRepositoryProtocol, formatter: OutputFormatter):
        self.repo = repo
        self.formatter = formatter
        self.console = formatter.console

    def process_csv(
            self, csv_file: str, operation: str, test: bool = False,
            dry_run: bool = False, ignore_status: bool = False,
            non_interactive: bool = False, delay: float = 0.5
    ) -> None:
        """Process users from CSV file"""
        if not Path(csv_file).exists():
            logger.error(f"File {csv_file} not found")
            return

        users = self._load_csv(csv_file, operation, ignore_status)

        if test:
            users = users[:1]
            self.console.print(
                f"\n⚠️  [bold yellow]TEST MODE:[/bold yellow] only first user will be processed"
            )

        resume_file = f"{config.logs_dir}/operation_resume_{operation}.json"

        with self._resume_context(resume_file, non_interactive) as processed:
            users = [u for u in users if u.email not in processed]

            if not users:
                self.console.print(
                    f"\n✓ [bold green]All users already processed for operation {operation}![/bold green]")
                return

            if not self._confirm(users, operation, dry_run, non_interactive):
                return

            results = []
            desc = f"{'Testing' if dry_run else 'Processing'} {operation}"

            with Progress() as progress:
                task = progress.add_task(desc, total=len(users))
                for user in users:
                    result = self._process_user(user, operation, dry_run, delay)
                    results.append(result)
                    processed.add(user.email)
                    progress.advance(task)

                    if result.success:
                        status_parts = []
                        if result.lifecycle_action:
                            status_parts.append(f"✓ Lifecycle {result.lifecycle_action}")
                        if result.access_action:
                            status_parts.append(f"✓ Access {result.access_action}")
                        status_str = " | ".join(status_parts) if status_parts else "✓"
                        self.console.print(f"  {status_str} {user.email} - {result.message}")
                    else:
                        self.console.print(f"  ✗ {user.email} - {result.message}")

                    if len(processed) % 10 == 0:
                        self._save_progress(processed, resume_file)

                    if len(users) > 1:
                        time.sleep(delay)

            self._save_results(results, operation)
            self.formatter.operation_stats(results, operation, dry_run)

            # Update CSV with new statuses if not in dry run mode
            if not dry_run and any(r.success for r in results):
                self._update_csv_statuses(csv_file, results, operation)

    def _load_csv(self, csv_file: str, operation: str, ignore_status: bool) -> list[User]:
        """Load and filter users from CSV"""
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = [h.strip() for h in reader.fieldnames or []]
            
            email_col = find_csv_column(headers, ['email', 'Email', 'EMAIL', 'e-mail'])
            if not email_col:
                raise ValueError("Required 'email' column not found in CSV")

            # Find optional columns
            column_mapping = {'email': email_col}
            for standard_name, possible_names in OPTIONAL_CSV_COLUMNS.items():
                found_col = find_csv_column(headers, possible_names)
                if found_col:
                    column_mapping[standard_name] = found_col

            self.console.print(f"[dim]Found columns: {', '.join(column_mapping.values())}[/dim]")

            # Read all rows first
            all_rows = []
            for row in reader:
                # Strip all values and handle empty values
                clean_row = {k: (v.strip() if v else '') for k, v in row.items()}
                if clean_row.get(email_col, '').strip():  # Skip rows without email
                    all_rows.append(clean_row)

            initial_count = len(all_rows)
            
            # Apply status filtering
            if ignore_status:
                self.console.print(f"[dim]--all flag: ignoring status, processing all users[/dim]")
                filtered_rows = all_rows
            elif 'user_status' in column_mapping:
                status_col = column_mapping['user_status']
                filtered_rows = []
                
                for row in all_rows:
                    status = row.get(status_col, '').lower().strip()
                    
                    is_active = status in ['active', 'enabled', 'enable']
                    is_suspended = status in ['suspended', 'suspend']
                    is_deactivated = status in ['deactivated', 'inactive', 'disabled', 'disable', 'deactivate']
                    is_empty = status == ''

                    if operation == 'suspend':
                        # For suspend operation take only active and empty status users
                        if is_active or is_empty:
                            filtered_rows.append(row)
                        filter_desc = "active and without status"
                    elif operation == 'restore':
                        # For restore operation take suspended, deactivated and empty status users
                        if is_suspended or is_deactivated or is_empty:
                            filtered_rows.append(row)
                        filter_desc = "suspended, deactivated or without status"
                    else:
                        filtered_rows.append(row)
                        filter_desc = "all"

                filtered_count = len(filtered_rows)
                excluded_count = initial_count - filtered_count

                self.console.print(
                    f"[dim]Filtering for operation '{operation}': {filtered_count} {filter_desc} "
                    f"from {initial_count} (excluded {excluded_count})[/dim]"
                )
            else:
                self.console.print(f"[dim]Status column not found - processing all users[/dim]")
                filtered_rows = all_rows

            # Remove duplicates by email
            seen_emails = set()
            unique_rows = []
            for row in filtered_rows:
                email = row[email_col].strip().lower()
                if email not in seen_emails:
                    seen_emails.add(email)
                    unique_rows.append(row)

            # Convert to User objects
            users = []
            for row in unique_rows:
                user = User(email=row[email_col].strip())

                if 'user_id' in column_mapping:
                    user_id = row.get(column_mapping['user_id'], '').strip()
                    if user_id:
                        user.account_id = user_id

                if 'user_name' in column_mapping:
                    user_name = row.get(column_mapping['user_name'], '').strip()
                    if user_name:
                        user.name = user_name

                users.append(user)

            self.console.print(f"[dim]Loaded {len(users)} users from CSV[/dim]")
            return users

    def _process_user(
            self, user: User, operation: str, dry_run: bool, delay: float
    ) -> ProcessingResult:
        """Process single user"""
        if not user.account_id:
            found = self.repo.find_user(user.email)
            if found:
                user.account_id = found.account_id
                # Also update name if we found it
                if found.name and not user.name:
                    user.name = found.name
            else:
                return ProcessingResult(
                    email=user.email,
                    account_id=None,
                    success=False,
                    message="User not found",
                    user_obj=user
                )

        if dry_run:
            return ProcessingResult(
                email=user.email,
                account_id=user.account_id,
                success=True,
                message=f"Ready for {operation} operation (DRY RUN)",
                user_obj=user
            )

        try:
            success, message, lifecycle, access = self.repo.update_user_status(
                user.account_id, operation, f"Bulk {operation} operation"
            )
            return ProcessingResult(
                email=user.email,
                account_id=user.account_id,
                success=success,
                message=message,
                lifecycle_action=lifecycle,
                access_action=access,
                user_obj=user
            )
        except RateLimitError:
            logger.warning("Rate limit exceeded, increasing delay...")
            new_delay = min(delay * 2, 5.0)
            time.sleep(new_delay)
            # Retry once
            success, message, lifecycle, access = self.repo.update_user_status(
                user.account_id, operation, f"Bulk {operation} operation"
            )
            return ProcessingResult(
                email=user.email,
                account_id=user.account_id,
                success=success,
                message=message,
                lifecycle_action=lifecycle,
                access_action=access,
                user_obj=user
            )

    @contextmanager
    def _resume_context(self, resume_file: str, non_interactive: bool):
        """Context manager for resume functionality"""
        processed = set()

        if Path(resume_file).exists():
            try:
                with open(resume_file) as f:
                    data = json.load(f)
                    processed = set(data.get('processed_emails', []))

                if processed:
                    if non_interactive:
                        self.console.print(f"\n📁 Found resume file with {len(processed)} processed users.")
                        self.console.print(
                            "[INFO] Non-interactive mode: automatically resuming from where you left off")
                    else:
                        response = input(
                            f"\n📁 Found resume file with {len(processed)} processed users.\n"
                            f"Continue from where you left off? (yes/y to continue): "
                        )
                        if response.lower() in ['yes', 'y']:
                            pass
                        else:
                            processed = set()
                            Path(resume_file).unlink()
            except Exception:
                pass

        try:
            yield processed
            Path(resume_file).unlink(missing_ok=True)
        except Exception:
            self._save_progress(processed, resume_file)
            raise

    @staticmethod
    def _save_progress(processed_emails: set, resume_file: str) -> None:
        """Save progress for resuming"""
        try:
            with open(resume_file, 'w') as f:
                json.dump({
                    'processed_emails': list(processed_emails),
                    'timestamp': datetime.now().isoformat()
                }, f)
        except Exception:
            pass

    def _confirm(
            self, users: list[User], operation: str, dry_run: bool,
            non_interactive: bool
    ) -> bool:
        """Confirm operation"""
        action_verbs = {
            'suspend': ('suspended', 'checked for suspension'),
            'restore': ('restored', 'checked for restoration')
        }
        action = action_verbs[operation][1 if dry_run else 0]

        self.console.print(f"\n⚠️  [bold red]WARNING:[/bold red] {len(users)} user(s) will be {action}!")

        self.console.print("\n[bold]First 5 users:[/bold]")
        for user in users[:5]:
            name_part = f" ([cyan]{user.name}[/cyan])" if user.name else ""
            self.console.print(f"  - {user.email}{name_part}")

        if len(users) > 5:
            self.console.print(f"  [dim]... and {len(users) - 5} more users[/dim]")

        if non_interactive:
            self.console.print("\n[INFO] Non-interactive mode: proceeding automatically")
            return True

        return input("\nContinue? (yes/y to confirm): ").lower() in ['yes', 'y']

    def _save_results(self, results: ProcessingResults, operation: str) -> None:
        """Save operation results"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{config.logs_dir}/operation_log_{operation}_{timestamp}.csv"

        # Create a list of dicts without user_obj field
        data_for_csv = []
        for r in results:
            result_dict = asdict(r)
            result_dict.pop('user_obj', None)  # Remove user_obj field
            data_for_csv.append(result_dict)

        # Write CSV using built-in csv module
        if data_for_csv:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                fieldnames = data_for_csv[0].keys()
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data_for_csv)
        self.console.print(f"\n📄 Log saved to file: [bold cyan]{filename}[/bold cyan]")

    def _update_csv_statuses(
            self, csv_file: str, results: ProcessingResults, operation: str
    ) -> None:
        """Update statuses in CSV file after operation"""
        try:
            # Read original CSV
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                headers = [h.strip() for h in reader.fieldnames or []]
                rows = [{k: v for k, v in row.items()} for row in reader]

            # Find email column
            email_col = find_csv_column(headers, ['email', 'Email', 'EMAIL', 'e-mail'])
            if not email_col:
                logger.warning("Cannot update CSV: email column not found")
                return

            # Find or create status column
            status_col = None
            for standard_name, possible_names in OPTIONAL_CSV_COLUMNS.items():
                if standard_name == 'user_status':
                    status_col = find_csv_column(headers, possible_names)
                    break

            if not status_col:
                status_col = 'User status'
                headers.append(status_col)
                for row in rows:
                    row[status_col] = ''

            # Find or create account_id column
            account_id_col = None
            for standard_name, possible_names in OPTIONAL_CSV_COLUMNS.items():
                if standard_name == 'user_id':
                    account_id_col = find_csv_column(headers, possible_names)
                    break

            if not account_id_col:
                account_id_col = 'User id'
                headers.append(account_id_col)
                for row in rows:
                    row[account_id_col] = ''

            # Find or create name column
            name_col = None
            for standard_name, possible_names in OPTIONAL_CSV_COLUMNS.items():
                if standard_name == 'user_name':
                    name_col = find_csv_column(headers, possible_names)
                    break

            if not name_col:
                name_col = 'User name'
                headers.append(name_col)
                for row in rows:
                    row[name_col] = ''

            # Update data for successfully processed users
            success_count = 0
            for result in results:
                if result.success and result.user_obj:
                    # Find user by email
                    for row in rows:
                        row_email = row.get(email_col, '').strip().lower()
                        if row_email == result.email.lower():
                            # Update status
                            new_status = 'suspended' if operation == 'suspend' else 'active'
                            row[status_col] = new_status

                            # Update account_id if we have it
                            if result.user_obj.account_id:
                                row[account_id_col] = result.user_obj.account_id

                            # Update name if we found it and it was empty
                            if result.user_obj.name:
                                current_name = row.get(name_col, '').strip()
                                if not current_name:
                                    row[name_col] = result.user_obj.name

                            success_count += 1
                            break

            if success_count > 0:
                # Save updated CSV
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(rows)
                    
                self.console.print(
                    f"✓ Updated data for [green]{success_count}[/green] users in "
                    f"[cyan]{csv_file}[/cyan]"
                )

        except Exception as e:
            logger.warning(f"Failed to update CSV: {e}")


def create_cli():
    """Create CLI with lazy initialization"""

    @click.group()
    @click.pass_context
    def cli_group(ctx):
        """Atlassian User Manager - Managing users in cloud Jira/Confluence"""
        if ctx.invoked_subcommand is None or '--help' in sys.argv:
            return

        if not config.org_id or not config.api_key:
            console = Console()
            error_msg = """[bold red]✗ Error: ORG_ID or API_KEY environment variables not found[/bold red]

[bold]⚙️ Setup instructions:[/bold]
1. Create .env file in script directory
2. Add the following:
   [cyan]ORG_ID=your-organization-id
   API_KEY=your-api-key[/cyan]

[bold]🔑 How to get API key:[/bold]
1. Go to Atlassian Admin: [link]https://admin.atlassian.com[/link]
2. Settings → API keys
3. Create API key ([bold yellow]WITHOUT scope![/bold yellow])
4. Ensure you have Organization Admin rights

[bold]📋 How to find Organization ID:[/bold]
1. In Atlassian Admin check URL
2. It will be like: admin.atlassian.com/o/[bold cyan]YOUR-ORG-ID[/bold cyan]/..."""
            console.print(error_msg)
            ctx.exit(1)

        repo = AtlassianUserRepository()
        formatter = OutputFormatter()

        if not any(arg in sys.argv for arg in ['--help', '-h']):
            try:
                console = formatter.console
                console.print("🔒 Verifying credentials...")
                repo.verify_credentials()
                console.print("✓ Credentials verified successfully")
                console.print(f"   Organization: [bold cyan]{config.org_id}[/bold cyan]\n")
            except AuthenticationError as e:
                logger.error(f"Authentication error: {e}")
                ctx.exit(1)
            except Exception as e:
                logger.error(f"Connection failed: {e}")
                ctx.exit(1)

        ctx.obj = {'repo': repo, 'formatter': formatter, 'manager': UserManager(repo, formatter)}

    @cli_group.command('show-cloud-users')
    @click.option('--filter', 'filter_text', help='Filter by text in email (e.g., @example.com)')
    @click.pass_context
    def show_users(ctx, filter_text: str | None):
        """Show all organization users"""
        repo = ctx.obj['repo']
        formatter = ctx.obj['formatter']

        with formatter.console.status("[bold blue]Getting user list...[/bold blue]"):
            users = repo.get_all_users()
            directory_ids = list(set(u.directory_id for u in users if u.directory_id))
            directories = repo.get_directories() if directory_ids else []

        if filter_text:
            filtered_users = [u for u in users if filter_text.lower() in u.email.lower()]
        else:
            filtered_users = users

        title = f"Organization users"
        if filter_text:
            title += f" (filter: '{filter_text}')"
        title += f" - shown: {len(filtered_users)} of {len(users)}"

        formatter.user_table(filtered_users, title, directories)

    @cli_group.command()
    @click.argument('email')
    @click.pass_context
    def search(ctx, email: str):
        """Find user by email"""
        repo = ctx.obj['repo']
        formatter = ctx.obj['formatter']

        with formatter.console.status(f"[bold blue]Searching for user {email}...[/bold blue]"):
            user = repo.find_user(email)
            if user:
                formatter.user_details(user)
            else:
                formatter.console.print(f"✗ User {email} not found", style="red")

    def common_options(f):
        f = click.option(
            '--delay', default=config.default_delay, type=float,
            help=f'Delay between requests in seconds (default: {config.default_delay})'
        )(f)
        f = click.option(
            '--non-interactive', is_flag=True,
            help='Skip confirmation prompts (non-interactive mode)'
        )(f)
        f = click.option(
            '--all', 'ignore_status', is_flag=True,
            help='Ignore status in CSV and process all users'
        )(f)
        f = click.option(
            '--dry-run', is_flag=True,
            help='Check mode - no actual operations performed'
        )(f)
        f = click.option(
            '--test', is_flag=True,
            help='Test mode - process only first user'
        )(f)
        f = click.option(
            '--csv', default=config.default_csv,
            help=f'Path to CSV file (default: {config.default_csv})'
        )(f)
        return f

    @cli_group.command()
    @common_options
    @click.pass_context
    def suspend(ctx, **kwargs):
        """Suspend users (lifecycle disable + suspend access)"""
        manager = ctx.obj['manager']
        kwargs['non_interactive'] = kwargs['non_interactive'] or config.non_interactive
        manager.process_csv(operation='suspend', csv_file=kwargs.pop('csv'), **kwargs)

    @cli_group.command()
    @common_options
    @click.pass_context
    def restore(ctx, **kwargs):
        """Restore users (lifecycle enable + restore access)"""
        manager = ctx.obj['manager']
        kwargs['non_interactive'] = kwargs['non_interactive'] or config.non_interactive
        manager.process_csv(operation='restore', csv_file=kwargs.pop('csv'), **kwargs)

    return cli_group


if __name__ == "__main__":
    try:
        cli_app = create_cli()
        cli_app()
    except KeyboardInterrupt:
        Console().print("\n\n⚠️ Operation interrupted by user", style="yellow")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if config.debug:
            traceback.print_exc()
        sys.exit(1)