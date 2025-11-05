#!/usr/bin/env python3

"""
postgres_manager.py - Manage PostgreSQL containers with persistence

Usage:
  ./postgres_manager.py            - Show interactive menu to select database and actions
  ./postgres_manager.py start      - Start or ensure container is running
  ./postgres_manager.py stop       - Stop container
  ./postgres_manager.py restart    - Restart container
  ./postgres_manager.py status     - Check container status
  ./postgres_manager.py restore <dump> - Restore from a dump file
  ./postgres_manager.py logs       - Show container logs

Interactive Menu Options:
  - Database Selection:
    1) Watchdog3
    2) Billsen

  - Actions:
    1) status   - Check container status (default)
    2) start    - Start or ensure container is running
    3) stop     - Stop container
    4) restart  - Restart container
    5) restore  - Restore from a dump file
    6) logs     - Show container logs
    7) list tables - List database tables
    8) reset    - Complete reset (DANGER: wipes all data)
"""

import subprocess
import sys
import os
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict
import shutil


# Color definitions
class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


@dataclass
class DatabaseConfig:
    """Configuration for a PostgreSQL database container"""

    container_name: str
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_port: int
    volume_name: str
    postgres_image: str
    remote_db_name: str
    remote_db_user: str
    needs_password: bool
    remote_db_key: str
    dump_file_prefix: str


# Configuration for Watchdog3
WATCHDOG_CONFIG = DatabaseConfig(
    container_name="postgresql16",
    postgres_user="watchdog2",
    postgres_password="watchdog2",
    postgres_db="watchdog2",
    postgres_port=10000,
    volume_name="pgdata16",
    postgres_image="timescale/timescaledb-ha:pg16-ts2.18",
    remote_db_name="watchdog2",
    remote_db_user="watchdog2",
    needs_password=False,
    remote_db_key="wd3",
    dump_file_prefix="wd3-stage-dump",
)

# Configuration for Billsen
BILLSEN_CONFIG = DatabaseConfig(
    container_name="billsen-db",
    postgres_user="billsen",
    postgres_password="billsen",
    postgres_db="billsen",
    postgres_port=5433,
    volume_name="billsen_pgdata",
    postgres_image="postgres:16",
    remote_db_name="billsen",
    remote_db_user="billsen",
    needs_password=True,
    remote_db_key="billsen",
    dump_file_prefix="billsen-stage-dump",
)

# Remote dump configuration
SSH_HOST_ALIAS = "sstagedb1nur"
DB_HOST = "127.0.0.1"
REMOTE_TMP_DIR = "/tmp"
LOCAL_DESTINATION = "./"

# Remote database passwords
REMOTE_DB_PASSWORDS = {"billsen": r"$r@4lDV^5%2w5dJJaHrcIgsSBG", "wd3": "watchdog2"}


def log_info(message: str):
    """Print info message"""
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {message}")


def log_success(message: str):
    """Print success message"""
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {message}")


def log_warn(message: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {message}")


def log_error(message: str):
    """Print error message"""
    print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")


def run_command(
    cmd: List[str], capture_output=True, check=False
) -> subprocess.CompletedProcess:
    """Run a shell command"""
    try:
        if capture_output:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        else:
            result = subprocess.run(cmd, check=check)
        return result
    except subprocess.CalledProcessError as e:
        return e


def check_docker() -> bool:
    """Check if docker is installed and running"""
    # Check if docker is installed
    if not shutil.which("docker"):
        log_error("Docker is not installed or not in PATH")
        return False

    # Check if docker is running
    result = run_command(["docker", "info"])
    if result.returncode != 0:
        log_error("Docker is not running or current user doesn't have permission")
        return False

    return True


class PostgresManager:
    """Manager for PostgreSQL containers"""

    def __init__(self, config: DatabaseConfig):
        self.config = config

    def container_exists(self) -> bool:
        """Check if container exists"""
        result = run_command(["docker", "ps", "-a", "--format", "{{.Names}}"])
        if result.returncode == 0:
            containers = result.stdout.strip().split("\n")
            return self.config.container_name in containers
        return False

    def container_running(self) -> bool:
        """Check if container is running"""
        result = run_command(["docker", "ps", "--format", "{{.Names}}"])
        if result.returncode == 0:
            containers = result.stdout.strip().split("\n")
            return self.config.container_name in containers
        return False

    def wait_for_postgres(self, max_attempts=30) -> bool:
        """Wait for PostgreSQL to be ready"""
        log_info("Waiting for PostgreSQL to start...")

        for attempt in range(max_attempts):
            result = run_command(
                [
                    "docker",
                    "exec",
                    self.config.container_name,
                    "pg_isready",
                    "-U",
                    self.config.postgres_user,
                ]
            )

            if result.returncode == 0:
                print()  # New line after dots
                log_success("PostgreSQL is ready!")
                return True

            print(".", end="", flush=True)
            time.sleep(2)

        print()  # New line after dots
        log_error("PostgreSQL failed to start in time")
        return False

    def create_extensions(self):
        """Create required extensions"""
        log_info("Creating required extensions...")

        # Try to create timescaledb extension
        run_command(
            [
                "docker",
                "exec",
                self.config.container_name,
                "psql",
                "-U",
                self.config.postgres_user,
                "-d",
                self.config.postgres_db,
                "-c",
                "CREATE EXTENSION IF NOT EXISTS timescaledb;",
            ]
        )

        # Try to create postgis extension
        run_command(
            [
                "docker",
                "exec",
                self.config.container_name,
                "psql",
                "-U",
                self.config.postgres_user,
                "-d",
                self.config.postgres_db,
                "-c",
                "CREATE EXTENSION IF NOT EXISTS postgis;",
            ]
        )

        log_success("Extensions created successfully")

    def start_container(self):
        """Start container if it exists, create it otherwise"""
        if self.container_exists():
            if not self.container_running():
                log_info("Container exists but not running. Starting container...")
                run_command(["docker", "start", self.config.container_name])
                log_success("Container started successfully")
            else:
                log_success("Container is already running")
        else:
            log_info("Container does not exist. Creating and starting new container...")

            result = run_command(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    self.config.container_name,
                    "-e",
                    f"POSTGRES_USER={self.config.postgres_user}",
                    "-e",
                    f"POSTGRES_PASSWORD={self.config.postgres_password}",
                    "-e",
                    f"POSTGRES_DB={self.config.postgres_db}",
                    "-p",
                    f"{self.config.postgres_port}:5432",
                    "-v",
                    f"{self.config.volume_name}:/var/lib/postgresql/data",
                    self.config.postgres_image,
                ]
            )

            if result.returncode == 0:
                log_success("Container created and started successfully")
                if self.wait_for_postgres():
                    self.create_extensions()
            else:
                log_error("Failed to create and start container")
                sys.exit(1)

    def stop_container(self):
        """Stop container"""
        if self.container_running():
            log_info("Stopping container...")
            run_command(["docker", "stop", self.config.container_name])
            log_success("Container stopped successfully")
        else:
            log_warn("Container is not running")

    def restart_container(self):
        """Restart container"""
        log_info("Restarting container...")

        if self.container_running():
            run_command(["docker", "restart", self.config.container_name])
            log_success("Container restarted successfully")
        else:
            if self.container_exists():
                run_command(["docker", "start", self.config.container_name])
                log_success("Container started successfully")
            else:
                self.start_container()

    def container_status(self):
        """Check container status"""
        if self.container_exists():
            if self.container_running():
                log_success("Container is running")
                run_command(
                    [
                        "docker",
                        "ps",
                        "--filter",
                        f"name={self.config.container_name}",
                        "--format",
                        "table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}",
                    ],
                    capture_output=False,
                )
            else:
                log_warn("Container exists but is not running")
        else:
            log_warn("Container does not exist")

    def list_tables(self):
        """List database tables"""
        if not self.container_running():
            log_error("Container is not running")
            return False

        log_info("Listing database tables...")
        print()

        run_command(
            [
                "docker",
                "exec",
                self.config.container_name,
                "psql",
                "-U",
                self.config.postgres_user,
                "-d",
                self.config.postgres_db,
                "-c",
                "\\dt",
            ],
            capture_output=False,
        )

        print()

        # Show table count
        result = run_command(
            [
                "docker",
                "exec",
                self.config.container_name,
                "psql",
                "-U",
                self.config.postgres_user,
                "-d",
                self.config.postgres_db,
                "-t",
                "-c",
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';",
            ]
        )

        if result.returncode == 0:
            table_count = result.stdout.strip()
            if table_count and int(table_count) > 0:
                log_success(f"Total tables in database: {table_count}")

        return True

    def find_dump_files(self) -> List[Path]:
        """Find dump files based on database configuration"""
        dump_files = []

        # Search current directory recursively (max depth 3)
        current_dir = Path(".")
        for dump_file in current_dir.rglob(f"{self.config.dump_file_prefix}*.db"):
            if dump_file.is_file() and len(dump_file.parts) <= 4:
                dump_files.append(dump_file)

        # Search home directory (max depth 1)
        home_dir = Path.home()
        for dump_file in home_dir.glob(f"{self.config.dump_file_prefix}*.db"):
            if dump_file.is_file():
                dump_files.append(dump_file)

        return sorted(dump_files, key=lambda x: x.stat().st_mtime, reverse=True)

    def fetch_remote_dump(self) -> Optional[Path]:
        """Fetch latest dump from remote server"""
        log_info("Fetching latest dump from remote server...")

        # Validate SSH connection
        log_info(f"Validating SSH connection to {SSH_HOST_ALIAS}...")
        result = run_command(["ssh", "-q", SSH_HOST_ALIAS, "exit"])
        if result.returncode != 0:
            log_error(
                f"SSH connection to {SSH_HOST_ALIAS} failed. Check your SSH configuration."
            )
            return None

        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d%H%M")
        filename = f"{self.config.remote_db_key}-stage-dump-{timestamp}.db"

        # Set up password command if needed
        pgpassword_cmd = ""
        if self.config.needs_password:
            if self.config.remote_db_key in REMOTE_DB_PASSWORDS:
                password = REMOTE_DB_PASSWORDS[self.config.remote_db_key]
                pgpassword_cmd = f"PGPASSWORD='{password}' "
            else:
                log_error(
                    f"No password configured for remote database {self.config.remote_db_key}"
                )
                return None

        # Perform remote database dump
        log_info(
            f"Creating PostgreSQL database dump on remote server ({SSH_HOST_ALIAS})..."
        )
        dump_cmd = f"{pgpassword_cmd}pg_dump -h {DB_HOST} -U {self.config.remote_db_user} -Fc {self.config.remote_db_name} > {REMOTE_TMP_DIR}/{filename}"

        result = run_command(["ssh", SSH_HOST_ALIAS, dump_cmd])
        if result.returncode != 0:
            log_error("Remote database dump failed.")
            return None

        log_success(f"Remote dump created: {REMOTE_TMP_DIR}/{filename}")

        # Transfer dump file to local machine
        log_info("Transferring dump file to local machine...")
        result = run_command(
            ["scp", f"{SSH_HOST_ALIAS}:{REMOTE_TMP_DIR}/{filename}", LOCAL_DESTINATION]
        )
        if result.returncode != 0:
            log_error("File transfer failed.")
            return None

        log_success(f"File successfully transferred to {LOCAL_DESTINATION}{filename}")

        # Cleanup remote temporary dump file
        log_info("Cleaning up remote temporary file...")
        result = run_command(["ssh", SSH_HOST_ALIAS, f"rm {REMOTE_TMP_DIR}/{filename}"])
        if result.returncode == 0:
            log_success("Cleaned up remote temporary file.")
        else:
            log_warn("Warning: Unable to delete remote temporary file.")

        local_file = Path(LOCAL_DESTINATION) / filename
        log_success(f"Latest dump fetched: {filename}")
        return local_file

    def select_dump_file(self) -> Optional[Path]:
        """Select dump file interactively"""
        dump_files = self.find_dump_files()

        if not dump_files:
            log_warn(f"No dump files found for {self.config.container_name}")
            print(f"{Colors.BLUE}Options:{Colors.NC}")
            print("1) Fetch latest dump from remote server")
            print("2) Enter file path manually")
            print("3) Cancel")

            while True:
                choice = input("Select option (1-3): ").strip()
                if choice == "1":
                    return self.fetch_remote_dump()
                elif choice == "2":
                    manual_file = input("Enter dump file path: ").strip()
                    if not manual_file:
                        log_error("No dump file provided")
                        continue
                    return Path(manual_file)
                elif choice == "3":
                    log_info("Restore cancelled")
                    return None
                else:
                    print("Invalid selection. Please try again.")

        # Show available dump files
        print(f"{Colors.BLUE}Available dump files:{Colors.NC}")
        for i, dump_file in enumerate(dump_files, 1):
            file_size = self._get_file_size(dump_file)
            file_date = datetime.fromtimestamp(dump_file.stat().st_mtime).strftime(
                "%Y-%m-%d"
            )
            print(f"{i}) {dump_file.name} ({file_size}, {file_date})")

        fetch_option = len(dump_files) + 1
        manual_option = len(dump_files) + 2

        print(f"{fetch_option}) Fetch latest dump from remote server")
        print(f"{manual_option}) Enter file path manually")

        while True:
            choice = input(f"Select dump file (1-{manual_option}): ").strip()
            if choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(dump_files):
                    return dump_files[choice_num - 1]
                elif choice_num == fetch_option:
                    return self.fetch_remote_dump()
                elif choice_num == manual_option:
                    manual_file = input("Enter dump file path: ").strip()
                    if not manual_file:
                        log_error("No dump file provided")
                        continue
                    return Path(manual_file)

            print("Invalid selection. Please try again.")

    def _get_file_size(self, file_path: Path) -> str:
        """Get human-readable file size"""
        size = file_path.stat().st_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}TB"

    def restore_database(self, dump_file_path: Optional[str] = None):
        """Restore database from dump"""
        # Determine dump file
        if dump_file_path:
            db_dump_file = Path(dump_file_path)
        else:
            db_dump_file = self.select_dump_file()
            if not db_dump_file:
                log_error("No dump file selected")
                return False

        # Handle different path types
        if not db_dump_file.is_absolute():
            # Try current directory first
            if (Path.cwd() / db_dump_file).exists():
                db_dump_file = (Path.cwd() / db_dump_file).resolve()
            # Try home directory
            elif (Path.home() / db_dump_file).exists():
                db_dump_file = Path.home() / db_dump_file
            else:
                log_error(
                    f"Cannot find file '{db_dump_file}' in current directory or home directory"
                )
                return False

        # Verify file exists and is readable
        if not db_dump_file.exists():
            log_error(f"File '{db_dump_file}' does not exist")
            return False

        if not os.access(db_dump_file, os.R_OK):
            log_error(f"File '{db_dump_file}' is not readable")
            return False

        log_info(f"Using database dump: {db_dump_file}")

        # Restart container to ensure clean state
        self.restart_container()
        if not self.wait_for_postgres():
            return False

        # Copy file to container
        log_info("Copying database dump to container...")
        run_command(
            [
                "docker",
                "cp",
                str(db_dump_file),
                f"{self.config.container_name}:/tmp/dbdump.db",
            ]
        )

        # Create extensions
        self.create_extensions()

        # Restore database
        log_info("Restoring database (this may take some time)...")
        result = run_command(
            [
                "docker",
                "exec",
                self.config.container_name,
                "pg_restore",
                "--clean",
                "--no-owner",
                "-U",
                self.config.postgres_user,
                "-d",
                self.config.postgres_db,
                "--verbose",
                "/tmp/dbdump.db",
            ],
            capture_output=False,
        )

        if result.returncode == 0:
            log_success("Database restoration complete!")
        else:
            log_warn("Database restoration completed with some warnings or errors")

        # List tables to verify restoration
        print()
        log_info("Verifying restoration by listing tables...")
        self.list_tables()

        # Ask if user wants to delete the dump file
        print()
        while True:
            delete_choice = (
                input(f"Do you want to delete the dump file '{db_dump_file}'? (y/N): ")
                .strip()
                .lower()
            )
            if delete_choice in ["y", "yes"]:
                try:
                    db_dump_file.unlink()
                    log_success(f"Dump file deleted: {db_dump_file}")
                except Exception as e:
                    log_error(f"Failed to delete dump file: {e}")
                break
            elif delete_choice in ["n", "no", ""]:
                log_info(f"Dump file kept: {db_dump_file}")
                break
            else:
                print("Please answer yes (y) or no (n)")

        return True

    def show_logs(self):
        """Show container logs"""
        if not self.container_running():
            log_error("Container is not running")
            return False

        print(f"{Colors.BLUE}Log options:{Colors.NC}")
        print("1) Show last 100 lines (default)")
        print("2) Show all logs")
        print("3) Follow logs in real-time")
        print("b) Back to action menu")

        log_choice = input("Enter your choice (1-3, b) [1]: ").strip() or "1"

        if log_choice == "1":
            log_info("Showing last 100 lines of logs...")
            run_command(
                ["docker", "logs", "--tail", "100", self.config.container_name],
                capture_output=False,
            )
        elif log_choice == "2":
            log_info("Showing all logs...")
            run_command(
                ["docker", "logs", self.config.container_name], capture_output=False
            )
        elif log_choice == "3":
            log_info("Following logs in real-time (press Ctrl+C to stop)...")
            try:
                run_command(
                    ["docker", "logs", "-f", self.config.container_name],
                    capture_output=False,
                )
            except KeyboardInterrupt:
                print()
                log_info("Stopped following logs")
        elif log_choice.lower() == "b":
            return True
        else:
            log_error("Invalid choice")
            return False

        return True

    def cleanup_old_containers(self):
        """Cleanup old containers"""
        old_containers = []

        if self.config.container_name == "billsen-db":
            # Find containers by name
            result = run_command(["docker", "ps", "-a", "--format", "{{.Names}}"])
            if result.returncode == 0:
                containers = result.stdout.strip().split("\n")
                for container in containers:
                    if "billsen" in container:
                        old_containers.append(container)

            # Find containers by port mapping (5433)
            result = run_command(["docker", "ps", "-a", "--format", "{{.Names}}"])
            if result.returncode == 0:
                containers = result.stdout.strip().split("\n")
                for container in containers:
                    port_result = run_command(["docker", "port", container])
                    if port_result.returncode == 0 and "5433" in port_result.stdout:
                        if container not in old_containers:
                            old_containers.append(container)

            # Find containers by image (postgres:16)
            result = run_command(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--format",
                    "{{.Names}}",
                    "--filter",
                    "ancestor=postgres:16",
                ]
            )
            if result.returncode == 0:
                containers = result.stdout.strip().split("\n")
                for container in containers:
                    if container and container not in old_containers:
                        old_containers.append(container)

        # Remove duplicates
        old_containers = list(set(old_containers))

        if old_containers:
            log_info("Found the following old containers:")
            for container in old_containers:
                print(f"  - {container}")

                # Show more details
                result = run_command(
                    ["docker", "inspect", "-f", "{{.Config.Image}}", container]
                )
                if result.returncode == 0:
                    print(f"    Image: {result.stdout.strip()}")

                result = run_command(["docker", "port", container])
                if result.returncode == 0 and result.stdout.strip():
                    print(f"    Ports: {result.stdout.strip()}")

            while True:
                choice = (
                    input("Do you want to remove all of them? (y/N): ").strip().lower()
                )
                if choice in ["y", "yes"]:
                    for container in old_containers:
                        if container != self.config.container_name:
                            log_info(f"Removing container: {container}")
                            result = run_command(["docker", "rm", "-f", container])
                            if result.returncode == 0:
                                log_success(f"Container removed: {container}")
                            else:
                                log_error(f"Failed to remove container: {container}")
                    break
                elif choice in ["n", "no", ""]:
                    log_info("Skipping container removal")
                    break
                else:
                    print("Please answer yes (y) or no (n)")
        else:
            log_success("No old containers found")

    def reset_postgres(self):
        """Reset container and volume completely"""
        print()
        log_warn("⚠️  WARNING: COMPLETE RESET ⚠️")
        print(f"{Colors.RED}This will:{Colors.NC}")
        print(
            f"{Colors.RED}  1. Stop and remove the container: {self.config.container_name}{Colors.NC}"
        )
        print(
            f"{Colors.RED}  2. DELETE the volume: {self.config.volume_name}{Colors.NC}"
        )
        print(f"{Colors.RED}  3. PERMANENTLY ERASE all database data{Colors.NC}")
        print()
        print(f"{Colors.YELLOW}This action CANNOT be undone!{Colors.NC}")
        print()

        # First confirmation
        confirm1 = input(
            "Are you sure you want to continue? Type 'yes' to confirm: "
        ).strip()
        if confirm1 != "yes":
            log_info("Reset cancelled")
            return

        # Second confirmation with container name
        print()
        confirm2 = input(
            f"Type the container name '{self.config.container_name}' to confirm: "
        ).strip()
        if confirm2 != self.config.container_name:
            log_error("Container name does not match. Reset cancelled")
            return

        print()
        log_info("Starting complete PostgreSQL reset...")

        # Stop and remove container if it exists
        if self.container_exists():
            log_info("Stopping and removing existing container...")
            run_command(["docker", "stop", self.config.container_name])
            run_command(["docker", "rm", "-f", self.config.container_name])
            log_success("Container removed")
        else:
            log_info("No existing container found")

        # Remove volume if it exists
        result = run_command(["docker", "volume", "ls", "-q"])
        if result.returncode == 0 and self.config.volume_name in result.stdout:
            log_info("Removing existing volume...")
            run_command(["docker", "volume", "rm", self.config.volume_name])
            log_success("Volume removed")
        else:
            log_info("No existing volume found")

        log_success("PostgreSQL has been completely reset")
        print()

        # Ask if user wants to restore from dump
        while True:
            restore_choice = (
                input("Do you want to restore from a dump now? (y/N): ").strip().lower()
            )
            if restore_choice in ["y", "yes"]:
                print()
                self.restore_database()
                break
            elif restore_choice in ["n", "no", ""]:
                log_info(
                    "To create a fresh container later, select 'start' from the menu"
                )
                log_info("To restore from dump later, select 'restore' from the menu")
                break
            else:
                print("Please answer yes (y) or no (n)")


def show_database_menu() -> Optional[DatabaseConfig]:
    """Show database selection menu"""
    print(f"{Colors.BLUE}Select database to manage:{Colors.NC}")
    print("1) Watchdog3")
    print("2) Billsen")
    print("q) Quit")

    choice = input("Enter your choice (1-2, q): ").strip()

    if choice == "1":
        return WATCHDOG_CONFIG
    elif choice == "2":
        return BILLSEN_CONFIG
    elif choice.lower() == "q":
        sys.exit(0)
    else:
        print(f"{Colors.RED}Invalid choice{Colors.NC}")
        return None


def show_action_menu(manager: PostgresManager) -> bool:
    """Show action menu. Returns True to continue, False to go back"""
    while True:
        print(f"{Colors.BLUE}Select action:{Colors.NC}")
        print("1) status")
        print("2) start")
        print("3) stop")
        print("4) restart")
        print("5) restore")
        print("6) logs")
        print("7) list tables")
        print("8) reset (⚠️  DANGER: wipes all data)")
        print("b) Back to database selection")
        print("q) Quit")

        action_choice = input("Enter your choice (1-8, b, q) [1]: ").strip() or "1"

        if action_choice == "1":
            manager.container_status()
        elif action_choice == "2":
            manager.start_container()
        elif action_choice == "3":
            manager.stop_container()
        elif action_choice == "4":
            manager.restart_container()
        elif action_choice == "5":
            manager.restore_database()
        elif action_choice == "6":
            manager.show_logs()
        elif action_choice == "7":
            manager.list_tables()
        elif action_choice == "8":
            manager.reset_postgres()
        elif action_choice.lower() == "b":
            return False  # Go back to database selection
        elif action_choice.lower() == "q":
            sys.exit(0)
        else:
            print(f"{Colors.RED}Invalid choice{Colors.NC}")

        print()  # Add blank line for better readability


def main():
    """Main function"""
    if not check_docker():
        sys.exit(1)

    # If no arguments provided, show menu
    if len(sys.argv) == 1:
        while True:
            config = show_database_menu()
            if config:
                manager = PostgresManager(config)
                manager.cleanup_old_containers()
                show_action_menu(manager)
    else:
        # Handle direct command line arguments
        # Use Watchdog3 as default for command line usage
        log_warn(
            "No database configuration loaded. Using Watchdog3 as default for command line usage."
        )
        config = WATCHDOG_CONFIG
        manager = PostgresManager(config)
        manager.cleanup_old_containers()

        command = sys.argv[1]

        if command == "start":
            manager.start_container()
        elif command == "stop":
            manager.stop_container()
        elif command == "restart":
            manager.restart_container()
        elif command == "status":
            manager.container_status()
        elif command == "restore":
            if len(sys.argv) > 2:
                manager.restore_database(sys.argv[2])
            else:
                manager.restore_database()
        elif command == "logs":
            manager.show_logs()
        else:
            print(
                f"Usage: {sys.argv[0]} {{start|stop|restart|status|restore [dump_file]|logs}}"
            )
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        log_info("Operation cancelled by user")
        sys.exit(0)
