# Toolbox

A collection of development and debugging utility scripts for local environment management.

## Scripts

### postgres_manager.sh
Interactive PostgreSQL container manager with persistent storage. Supports multiple database configurations (Watchdog3, Billsen) with commands for starting, stopping, restarting containers, checking status, restoring from dumps, and viewing logs. Uses Docker with TimescaleDB image.

**Usage:**
```bash
./postgres_manager.sh              # Interactive menu
./postgres_manager.sh start        # Start container
./postgres_manager.sh stop         # Stop container
./postgres_manager.sh restart      # Restart container
./postgres_manager.sh status       # Check status
./postgres_manager.sh restore <dump>  # Restore from dump file
./postgres_manager.sh logs         # Show logs
```

### rabbitmq_interface.py
Interactive RabbitMQ queue manager for monitoring and sending commands to devices. Provides an interface to send commands (getinfo, getver, getstatus, battery, cpureset) and configuration checks to specific devices by IMEI. Monitors queues and handles message consumption.

**Usage:**
```bash
python rabbitmq_interface.py --imei 350317177240177  # Interface for specific IMEI
python rabbitmq_interface.py                         # General interface
```

## Requirements

- Docker (for postgres_manager.sh)
- Python 3 with pika and python-dotenv (for rabbitmq_interface.py)
- RabbitMQ server access with proper credentials
