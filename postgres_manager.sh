#!/bin/bash

# postgres_manager.sh - Manage PostgreSQL containers with persistence
#
# Usage:
#   ./postgres_manager.sh            - Show interactive menu to select database and actions
#   ./postgres_manager.sh start      - Start or ensure container is running
#   ./postgres_manager.sh stop       - Stop container
#   ./postgres_manager.sh restart    - Restart container
#   ./postgres_manager.sh status     - Check container status
#   ./postgres_manager.sh restore <dump> - Restore from a dump file
#   ./postgres_manager.sh logs       - Show container logs
#
# Interactive Menu Options:
#   - Database Selection:
#     1) Watchdog3
#     2) Billsen
#
#   - Actions:
#     1) start    - Start or ensure container is running
#     2) stop     - Stop container
#     3) restart  - Restart container
#     4) status   - Check container status
#     5) restore  - Restore from a dump file
#     6) logs     - Show container logs
#
# Complete first-time setup in one go:
#   ./postgres_manager.sh restore watchdog3-stage-dump-202505071106.db
#
# Details:
#
# 1. Initial setup
# Start the PostgreSQL container with the persistent volume
# ./postgres_manager.sh start
#
# 2. Restore your database dump
# Assuming your dump file is named watchdog3-stage-dump-202505071106.db
# ./postgres_manager.sh restore watchdog3-stage-dump-202505071106.db

# Configuration for Watchdog3
WATCHDOG_CONFIG=(
  "CONTAINER_NAME=postgresql16"
  "POSTGRES_USER=watchdog2"
  "POSTGRES_PASSWORD=watchdog2"
  "POSTGRES_DB=watchdog2"
  "POSTGRES_PORT=10000"
  "VOLUME_NAME=pgdata16"
  "POSTGRES_IMAGE=timescale/timescaledb-ha:pg16-ts2.18"
)

# Configuration for Billsen
BILLSEN_CONFIG=(
  "CONTAINER_NAME=billsen-db"
  "POSTGRES_USER=billsen"
  "POSTGRES_PASSWORD=billsen"
  "POSTGRES_DB=billsen"
  "POSTGRES_PORT=5433"
  "VOLUME_NAME=billsen_pgdata"
  "POSTGRES_IMAGE=postgres:16"
)

# Remote dump configuration
SSH_HOST_ALIAS="sstagedb1nur"
DB_HOST="127.0.0.1"
REMOTE_TMP_DIR="/tmp"
LOCAL_DESTINATION="./"

# Remote database passwords
declare -A REMOTE_DB_PASSWORDS
REMOTE_DB_PASSWORDS["billsen"]='$r@4lDV^5%2w5dJJaHrcIgsSBG'
REMOTE_DB_PASSWORDS["wd3"]='watchdog2'

# Remote database configurations (format: "remote_dbname:remote_username:needs_password")
declare -A REMOTE_DB_CONFIGS
REMOTE_DB_CONFIGS["watchdog3"]="watchdog2:watchdog2:false"
REMOTE_DB_CONFIGS["billsen"]="billsen:billsen:true"

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

# Check if docker is installed and running
check_docker() {
  if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed or not in PATH"
    exit 1
  fi
  
  if ! docker info &> /dev/null; then
    log_error "Docker is not running or current user doesn't have permission"
    exit 1
  fi
}

# Check if container exists
container_exists() {
  docker ps -a --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"
  return $?
}

# Check if container is running
container_running() {
  docker ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"
  return $?
}

# Start container if it exists, create it otherwise
start_container() {
  if container_exists; then
    if ! container_running; then
      log_info "Container exists but not running. Starting container..."
      docker start ${CONTAINER_NAME}
      log_success "Container started successfully"
    else
      log_success "Container is already running"
    fi
  else
    log_info "Container does not exist. Creating and starting new container..."
    docker run -d \
      --name ${CONTAINER_NAME} \
      -e POSTGRES_USER=${POSTGRES_USER} \
      -e POSTGRES_PASSWORD=${POSTGRES_PASSWORD} \
      -e POSTGRES_DB=${POSTGRES_DB} \
      -p ${POSTGRES_PORT}:5432 \
      -v ${VOLUME_NAME}:/var/lib/postgresql/data \
      ${POSTGRES_IMAGE}
    
    if [ $? -eq 0 ]; then
      log_success "Container created and started successfully"
      wait_for_postgres
      create_extensions
    else
      log_error "Failed to create and start container"
      exit 1
    fi
  fi
}

# Stop container
stop_container() {
  if container_running; then
    log_info "Stopping container..."
    docker stop ${CONTAINER_NAME}
    log_success "Container stopped successfully"
  else
    log_warn "Container is not running"
  fi
}

# Restart container
restart_container() {
  log_info "Restarting container..."
  if container_running; then
    docker restart ${CONTAINER_NAME}
    log_success "Container restarted successfully"
  else
    if container_exists; then
      docker start ${CONTAINER_NAME}
      log_success "Container started successfully"
    else
      start_container
    fi
  fi
}

# Check container status
container_status() {
  if container_exists; then
    if container_running; then
      log_success "Container is running"
      docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
    else
      log_warn "Container exists but is not running"
    fi
  else
    log_warn "Container does not exist"
  fi
}

# Wait for PostgreSQL to be ready
wait_for_postgres() {
  log_info "Waiting for PostgreSQL to start..."
  max_attempts=30
  attempt=0
  until docker exec ${CONTAINER_NAME} pg_isready -U ${POSTGRES_USER} 2>/dev/null || [ $attempt -ge $max_attempts ]; do
    echo -n "."
    attempt=$((attempt+1))
    sleep 2
  done
  echo "" # New line after dots
  
  if [ $attempt -ge $max_attempts ]; then
    log_error "PostgreSQL failed to start in time"
    exit 1
  fi
  log_success "PostgreSQL is ready!"
}

# Create required extensions
create_extensions() {
  log_info "Creating required extensions..."
  docker exec ${CONTAINER_NAME} psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" &>/dev/null
  docker exec ${CONTAINER_NAME} psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "CREATE EXTENSION IF NOT EXISTS postgis;" &>/dev/null
  log_success "Extensions created successfully"
}

# List database tables
list_tables() {
  if ! container_running; then
    log_error "Container is not running"
    return 1
  fi
  
  log_info "Listing database tables..."
  echo ""
  docker exec ${CONTAINER_NAME} psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "\dt"
  echo ""
  
  # Also show table count
  local table_count=$(docker exec ${CONTAINER_NAME} psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
  if [ -n "$table_count" ] && [ "$table_count" -gt 0 ]; then
    log_success "Total tables in database: $table_count"
  fi
}

# Fetch latest dump from remote server
fetch_remote_dump() {
  local db_config=$1
  
  # Get remote database configuration
  local remote_config=""
  local remote_db_name=""
  local remote_db_user=""
  local needs_password=""
  local remote_db_key=""
  
  case "$db_config" in
    "watchdog3")
      remote_config="${REMOTE_DB_CONFIGS["watchdog3"]}"
      remote_db_key="wd3"
      ;;
    "billsen")
      remote_config="${REMOTE_DB_CONFIGS["billsen"]}"
      remote_db_key="billsen"
      ;;
    *)
      log_error "Unknown database configuration: $db_config"
      return 1
      ;;
  esac
  
  # Parse remote configuration
  IFS=':' read -r remote_db_name remote_db_user needs_password <<< "$remote_config"
  
  # Set up password command if needed
  local pgpassword_cmd=""
  if [ "$needs_password" = "true" ]; then
    if [ -n "${REMOTE_DB_PASSWORDS[$remote_db_key]:-}" ]; then
      pgpassword_cmd="PGPASSWORD='${REMOTE_DB_PASSWORDS[$remote_db_key]}'"
    else
      log_error "No password configured for remote database $remote_db_key"
      return 1
    fi
  fi
  
  # Generate timestamped filename
  local filename="${remote_db_key}-stage-dump-$(date +"%Y%m%d%H%M").db"
  
  log_info "Fetching latest dump from remote server..."
  
  # Validate SSH connection
  log_info "Validating SSH connection to $SSH_HOST_ALIAS..."
  if ! ssh -q "$SSH_HOST_ALIAS" exit; then
    log_error "SSH connection to $SSH_HOST_ALIAS failed. Check your SSH configuration."
    return 1
  fi
  
  # Perform remote database dump
  log_info "Creating PostgreSQL database dump on remote server ($SSH_HOST_ALIAS)..."
  if ! ssh "$SSH_HOST_ALIAS" "$pgpassword_cmd pg_dump -h $DB_HOST -U $remote_db_user -Fc $remote_db_name > $REMOTE_TMP_DIR/$filename"; then
    log_error "Remote database dump failed."
    return 1
  fi
  
  log_success "Remote dump created: $REMOTE_TMP_DIR/$filename"
  
  # Transfer dump file to local machine
  log_info "Transferring dump file to local machine..."
  if ! scp "$SSH_HOST_ALIAS:$REMOTE_TMP_DIR/$filename" "$LOCAL_DESTINATION"; then
    log_error "File transfer failed."
    return 1
  fi
  
  log_success "File successfully transferred to ${LOCAL_DESTINATION}${filename}"
  
  # Cleanup remote temporary dump file
  log_info "Cleaning up remote temporary file..."
  if ssh "$SSH_HOST_ALIAS" "rm $REMOTE_TMP_DIR/$filename"; then
    log_success "Cleaned up remote temporary file."
  else
    log_warn "Warning: Unable to delete remote temporary file."
  fi
  
  # Set the global variable for the fetched file
  SELECTED_DUMP_FILE="${LOCAL_DESTINATION}${filename}"
  log_success "Latest dump fetched: $filename"
  
  return 0
}

# Function to find dump files based on database configuration
find_dump_files() {
  local db_config=$1
  local search_prefix=""
  
  # Set search prefix based on database configuration
  case "$db_config" in
    "watchdog3")
      search_prefix="wd3-stage-dump"
      ;;
    "billsen")
      search_prefix="billsen-stage-dump"
      ;;
    *)
      # Don't echo error, just return
      return 1
      ;;
  esac
  
  # Simple find command - search current directory recursively and home directory
  find . -maxdepth 3 -name "${search_prefix}*.db" -type f 2>/dev/null
  find "$HOME" -maxdepth 1 -name "${search_prefix}*.db" -type f 2>/dev/null
}

# Function to select dump file interactively
select_dump_file() {
  local db_config=$1
  
  local dump_files
  mapfile -t dump_files < <(find_dump_files "$db_config")
  
  
  if [ ${#dump_files[@]} -eq 0 ]; then
    log_warn "No dump files found for $db_config"
    echo -e "${BLUE}Options:${NC}"
    echo "1) Fetch latest dump from remote server"
    echo "2) Enter file path manually"
    echo "3) Cancel"

    while true; do
      read -p "Select option (1-3): " choice
      case "$choice" in
        1)
          if fetch_remote_dump "$db_config"; then
            return 0
          else
            log_error "Failed to fetch remote dump"
            return 1
          fi
          ;;
        2)
          read -p "Enter dump file path: " manual_file
          if [ -z "$manual_file" ]; then
            log_error "No dump file provided"
            return 1
          fi
          SELECTED_DUMP_FILE="$manual_file"
          return 0
          ;;
        3)
          log_info "Restore cancelled"
          return 1
          ;;
        *)
          echo "Invalid selection. Please try again."
          ;;
      esac
    done
  fi
  
  
  echo -e "${BLUE}Available dump files for $db_config:${NC}"
  local i=1
  for file in "${dump_files[@]}"; do
    if [ -f "$file" ]; then
      local file_size=$(du -h "$file" 2>/dev/null | cut -f1 || echo "?")
      local file_date=$(stat -c %y "$file" 2>/dev/null | cut -d' ' -f1 || echo "unknown")
      echo "$i) $(basename "$file") (${file_size}, ${file_date})"
      ((i++))
    fi
  done
  echo "$i) Fetch latest dump from remote server"
  ((i++))
  echo "$i) Enter file path manually"
  
  while true; do
    read -p "Select dump file (1-$i): " choice
    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le $i ]; then
      if [ "$choice" -eq $i ]; then
        # Manual entry option (last option)
        read -p "Enter dump file path: " manual_file
        if [ -z "$manual_file" ]; then
          log_error "No dump file provided"
          continue
        fi
        SELECTED_DUMP_FILE="$manual_file"
        return 0
      elif [ "$choice" -eq $((i-1)) ]; then
        # Fetch latest dump option (second to last option)
        if fetch_remote_dump "$db_config"; then
          return 0
        else
          log_error "Failed to fetch remote dump"
          continue
        fi
      else
        # Selected from list
        SELECTED_DUMP_FILE="${dump_files[$((choice-1))]}"
        return 0
      fi
    else
      echo "Invalid selection. Please try again."
    fi
  done
}

# Restore database from dump
restore_database() {
  local dump_file_path="$1"
  
  # If no file provided, use interactive selection
  if [ -z "$dump_file_path" ]; then
    # Determine database config based on current configuration
    local current_db_config=""
    if [ "$CONTAINER_NAME" = "postgresql16" ]; then
      current_db_config="watchdog3"
    elif [ "$CONTAINER_NAME" = "billsen-db" ]; then
      current_db_config="billsen"
    else
      log_error "Cannot determine database configuration for dump file selection"
      return 1
    fi
    
    SELECTED_DUMP_FILE=""
    select_dump_file "$current_db_config"
    dump_file_path="$SELECTED_DUMP_FILE"
    if [ -z "$dump_file_path" ]; then
      log_error "No dump file selected"
      return 1
    fi
  fi
  
  # Get dump file path
  DB_DUMP_FILE=""
  
  # Handle relative, absolute, or simple filenames
  if [[ "$dump_file_path" == /* ]]; then
    # Absolute path
    DB_DUMP_FILE="$dump_file_path"
  elif [[ "$dump_file_path" == ./* || "$dump_file_path" == ../* ]]; then
    # Relative path
    DB_DUMP_FILE="$(realpath "$dump_file_path")"
  else
    # Simple filename - check in current directory first, then in home
    if [ -f "./$dump_file_path" ]; then
      DB_DUMP_FILE="$(realpath "./$dump_file_path")"
    elif [ -f "$HOME/$dump_file_path" ]; then
      DB_DUMP_FILE="$HOME/$dump_file_path"
    else
      log_error "Cannot find file '$dump_file_path' in current directory or home directory"
      exit 1
    fi
  fi
  
  # Verify file exists and is readable
  if [ ! -f "$DB_DUMP_FILE" ]; then
    log_error "File '$DB_DUMP_FILE' does not exist"
    exit 1
  fi
  if [ ! -r "$DB_DUMP_FILE" ]; then
    log_error "File '$DB_DUMP_FILE' is not readable"
    exit 1
  fi
  
  log_info "Using database dump: $DB_DUMP_FILE"
  
  # Restart container to ensure clean state
  restart_container
  wait_for_postgres
  
  # Copy file to container
  log_info "Copying database dump to container..."
  docker cp "$DB_DUMP_FILE" ${CONTAINER_NAME}:/tmp/dbdump.db
  
  # Create extensions
  create_extensions
  
  # Restore database
  log_info "Restoring database (this may take some time)..."
  docker exec ${CONTAINER_NAME} pg_restore --clean --no-owner \
    -U ${POSTGRES_USER} \
    -d ${POSTGRES_DB} \
    --verbose /tmp/dbdump.db
  
  if [ $? -eq 0 ]; then
    log_success "Database restoration complete!"
  else
    log_warn "Database restoration completed with some warnings or errors"
  fi
  
  # List tables to verify restoration
  echo ""
  log_info "Verifying restoration by listing tables..."
  list_tables

  # Ask if user wants to delete the dump file
  echo ""
  while true; do
    read -p "Do you want to delete the dump file '$DB_DUMP_FILE'? (y/N): " delete_choice
    case "$delete_choice" in
      [Yy]* )
        if rm "$DB_DUMP_FILE" 2>/dev/null; then
          log_success "Dump file deleted: $DB_DUMP_FILE"
        else
          log_error "Failed to delete dump file: $DB_DUMP_FILE"
        fi
        break
        ;;
      [Nn]* | "" )
        log_info "Dump file kept: $DB_DUMP_FILE"
        break
        ;;
      * )
        echo "Please answer yes (y) or no (n)"
        ;;
    esac
  done
}

# Function to cleanup old containers
cleanup_old_containers() {
  local config_name=$1
  local old_containers=()
  
  case "$config_name" in
    "billsen")
      # Find containers by name (exact match for billsen-db and any containing billsen)
      old_containers+=($(docker ps -a --format "{{.Names}}" | grep -E "^billsen-db$|billsen"))
      
      # Find containers by port mapping (5433)
      old_containers+=($(docker ps -a --format "{{.Names}}" | while read name; do
        if docker port "$name" 2>/dev/null | grep -q "5433"; then
          echo "$name"
        fi
      done))
      
      # Find containers by image (postgres:16)
      old_containers+=($(docker ps -a --format "{{.Names}}" --filter "ancestor=postgres:16"))
      ;;
    "watchdog3")
      # Add any old watchdog container names here if needed
      ;;
  esac
  
  # Remove duplicates from the array
  old_containers=($(echo "${old_containers[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' '))
  
  if [ ${#old_containers[@]} -gt 0 ]; then
    log_info "Found the following old containers:"
    for container in "${old_containers[@]}"; do
      # Show more details about each container
      echo "  - $container"
      echo "    Image: $(docker inspect -f '{{.Config.Image}}' $container 2>/dev/null)"
      echo "    Ports: $(docker port $container 2>/dev/null)"
    done
    
    while true; do
      read -p "Do you want to remove all of them? (y/N): " choice
      case "$choice" in
        [Yy]* )
          for container in "${old_containers[@]}"; do
            if [ "$container" != "$CONTAINER_NAME" ]; then
              log_info "Removing container: $container"
              docker rm -f "$container" 2>/dev/null
              if [ $? -eq 0 ]; then
                log_success "Container removed: $container"
              else
                log_error "Failed to remove container: $container"
              fi
            fi
          done
          
          # Double check if any containers are still running
          remaining=$(docker ps --format "{{.Names}}" | grep -E "^billsen-db$|billsen|5433")
          if [ ! -z "$remaining" ]; then
            log_warn "Some containers are still running:"
            echo "$remaining"
            read -p "Force remove remaining containers? (y/N): " force_choice
            case "$force_choice" in
              [Yy]* )
                echo "$remaining" | while read container; do
                  log_info "Force removing container: $container"
                  docker rm -f "$container" 2>/dev/null
                done
                ;;
              * )
                log_info "Skipping force removal"
                ;;
            esac
          fi
          break
          ;;
        [Nn]* | "" )
          log_info "Skipping container removal"
          break
          ;;
        * )
          echo "Please answer yes (y) or no (n)"
          ;;
      esac
    done
  else
    log_success "No old containers found"
  fi
}

# Function to load configuration
load_config() {
  local config_name=$1
  local config_array
  
  case "$config_name" in
    "watchdog3")
      config_array=("${WATCHDOG_CONFIG[@]}")
      ;;
    "billsen")
      config_array=("${BILLSEN_CONFIG[@]}")
      ;;
    *)
      log_error "Invalid configuration: $config_name"
      exit 1
      ;;
  esac
  
  for item in "${config_array[@]}"; do
    export "$item"
  done
  
  # Cleanup old containers after loading config
  cleanup_old_containers "$config_name"
}

# Function to show menu
show_menu() {
  echo -e "${BLUE}Select database to manage:${NC}"
  echo "1) Watchdog3"
  echo "2) Billsen"
  echo "q) Quit"
  
  read -p "Enter your choice (1-2, q): " choice
  
  case $choice in
    1)
      load_config "watchdog3"
      ;;
    2)
      load_config "billsen"
      ;;
    q|Q)
      exit 0
      ;;
    *)
      echo -e "${RED}Invalid choice${NC}"
      exit 1
      ;;
  esac
}

# Function to reset container and volume
reset_postgres() {
  echo ""
  log_warn "⚠️  WARNING: COMPLETE RESET ⚠️"
  echo -e "${RED}This will:${NC}"
  echo -e "${RED}  1. Stop and remove the container: ${CONTAINER_NAME}${NC}"
  echo -e "${RED}  2. DELETE the volume: ${VOLUME_NAME}${NC}"
  echo -e "${RED}  3. PERMANENTLY ERASE all database data${NC}"
  echo ""
  echo -e "${YELLOW}This action CANNOT be undone!${NC}"
  echo ""

  # First confirmation
  read -p "Are you sure you want to continue? Type 'yes' to confirm: " confirm1
  if [ "$confirm1" != "yes" ]; then
    log_info "Reset cancelled"
    return 0
  fi

  # Second confirmation with container name
  echo ""
  read -p "Type the container name '${CONTAINER_NAME}' to confirm: " confirm2
  if [ "$confirm2" != "${CONTAINER_NAME}" ]; then
    log_error "Container name does not match. Reset cancelled"
    return 0
  fi

  echo ""
  log_info "Starting complete PostgreSQL reset..."

  # Stop and remove container if it exists
  if container_exists; then
    log_info "Stopping and removing existing container..."
    docker stop ${CONTAINER_NAME} 2>/dev/null
    docker rm -f ${CONTAINER_NAME} 2>/dev/null
    log_success "Container removed"
  else
    log_info "No existing container found"
  fi

  # Remove volume if it exists
  if docker volume ls -q | grep -q "^${VOLUME_NAME}$"; then
    log_info "Removing existing volume..."
    docker volume rm ${VOLUME_NAME} 2>/dev/null
    log_success "Volume removed"
  else
    log_info "No existing volume found"
  fi

  log_success "PostgreSQL has been completely reset"
  echo ""

  # Ask if user wants to restore from dump
  while true; do
    read -p "Do you want to restore from a dump now? (y/N): " restore_choice
    case "$restore_choice" in
      [Yy]* )
        echo ""
        restore_database
        break
        ;;
      [Nn]* | "" )
        log_info "To create a fresh container later, select 'start' from the menu"
        log_info "To restore from dump later, select 'restore' from the menu"
        break
        ;;
      * )
        echo "Please answer yes (y) or no (n)"
        ;;
    esac
  done
}

# Function to show container logs
show_logs() {
  if ! container_running; then
    log_error "Container is not running"
    return 1
  fi
  
  echo -e "${BLUE}Log options:${NC}"
  echo "1) Show last 100 lines (default)"
  echo "2) Show all logs"
  echo "3) Follow logs in real-time"
  echo "b) Back to action menu"
  
  read -p "Enter your choice (1-3, b) [1]: " log_choice
  
  case $log_choice in
    1|"")
      log_info "Showing last 100 lines of logs..."
      docker logs --tail 100 ${CONTAINER_NAME}
      ;;
    2)
      log_info "Showing all logs..."
      docker logs ${CONTAINER_NAME}
      ;;
    3)
      log_info "Following logs in real-time (press Ctrl+C to stop)..."
      docker logs -f ${CONTAINER_NAME}
      ;;
    b|B)
      return 0
      ;;
    *)
      log_error "Invalid choice"
      return 1
      ;;
  esac
}

# Function to show action menu
show_action_menu() {
  while true; do
    echo -e "${BLUE}Select action:${NC}"
    echo "1) start"
    echo "2) stop"
    echo "3) restart"
    echo "4) status"
    echo "5) restore"
    echo "6) logs"
    echo "7) list tables"
    echo "8) reset (⚠️  DANGER: wipes all data)"
    echo "b) Back to database selection"
    echo "q) Quit"

    read -p "Enter your choice (1-8, b, q): " action_choice

    case $action_choice in
      1)
        start_container
        ;;
      2)
        stop_container
        ;;
      3)
        restart_container
        ;;
      4)
        container_status
        ;;
      5)
        restore_database
        ;;
      6)
        show_logs
        ;;
      7)
        list_tables
        ;;
      8)
        reset_postgres
        ;;
      b|B)
        return 1  # Signal to go back to database selection
        ;;
      q|Q)
        exit 0
        ;;
      *)
        echo -e "${RED}Invalid choice${NC}"
        ;;
    esac
    
    echo  # Add a blank line for better readability
  done
}

# Main function
main() {
  check_docker
  
  # If no arguments provided, show menu and get command
  if [ $# -eq 0 ]; then
    while true; do
      show_menu
      show_action_menu
      # If show_action_menu returns 1, continue to next iteration (back to database selection)
      if [ $? -eq 1 ]; then
        continue
      fi
    done
  else
    # Handle direct command line arguments
    # For direct command line usage, we need to load a default config
    # Since no database was selected interactively, try to determine from available configs
    if [ -z "$CONTAINER_NAME" ]; then
      log_warn "No database configuration loaded. Using Watchdog3 as default for command line usage."
      load_config "watchdog3"
    fi
    
    case "$1" in
      start)
        start_container
        ;;
      stop)
        stop_container
        ;;
      restart)
        restart_container
        ;;
      status)
        container_status
        ;;
      restore)
        if [ -z "$2" ]; then
          restore_database  # Use interactive selection
        else
          restore_database "$2"  # Use provided file
        fi
        ;;
      *)
        echo "Usage: $0 {start|stop|restart|status|restore [dump_file]}"
        exit 1
        ;;
    esac
  fi
}

main "$@"
