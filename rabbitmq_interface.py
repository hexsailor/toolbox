#!/usr/bin/env python3
"""
RabbitMQ Queue Manager
Combines monitoring and command sending functionality

USAGE EXAMPLES:
python rabbitmq_interface.py --imei 350317177240177    # Open interface for specific IMEI
python rabbitmq_interface.py -i 350317177240177        # Short form
python rabbitmq_interface.py                           # Open general interface
"""

import argparse
import datetime
import json
import logging
import os
import signal
import sys
import time
import uuid
from typing import Optional

import pika
from dotenv import load_dotenv

# Load environment variables
load_dotenv("/home/xmarine/.dotenv/.env")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s - %(levelname)s -- %(name)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Reduce pika logging noise
pika_logger = logging.getLogger("pika")
pika_logger.setLevel(logging.WARNING)

# Available commands - easy to add new ones here
AVAILABLE_COMMANDS = {
    "1": {"command": "getinfo", "description": "Get Device Info"},
    "2": {"command": "getver", "description": "Get Device Version"},
    "3": {"command": "getstatus", "description": "Modem Status information"},
    "4": {"command": "battery", "description": "Get Battery Status"},
    "5": {"command": "cpureset", "description": "Resets device"},
}

# Set commands for configuration checking
SET_COMMANDS = {
    "1": {
        "name": "Check duplicate server",
        "commands": [
            {"command": "getparam 2007", "description": "Duplicate server ip"},
            {"command": "getparam 2008", "description": "Duplicate server port"},
            {"command": "getparam 2010", "description": "Duplicate server status"},
        ],
    }
}


class RabbitMQInterface:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.rabbitmq_url = os.environ.get(
            "RABBITMQ_BROKER_URL", "amqp://watchdog2:TEST@localhost:5673/%2F"
        )
        self.data_queue = "device_tcp_data"
        self.running = True
        self.target_imei = None

    def connect(self):
        """Connect to RabbitMQ"""
        # Check if using environment variable or default
        using_env_var = "RABBITMQ_BROKER_URL" in os.environ
        if using_env_var:
            logger.info(
                f"🔗 Using RABBITMQ_BROKER_URL from environment: {self.rabbitmq_url}"
            )
        else:
            logger.info(f"🔗 Using default RabbitMQ URL: {self.rabbitmq_url}")

        while True:
            try:
                logger.info(f"Connecting to RabbitMQ: {self.rabbitmq_url}")
                self.connection = pika.BlockingConnection(
                    pika.URLParameters(self.rabbitmq_url)
                )
                self.channel = self.connection.channel()
                logger.info("Successfully connected to RabbitMQ")
                break
            except Exception as e:
                logger.error(f"Failed to connect to RabbitMQ: {e}")
                print("\n" + "=" * 60)
                print("❌ RabbitMQ Connection Failed!")
                print("=" * 60)
                print(f"Current URL: {self.rabbitmq_url}")
                if "RABBITMQ_BROKER_URL" in os.environ:
                    print("📝 URL source: Environment variable (RABBITMQ_BROKER_URL)")
                else:
                    print("📝 URL source: Script default")
                print(f"Error: {e}")
                print(
                    "\n💡 TIP: You can export RABBITMQ_BROKER_URL before running this script:"
                )
                print(
                    "   export RABBITMQ_BROKER_URL='amqp://user:pass@host:port/vhost'"
                )
                print("   python rabbitmq_interface.py --imei YOUR_IMEI")
                print("\nOptions:")
                print("1. Enter a new RabbitMQ URL")
                print("q. Quit")
                print("=" * 60)

                choice = input("Enter your choice (1/q): ").strip().lower()

                if choice == "q":
                    print("Exiting...")
                    sys.exit(1)
                elif choice == "1":
                    new_url = input(
                        "Enter new RabbitMQ URL (e.g., amqp://user:pass@host:port/vhost): "
                    ).strip()
                    if new_url:
                        self.rabbitmq_url = new_url
                        print(f"Updated RabbitMQ URL to: {new_url}")
                    else:
                        print("No URL provided, using current URL")
                else:
                    print("Invalid choice, trying again with current URL...")

    def close(self):
        """Close the connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger.info("RabbitMQ connection closed")

    def ensure_connection(self):
        """Ensure connection and channel are available"""
        try:
            if not self.connection or self.connection.is_closed:
                logger.info("Connection lost, reconnecting...")
                self.connect()
            elif not self.channel or self.channel.is_closed:
                logger.info("Channel lost, recreating...")
                self.channel = self.connection.channel()
        except Exception as e:
            logger.error(f"Error ensuring connection: {e}")
            self.connect()

    # === COMMAND SENDER FUNCTIONALITY ===
    
    def send_command(self, imei: str, command: str, command_id: Optional[str] = None):
        """Send a command to a specific device queue"""
        try:
            # Generate command ID if not provided
            if command_id is None:
                command_id = str(uuid.uuid4())

            # Prepare command message
            message = {
                "command_id": command_id,
                "command": command,
                "timestamp": str(int(time.time())),
                "source": "command_sender",
            }

            # Declare queue (create if doesn't exist)
            self.channel.queue_declare(queue=imei, durable=True)

            # Send command
            self.channel.basic_publish(
                exchange="",
                routing_key=imei,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent message
                    content_type="application/json",
                ),
            )

            logger.info("✅ Command sent successfully!")
            logger.info(f"  IMEI: {imei}")
            logger.info(f"  Command: {command}")
            logger.info(f"  Command ID: {command_id}")

            # Check queue status
            queue_info = self.channel.queue_declare(queue=imei, passive=True)
            logger.info(
                f"  Queue status: {queue_info.method.message_count} messages in queue"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to send command: {e}")
            return False

    def check_queue_status(self, imei: str):
        """Check the status of a device's command queue"""
        try:
            # Temporarily suppress pika warnings for queue existence checks
            pika_logger.setLevel(logging.ERROR)
            queue_info = self.channel.queue_declare(queue=imei, passive=True)
            pika_logger.setLevel(logging.WARNING)
            message_count = queue_info.method.message_count
            consumer_count = queue_info.method.consumer_count

            print("=" * 60)
            print(f"QUEUE STATUS FOR IMEI: {imei}")
            print("=" * 60)
            print(f"Messages in queue: {message_count}")
            print(f"Active consumers: {consumer_count}")
            print("=" * 60)

        except Exception as e:
            # Restore pika logging level in case of exception
            pika_logger.setLevel(logging.WARNING)
            logger.error(f"Error checking queue status: {e}")

    def list_queue_commands(self, imei: str):
        """List commands in the queue (shows last 10 if more than 10 total)"""
        try:
            # Temporarily suppress pika warnings for queue existence checks
            pika_logger.setLevel(logging.ERROR)
            queue_info = self.channel.queue_declare(queue=imei, passive=True)
            pika_logger.setLevel(logging.WARNING)
            message_count = queue_info.method.message_count

            if message_count == 0:
                print(f"📭 Command queue for IMEI {imei} is empty")
                return

            # Determine how many to show
            show_limit = 10
            show_all = message_count <= show_limit
            
            print("=" * 60)
            if show_all:
                print(f"📋 ALL COMMANDS IN QUEUE FOR IMEI: {imei}")
                print(f"Total commands: {message_count}")
            else:
                print(f"📋 LAST {show_limit} COMMANDS IN QUEUE FOR IMEI: {imei}")
                print(f"Total commands: {message_count} (showing last {show_limit} only)")
                print("💡 Use 'Purge Queue' option to clear old commands if needed")
            print("=" * 60)

            # Collect all messages first, then show the last N
            messages = []
            for i in range(message_count):
                method_frame, header_frame, body = self.channel.basic_get(
                    queue=imei, auto_ack=False
                )

                if method_frame is None:
                    break

                messages.append((method_frame, body))

            # Show the messages (last N if too many)
            messages_to_show = messages[-show_limit:] if not show_all else messages
            start_index = message_count - len(messages_to_show) + 1 if not show_all else 1

            for idx, (method_frame, body) in enumerate(messages_to_show):
                display_number = start_index + idx
                
                try:
                    data = json.loads(body.decode("utf-8"))
                    command = data.get("command", "Unknown")
                    command_id = data.get("command_id", "N/A")
                    timestamp = data.get("timestamp", "N/A")
                    source = data.get("source", "N/A")

                    print(f"{display_number:2d}. Command: {command}")
                    print(f"     ID: {command_id}")
                    print(f"     Timestamp: {timestamp}")
                    print(f"     Source: {source}")
                    print("-" * 40)

                except json.JSONDecodeError:
                    print(
                        f"{display_number:2d}. Raw message: {body.decode('utf-8', errors='ignore')}"
                    )
                    print("-" * 40)

            # Put all messages back in queue (in reverse order to maintain original order)
            for method_frame, body in reversed(messages):
                self.channel.basic_nack(delivery_tag=method_frame.delivery_tag)

            print("=" * 60)

        except Exception as e:
            # Restore pika logging level in case of exception
            pika_logger.setLevel(logging.WARNING)
            logger.error(f"Error listing queue commands: {e}")

    def purge_queue(self, imei: str):
        """Purge (clear) all commands from the queue"""
        try:
            # Temporarily suppress pika warnings for queue existence checks
            pika_logger.setLevel(logging.ERROR)
            queue_info = self.channel.queue_declare(queue=imei, passive=True)
            pika_logger.setLevel(logging.WARNING)
            message_count = queue_info.method.message_count

            if message_count == 0:
                print(f"📭 Command queue for IMEI {imei} is already empty")
                return

            print("=" * 60)
            print(f"🗑️  PURGING COMMAND QUEUE FOR IMEI: {imei}")
            print(f"Commands to remove: {message_count}")
            print("=" * 60)

            # Confirm with user
            confirm = (
                input(
                    f"Are you sure you want to delete {message_count} commands? (yes/no): "
                )
                .strip()
                .lower()
            )

            if confirm in ["yes", "y"]:
                # Purge the queue
                self.channel.queue_purge(queue=imei)
                print("✅ Queue purged successfully!")

                # Verify
                new_count = self.channel.queue_declare(
                    queue=imei, passive=True
                ).method.message_count
                print(f"Remaining commands: {new_count}")
            else:
                print("❌ Queue purge cancelled")

            print("=" * 60)

        except Exception as e:
            # Restore pika logging level in case of exception
            pika_logger.setLevel(logging.WARNING)
            logger.error(f"Error purging queue: {e}")

    # === MONITOR FUNCTIONALITY ===
    
    def check_monitor_status(self):
        """Check queue status and message counts"""
        try:
            # Ensure connection is healthy
            self.ensure_connection()

            # Check main data queue
            queue_info = self.channel.queue_declare(self.data_queue, passive=True)
            message_count = queue_info.method.message_count
            consumer_count = queue_info.method.consumer_count

            print("\n" + "=" * 70)
            print("🔍 RABBITMQ STATUS OVERVIEW")
            if self.target_imei:
                print(f"📱 Target Device: {self.target_imei}")
            else:
                print("📱 Target Device: ALL DEVICES")
            print("=" * 70)
            
            # Main data queue status
            print(f"\n📊 DATA QUEUE STATUS")
            print(f"   Queue Name: {self.data_queue}")
            print(f"   Total Messages: {message_count:,}")
            print(f"   Active Consumers: {consumer_count}")
            
            if consumer_count == 0 and message_count > 0:
                print(f"   ⚠️  Warning: No consumers processing messages")

            if message_count > 0:
                # Check message types
                message_types, imei_breakdown = self._analyze_message_types(message_count)
                
                # Show IMEI-specific info if filtering
                if self.target_imei and imei_breakdown:
                    filtered_count = sum(imei_breakdown.values())
                    print(f"\n📱 TARGET DEVICE DATA:")
                    print(f"   Messages from {self.target_imei}: {filtered_count:,}")
                
                print(f"\n📈 MESSAGE BREAKDOWN:")
                for msg_type, count in message_types.items():
                    if msg_type == "DATA":
                        print(f"   📍 {msg_type}: {count:,} messages")
                    elif msg_type == "CONNECTION":
                        print(f"   📡 {msg_type}: {count:,} messages")
                    elif msg_type == "RAW":
                        print(f"   📦 {msg_type}: {count:,} messages")
                    else:
                        print(f"   ❓ {msg_type}: {count:,} messages")

                # Health indicators
                print(f"\n🏥 QUEUE HEALTH:")
                if "DATA" in message_types:
                    print(f"   ✅ AVL Data Flow: Active ({message_types['DATA']:,} messages)")
                else:
                    print(f"   ❌ AVL Data Flow: No recent data messages")

                if consumer_count > 0:
                    print(f"   ✅ Message Processing: Active ({consumer_count} consumers)")
                else:
                    print(f"   ⚠️  Message Processing: No active consumers")
            else:
                print(f"\n📭 Queue is currently empty")

            # Check command queues if IMEI is specified
            if self.target_imei:
                self._check_command_queue_status(self.target_imei)
            else:
                self._check_all_command_queues()

            print("=" * 70)
            return message_count, message_types if message_count > 0 else {}

        except Exception as e:
            logger.error(f"Error checking status: {e}")
            return 0, {}

    def _check_command_queue_status(self, imei: str):
        """Check status of a specific command queue"""
        try:
            # Temporarily suppress pika warnings for queue existence checks
            pika_logger.setLevel(logging.ERROR)
            queue_info = self.channel.queue_declare(queue=imei, passive=True)
            # Restore pika logging level
            pika_logger.setLevel(logging.WARNING)
            message_count = queue_info.method.message_count
            consumer_count = queue_info.method.consumer_count

            print(f"\n🔧 COMMAND QUEUE STATUS")
            print(f"   Device IMEI: {imei}")
            print(f"   Pending Commands: {message_count}")
            print(f"   Active Consumers: {consumer_count}")

            # Status indicators
            if consumer_count > 0:
                print(f"   🟢 Device Status: ONLINE (consumer connected)")
            else:
                print(f"   🔴 Device Status: OFFLINE (no consumer)")

            if message_count > 0:
                if consumer_count > 0:
                    print(f"   📤 Command Processing: Commands queued, being processed")
                else:
                    print(f"   ⏳ Command Processing: Commands waiting (device offline)")
                
                print(f"\n📋 NEXT COMMANDS TO PROCESS:")

                # Peek at commands (don't consume them)
                messages_to_requeue = []
                try:
                    for i in range(min(message_count, 3)):  # Show max 3
                        method_frame, header_frame, body = self.channel.basic_get(
                            queue=imei, auto_ack=False
                        )

                        if method_frame is None:
                            break

                        # Store delivery tag for requeuing
                        messages_to_requeue.append(method_frame.delivery_tag)

                        try:
                            data = json.loads(body.decode("utf-8"))
                            command = data.get("command", "Unknown")
                            command_id = data.get("command_id", "N/A")
                            # Safely truncate command_id if it's a string
                            if isinstance(command_id, str):
                                command_id = command_id[:8]
                            timestamp = data.get("timestamp", "N/A")
                            print(f"   {i+1}. {command}")
                            print(f"      ID: {command_id}...")
                            if timestamp != "N/A":
                                try:
                                    dt = datetime.datetime.fromtimestamp(int(timestamp))
                                    print(f"      Queued: {dt.strftime('%H:%M:%S')}")
                                except:
                                    print(f"      Timestamp: {timestamp}")
                        except json.JSONDecodeError:
                            print(f"   {i+1}. Raw message: {body.decode('utf-8', errors='ignore')[:50]}...")

                finally:
                    # Put all messages back in queue in reverse order
                    for delivery_tag in reversed(messages_to_requeue):
                        try:
                            self.channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
                        except Exception as e:
                            logger.debug(f"Error requeuing message {delivery_tag}: {e}")

                if message_count > 3:
                    print(f"   ... and {message_count - 3} more commands")
            else:
                print(f"   ✅ Command Queue: Empty (no pending commands)")
            
        except Exception as e:
            # Restore pika logging level in case of exception
            pika_logger.setLevel(logging.WARNING)
            print(f"   ❌ Command queue not accessible: {e}")
    
    def _check_all_command_queues(self):
        """Check all available command queues"""
        try:
            print(f"\n🔧 COMMAND QUEUES OVERVIEW")
            print(f"   Status: No specific device selected")
            print(f"   💡 Tip: Use --imei <IMEI> or select 'Change/Set IMEI' to monitor specific device commands")
            
            # Try to check some common IMEI patterns - expand list as needed
            common_imeis = [
                "350317177240177", "862771041414213", "350317177240178", 
                "350317177240179", "862771041414214", "862771041414215",
                "862771041414216", "862771041414217", "350317177240180",
                "350317177240181", "350317177240182", "350317177240183"
            ]
            
            device_queues = []
            
            for imei in common_imeis:
                try:
                    # Temporarily suppress pika warnings for queue existence checks
                    pika_logger.setLevel(logging.ERROR)
                    queue_info = self.channel.queue_declare(queue=imei, passive=True)
                    
                    # Restore pika logging level
                    pika_logger.setLevel(logging.WARNING)
                    
                    message_count = queue_info.method.message_count
                    consumer_count = queue_info.method.consumer_count
                    
                    # Include device if it has messages or is online
                    if message_count > 0 or consumer_count > 0:
                        status = "🟢 ONLINE" if consumer_count > 0 else "🔴 OFFLINE"
                        device_queues.append({
                            'imei': imei,
                            'messages': message_count,
                            'consumers': consumer_count,
                            'status': status
                        })
                except Exception:
                    # Restore pika logging level in case of exception
                    pika_logger.setLevel(logging.WARNING)
                    # Queue doesn't exist or not accessible - this is expected
            
            if device_queues:
                # Sort by message count (descending) then by consumer count (descending)
                device_queues.sort(key=lambda x: (x['messages'], x['consumers']), reverse=True)
                
                # Show max 5 devices
                display_count = min(5, len(device_queues))
                print(f"\n📋 ACTIVE DEVICE QUEUES (showing top {display_count}):")
                
                for i in range(display_count):
                    device = device_queues[i]
                    print(f"   📱 {device['imei']}: {device['messages']} commands, {device['status']}")
                
                if len(device_queues) > 5:
                    print(f"   ... and {len(device_queues) - 5} more devices")
            else:
                print(f"\n📭 No active command queues found")
                    
        except Exception as e:
            logger.debug(f"Error checking command queues: {e}")

    def _analyze_message_types(self, max_messages=10):
        """Analyze message types in queue"""
        message_types = {}
        imei_counts = {}
        messages_to_requeue = []

        try:
            for i in range(min(max_messages, 10)):  # Check max 10 messages
                method_frame, header_frame, body = self.channel.basic_get(
                    self.data_queue, auto_ack=False
                )

                if method_frame is None:
                    break

                # Store delivery tag for requeuing
                messages_to_requeue.append(method_frame.delivery_tag)

                try:
                    data = json.loads(body.decode("utf-8"))
                    msg_type = data.get("type", "UNKNOWN")
                    imei = data.get("imei", "UNKNOWN")

                    # Always collect IMEI counts for breakdown
                    if imei not in imei_counts:
                        imei_counts[imei] = 0
                    imei_counts[imei] += 1

                    # Count message type (filter by IMEI if specified)
                    if not self.target_imei or imei == self.target_imei:
                        if msg_type not in message_types:
                            message_types[msg_type] = 0
                        message_types[msg_type] += 1

                except json.JSONDecodeError:
                    if "RAW" not in message_types:
                        message_types["RAW"] = 0
                    message_types["RAW"] += 1

        finally:
            # Requeue all messages in reverse order to maintain original order
            for delivery_tag in reversed(messages_to_requeue):
                try:
                    self.channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
                except Exception as e:
                    logger.debug(f"Error requeuing message {delivery_tag}: {e}")

        # Return both message types and IMEI breakdown
        return message_types, imei_counts

    def peek_messages(self, limit=5, show_json=False):
        """Peek at messages without consuming them"""
        try:
            # Ensure connection is healthy
            self.ensure_connection()

            queue_info = self.channel.queue_declare(self.data_queue, passive=True)
            message_count = queue_info.method.message_count

            if message_count == 0:
                logger.info("📭 No messages in queue to peek")
                return

            logger.info("=" * 60)
            logger.info(
                f"PEEKING AT MESSAGES (showing {min(limit, message_count)} of {message_count})"
            )
            if self.target_imei:
                logger.info(f"Filtering for IMEI: {self.target_imei}")
            logger.info("=" * 60)

            messages_shown = 0
            messages_to_requeue = []

            try:
                for i in range(min(limit * 3, message_count)):  # Check more messages to find filtered ones
                    method_frame, header_frame, body = self.channel.basic_get(
                        self.data_queue, auto_ack=False
                    )

                    if method_frame is None:
                        break

                    # Store delivery tag for requeuing
                    messages_to_requeue.append(method_frame.delivery_tag)

                    # Check if this message matches our IMEI filter
                    if self.target_imei:
                        try:
                            data = json.loads(body.decode("utf-8"))
                            imei = data.get("imei", "UNKNOWN")
                            if imei != self.target_imei:
                                continue
                        except json.JSONDecodeError:
                            # Skip raw messages when filtering by IMEI
                            continue

                    self._display_message(messages_shown + 1, body, show_json)
                    messages_shown += 1

                    if messages_shown >= limit:
                        break

            finally:
                # Requeue all messages in reverse order to maintain original order
                for delivery_tag in reversed(messages_to_requeue):
                    try:
                        self.channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
                    except Exception as e:
                        logger.debug(f"Error requeuing message {delivery_tag}: {e}")

            if self.target_imei and messages_shown == 0:
                logger.info(f"❌ No messages found for IMEI: {self.target_imei}")

            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error peeking messages: {e}")

    def _display_message(self, msg_num, body, show_json=False):
        """Display a single message"""
        try:
            data = json.loads(body.decode("utf-8"))
            msg_type = data.get("type", "UNKNOWN")

            logger.info(f"Message {msg_num}:")
            logger.info(f"  Type: {msg_type}")
            logger.info(f"  IMEI: {data.get('imei', 'N/A')}")
            logger.info(f"  Device: {data.get('device', 'N/A')}")
            logger.info(f"  Timestamp: {data.get('timestamp', 'N/A')}")

            # Show message content based on type
            if msg_type == "CONNECTION":
                message_data = data.get("message", {})
                logger.info(f"  Status: {message_data.get('status', 'N/A')}")
                logger.info(f"  Source: {message_data.get('source', 'N/A')}")
            elif msg_type == "DATA":
                message_data = data.get("message", {})
                logger.info(
                    f"  🗺️  Location: [{message_data.get('lon', 'N/A')}, {message_data.get('lat', 'N/A')}]"
                )
                logger.info(f"  Speed: {message_data.get('speed', 'N/A')} km/h")
                logger.info(f"  Altitude: {message_data.get('alt', 'N/A')} m")
                logger.info(f"  Satellites: {message_data.get('sat_num', 'N/A')}")
                logger.info(f"  Bearing: {message_data.get('bearing', 'N/A')}°")
                logger.info(f"  Priority: {message_data.get('priority', 'N/A')}")
            elif msg_type == "RAW":
                message_data = data.get("message", {})
                hex_data = message_data.get("raw_data", "")
                logger.info(f"  Raw data length: {len(hex_data)} characters")
                logger.info(f"  Raw data preview: {hex_data[:50]}...")

            if show_json:
                logger.info(f"  Full JSON: {json.dumps(data, indent=2)}")

            logger.info("-" * 40)

        except json.JSONDecodeError:
            logger.info(f"Message {msg_num} (raw):")
            logger.info(f"  Raw data: {body.decode('utf-8', errors='ignore')}")
            logger.info("-" * 40)

    def monitor_realtime(self, show_json=False):
        """Monitor queue in real-time for new messages"""
        try:
            # Ensure connection is healthy
            self.ensure_connection()

            logger.info("=" * 60)
            logger.info("REAL-TIME MONITORING")
            logger.info("=" * 60)
            if self.target_imei:
                logger.info(f"Filtering for IMEI: {self.target_imei}")
            logger.info("Monitoring queue for new messages...")
            logger.info("Press Ctrl+C to stop monitoring")
            logger.info("=" * 60)

            def message_callback(ch, method, properties, body):
                """Callback for each message received"""
                # Check if this message matches our IMEI filter
                if self.target_imei:
                    try:
                        data = json.loads(body.decode("utf-8"))
                        imei = data.get("imei", "UNKNOWN")
                        if imei != self.target_imei:
                            # Acknowledge and skip this message
                            ch.basic_ack(delivery_tag=method.delivery_tag)
                            return
                    except json.JSONDecodeError:
                        # Acknowledge and skip raw messages when filtering by IMEI
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        return

                logger.info("🎯 NEW MESSAGE DETECTED!")
                self._display_message("REALTIME", body, show_json=show_json)

                # Acknowledge the message
                ch.basic_ack(delivery_tag=method.delivery_tag)

            # Set up consumer
            self.channel.basic_consume(
                queue=self.data_queue,
                on_message_callback=message_callback,
                auto_ack=False,
            )

            logger.info("Waiting for messages... (Press Ctrl+C to stop)")
            self.channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("\n⏹️  Stopping real-time monitor...")
            try:
                if self.channel and self.channel.is_open:
                    self.channel.stop_consuming()
            except Exception as e:
                logger.debug(f"Error stopping consumer: {e}")
        except Exception as e:
            logger.error(f"Error in real-time monitoring: {e}")
            try:
                if self.channel and self.channel.is_open:
                    self.channel.stop_consuming()
            except Exception:
                pass

    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        logger.info("Received interrupt signal, stopping monitor...")
        self.running = False
        if self.connection and not self.connection.is_closed:
            self.connection.close()
        sys.exit(0)

    # === QUEUE OPERATIONS ===

    def is_imei_format(self, queue_name):
        """Check if a queue name matches IMEI format (15 digits)"""
        return queue_name.isdigit() and len(queue_name) == 15

    def find_queues_by_partial_name(self, search_term):
        """Find all queues that contain the search term (case-insensitive)"""
        try:
            # Ensure we have a valid connection and channel
            self.ensure_connection()

            search_term_lower = search_term.lower()

            # Use smart discovery to get all queues
            all_queues = self._discover_queues_smart()

            # Filter queues by search term
            queues_found = [q for q in all_queues if search_term_lower in q['name'].lower()]

            return queues_found

        except Exception as e:
            logger.error(f"Error finding queues by partial name '{search_term}': {e}")
            return []

    def _discover_queues_smart(self):
        """Smart queue discovery - tries multiple methods to find ALL queues"""
        queues_found = []

        # Method 1: Try Management API (best method - finds ALL queues)
        try:
            import requests

            # Extract connection details from URL
            url_parts = self.rabbitmq_url.replace('amqp://', '').replace('amqps://', '')
            if '@' in url_parts:
                auth_part, server_part = url_parts.split('@', 1)
                if ':' in auth_part:
                    username, password = auth_part.split(':', 1)
                else:
                    username = auth_part
                    password = ""
            else:
                username = "guest"
                password = "guest"
                server_part = url_parts

            if ':' in server_part:
                host = server_part.split(':')[0]
                port_and_vhost = server_part.split(':', 1)[1]
                if '/' in port_and_vhost:
                    port = port_and_vhost.split('/')[0]
                else:
                    port = port_and_vhost
            else:
                host = server_part.split('/')[0]
                port = "5672"

            # Try management API on port 15672
            management_url = f"http://{host}:15672/api/queues"
            response = requests.get(management_url, auth=(username, password), timeout=5)

            if response.status_code == 200:
                queues_data = response.json()
                logger.info(f"✅ Management API available - found {len(queues_data)} queues")
                for queue in queues_data:
                    queues_found.append({
                        'name': queue.get('name', 'Unknown'),
                        'messages': queue.get('messages', 0),
                        'consumers': queue.get('consumers', 0),
                        'durable': queue.get('durable', False),
                        'auto_delete': queue.get('auto_delete', False)
                    })
                return queues_found
            else:
                raise Exception(f"Management API returned status {response.status_code}")

        except Exception as e:
            logger.debug(f"Management API not available: {e}")

        # Method 2: Fallback - Scan for IMEI patterns and known queues
        logger.info("Management API not available, using smart fallback method...")
        logger.info("💡 To see ALL queues, install requests library: pip install requests")
        logger.info("💡 And enable RabbitMQ management plugin on the server")

        discovered_queues = set()

        # Start with known system queues
        system_queues = [
            self.data_queue,
            "device_commands", "system_alerts", "error_queue",
            "dead_letter_queue", "audit_log", "notifications"
        ]

        # Scan for IMEI patterns - common prefixes for device IMEIs
        # Most IMEIs start with TAC (Type Allocation Code) - common prefixes
        imei_prefixes = [
            "350", "351", "352", "353", "354", "355", "356", "357", "358", "359",  # Common TACs
            "860", "861", "862", "863", "864", "865", "866", "867", "868", "869",  # Common Asian manufacturers
            "490", "491", "492",  # Some older devices
        ]

        # Generate potential IMEI patterns to check
        # We'll scan systematically but limit to avoid too many checks
        logger.info("Scanning for active IMEI queues...")

        check_queues = system_queues.copy()

        # Add IMEI scan range - we'll check patterns intelligently
        # Instead of brute force, we'll use a smarter approach:
        # Check recent/likely IMEI patterns based on your examples

        for queue_candidate in check_queues:
            if queue_candidate not in discovered_queues:
                try:
                    pika_logger.setLevel(logging.ERROR)
                    queue_info = self.channel.queue_declare(queue=queue_candidate, passive=True)
                    pika_logger.setLevel(logging.WARNING)

                    discovered_queues.add(queue_candidate)
                    queues_found.append({
                        'name': queue_candidate,
                        'messages': queue_info.method.message_count,
                        'consumers': queue_info.method.consumer_count,
                        'durable': True,
                        'auto_delete': False
                    })
                except Exception:
                    pika_logger.setLevel(logging.WARNING)
                    continue

        if not queues_found:
            logger.warning("⚠️  No queues discovered. Management API recommended for full visibility.")
        else:
            logger.info(f"Found {len(queues_found)} queues using fallback method")
            logger.warning("⚠️  Note: Fallback method may not show all queues. Some queues might be missing.")

        return queues_found

    def list_all_queues(self, filter_type="all", show_active_only=False):
        """List all queues in the RabbitMQ server

        Args:
            filter_type: "all", "non-imei", "imei-only", or "active"
            show_active_only: If True, only show queues with messages or consumers
        """
        try:
            # Ensure we have a valid connection and channel
            self.ensure_connection()

            print("\n" + "=" * 70)
            if filter_type == "non-imei":
                print("🗂️  NON-IMEI QUEUES ON RABBITMQ SERVER")
                print("(Excluding 15-digit numeric IMEI queues)")
            elif filter_type == "imei-only":
                print("🗂️  IMEI QUEUES ON RABBITMQ SERVER")
                print("(Only 15-digit numeric IMEI queues)")
            elif filter_type == "active":
                print("🗂️  ACTIVE QUEUES ON RABBITMQ SERVER")
                print("(Only queues with messages or consumers)")
            else:
                print("🗂️  ALL QUEUES ON RABBITMQ SERVER")
            print("=" * 70)

            # Use smart discovery
            queues_found = self._discover_queues_smart()

            if not queues_found:
                print("📭 No queues found or accessible")
                print("\n💡 TROUBLESHOOTING:")
                print("   1. Install requests library: pip install requests")
                print("   2. Enable RabbitMQ management plugin on server")
                print("   3. Check if queues exist: rabbitmqctl list_queues")
                return

            # Apply filtering based on filter_type
            if filter_type == "non-imei":
                queues_found = [q for q in queues_found if not self.is_imei_format(q['name'])]
            elif filter_type == "imei-only":
                queues_found = [q for q in queues_found if self.is_imei_format(q['name'])]
            elif filter_type == "active" or show_active_only:
                queues_found = [q for q in queues_found if q['messages'] > 0 or q['consumers'] > 0]

            if not queues_found:
                filter_msg = ""
                if filter_type == "non-imei":
                    filter_msg = " (no non-IMEI queues found)"
                elif filter_type == "imei-only":
                    filter_msg = " (no IMEI queues found)"
                elif filter_type == "active":
                    filter_msg = " (no active queues found)"
                print(f"📭 No queues found or accessible{filter_msg}")
                return

            # Smart sorting: prioritize queues with activity
            # Sort by: 1) has consumers, 2) has messages, 3) message count
            queues_found.sort(key=lambda x: (
                x['consumers'] > 0,  # Active consumers first
                x['messages'] > 0,   # Then queues with messages
                x['messages'],       # Then by message count
                x['consumers']       # Then by consumer count
            ), reverse=True)

            print(f"Found {len(queues_found)} queues:\n")

            # Display queues in a table format with better formatting
            print(f"{'Queue Name':<30} {'Messages':<10} {'Consumers':<10} {'Status':<12} {'Durable':<8}")
            print("-" * 70)

            for queue in queues_found:
                name = queue['name'][:29] if len(queue['name']) > 29 else queue['name']
                messages = str(queue['messages'])
                consumers = str(queue['consumers'])
                durable = "Yes" if queue['durable'] else "No"

                # Add status indicator
                if queue['consumers'] > 0 and queue['messages'] > 0:
                    status = "🟡 BUSY"
                elif queue['consumers'] > 0:
                    status = "🟢 ACTIVE"
                elif queue['messages'] > 0:
                    status = "🔴 BACKLOG"
                else:
                    status = "⚪ IDLE"

                print(f"{name:<30} {messages:<10} {consumers:<10} {status:<12} {durable:<8}")

            print("\n" + "=" * 70)

            # Show helpful summary
            active_queues = sum(1 for q in queues_found if q['consumers'] > 0)
            queues_with_messages = sum(1 for q in queues_found if q['messages'] > 0)
            total_messages = sum(q['messages'] for q in queues_found)

            print(f"📊 SUMMARY:")
            print(f"   Active queues (with consumers): {active_queues}")
            print(f"   Queues with pending messages: {queues_with_messages}")
            print(f"   Total messages across all queues: {total_messages:,}")

        except Exception as e:
            logger.error(f"Error listing queues: {e}")
            print(f"❌ Error listing queues: {e}")

    def inspect_queue_by_name(self, queue_name: str):
        """Inspect a specific queue by name"""
        try:
            # Ensure we have a valid connection and channel
            self.ensure_connection()

            print("\n" + "=" * 60)
            print(f"🔍 INSPECTING QUEUE: {queue_name}")
            print("=" * 60)

            # Try to get queue info
            try:
                # Temporarily suppress pika warnings for queue existence checks
                pika_logger.setLevel(logging.ERROR)
                queue_info = self.channel.queue_declare(queue=queue_name, passive=True)
                pika_logger.setLevel(logging.WARNING)

                message_count = queue_info.method.message_count
                consumer_count = queue_info.method.consumer_count

                print(f"Queue Name: {queue_name}")
                print(f"Messages in Queue: {message_count:,}")
                print(f"Active Consumers: {consumer_count}")

                # Status indicators
                if consumer_count > 0:
                    print("Status: 🟢 ACTIVE (has consumers)")
                else:
                    print("Status: 🔴 INACTIVE (no consumers)")

                if message_count > 0:
                    print(f"Backlog: ⚠️  {message_count:,} messages waiting")

                    # Show a few sample messages if available
                    print(f"\n📋 SAMPLE MESSAGES (first 3):")
                    print("-" * 40)

                    messages_shown = 0
                    for i in range(min(3, message_count)):
                        method_frame, header_frame, body = self.channel.basic_get(
                            queue=queue_name, auto_ack=False
                        )

                        if method_frame is None:
                            break

                        try:
                            # Try to parse as JSON
                            data = json.loads(body.decode("utf-8"))
                            print(f"{i+1}. Type: {data.get('type', 'Unknown')}")
                            if 'imei' in data:
                                print(f"   IMEI: {data.get('imei')}")
                            if 'command' in data:
                                print(f"   Command: {data.get('command')}")
                            if 'timestamp' in data:
                                print(f"   Timestamp: {data.get('timestamp')}")
                            print(f"   Size: {len(body)} bytes")
                        except json.JSONDecodeError:
                            # Show raw message info
                            preview = body.decode('utf-8', errors='ignore')[:100]
                            print(f"{i+1}. Raw message preview: {preview}...")
                            print(f"   Size: {len(body)} bytes")

                        print("-" * 30)
                        messages_shown += 1

                        # Put message back in queue
                        self.channel.basic_nack(delivery_tag=method_frame.delivery_tag)

                    if message_count > 3:
                        print(f"... and {message_count - 3} more messages")
                else:
                    print("Backlog: ✅ Empty queue")

            except Exception as e:
                # Restore pika logging level in case of exception
                pika_logger.setLevel(logging.WARNING)
                print(f"❌ Queue '{queue_name}' not found or not accessible")
                print(f"Error: {e}")
                return False

            print("=" * 60)
            return True

        except Exception as e:
            logger.error(f"Error inspecting queue '{queue_name}': {e}")
            print(f"❌ Error inspecting queue: {e}")
            return False

    def inspect_queues_by_partial_name(self, search_term):
        """Inspect all queues matching a partial name"""
        try:
            print("\n" + "=" * 70)
            print(f"🔍 SEARCHING FOR QUEUES CONTAINING: '{search_term}'")
            print("=" * 70)

            # Find matching queues
            matching_queues = self.find_queues_by_partial_name(search_term)

            if not matching_queues:
                print(f"❌ No queues found containing '{search_term}'")
                print("💡 Tip: Search is case-insensitive. Try broader terms like 'device', 'error', etc.")
                return False

            # Sort by message count (descending)
            matching_queues.sort(key=lambda x: x['messages'], reverse=True)

            if len(matching_queues) == 1:
                # If only one match, inspect it directly
                queue_name = matching_queues[0]['name']
                print(f"✅ Found 1 matching queue: {queue_name}")
                print("=" * 70)
                return self.inspect_queue_by_name(queue_name)
            else:
                # Multiple matches - show summary and let user choose
                print(f"✅ Found {len(matching_queues)} matching queues:")
                print("")
                print(f"{'#':<3} {'Queue Name':<30} {'Messages':<10} {'Consumers':<10} {'Status':<8}")
                print("-" * 70)

                for i, queue in enumerate(matching_queues, 1):
                    name = queue['name'][:29] if len(queue['name']) > 29 else queue['name']
                    messages = str(queue['messages'])
                    consumers = str(queue['consumers'])
                    status = "🟢 ACTIVE" if queue['consumers'] > 0 else "🔴 IDLE"

                    print(f"{i:<3} {name:<30} {messages:<10} {consumers:<10} {status:<8}")

                print("=" * 70)

                # Ask user which one(s) to inspect
                print("\nOptions:")
                print("a. Inspect all matching queues")
                print("1-{num}. Inspect specific queue by number".format(num=len(matching_queues)))
                print("0. Cancel")

                choice = input(f"\nEnter your choice (0/a/1-{len(matching_queues)}): ").strip().lower()

                if choice == "0":
                    return False
                elif choice == "a":
                    # Inspect all queues
                    for i, queue in enumerate(matching_queues):
                        if i > 0:
                            input("\nPress Enter to continue to next queue...")
                        print(f"\n{'='*20} QUEUE {i+1} of {len(matching_queues)} {'='*20}")
                        self.inspect_queue_by_name(queue['name'])
                    return True
                else:
                    # Inspect specific queue
                    try:
                        queue_index = int(choice) - 1
                        if 0 <= queue_index < len(matching_queues):
                            queue_name = matching_queues[queue_index]['name']
                            print(f"\n{'='*20} INSPECTING: {queue_name} {'='*20}")
                            return self.inspect_queue_by_name(queue_name)
                        else:
                            print(f"❌ Invalid choice. Please enter 1-{len(matching_queues)}")
                            return False
                    except ValueError:
                        print("❌ Invalid input. Please enter a number.")
                        return False

        except Exception as e:
            logger.error(f"Error inspecting queues by partial name '{search_term}': {e}")
            print(f"❌ Error inspecting queues: {e}")
            return False

    # === MENU SYSTEMS ===
    
    def show_command_menu(self, imei: str):
        """Show command selection menu"""
        print("\n" + "=" * 50)
        print("SELECT COMMAND TO SEND:")
        print("=" * 50)

        # Display available commands
        for key, cmd_info in AVAILABLE_COMMANDS.items():
            print(f"{key}. {cmd_info['description']} ({cmd_info['command']})")

        max_choice = len(AVAILABLE_COMMANDS)
        next_choice = max_choice + 1
        print(f"{next_choice}. Enter Custom Command")
        print("0. Back to Main Menu")
        print("=" * 50)

        while True:
            choice = input(f"Enter your choice (0-{next_choice}): ").strip()

            if choice == "0":
                return
            elif choice in AVAILABLE_COMMANDS:
                command = AVAILABLE_COMMANDS[choice]["command"]
                description = AVAILABLE_COMMANDS[choice]["description"]
                print(f"\nSending command: {command} ({description})")
                success = self.send_command(imei, command)
                if success:
                    print("✅ Command sent successfully!")
                else:
                    print("❌ Failed to send command")
                input("\nPress Enter to continue...")
                break
            elif choice == str(next_choice):
                custom_command = input("Enter custom command: ").strip()
                if custom_command:
                    print(f"\nSending custom command: {custom_command}")
                    success = self.send_command(imei, custom_command)
                    if success:
                        print("✅ Command sent successfully!")
                    else:
                        print("❌ Failed to send command")
                    input("\nPress Enter to continue...")
                else:
                    print("❌ No command entered")
                break
            else:
                print(f"Invalid choice. Please enter 0-{next_choice}.")

    def show_set_commands_menu(self, imei: str):
        """Show set commands menu for configuration checking"""
        print("\n" + "=" * 50)
        print("SET COMMANDS (Configuration Checking):")
        print("=" * 50)

        # Display available set commands
        for key, set_info in SET_COMMANDS.items():
            print(f"{key}. {set_info['name']}")

        print("0. Back to Main Menu")
        print("=" * 50)

        while True:
            choice = input(f"Enter your choice (0-{len(SET_COMMANDS)}): ").strip()

            if choice == "0":
                return
            elif choice in SET_COMMANDS:
                set_info = SET_COMMANDS[choice]
                print(f"\n--- {set_info['name']} ---")

                # Send each command in sequence
                for i, cmd_info in enumerate(set_info["commands"], 1):
                    command = cmd_info["command"]
                    description = cmd_info["description"]

                    print(f"\n{i}. {description}")
                    print(f"   Sending: {command}")

                    success = self.send_command(imei, command)
                    if success:
                        print("   ✅ Command sent successfully!")
                    else:
                        print("   ❌ Failed to send command")

                    # Small delay between commands
                    if i < len(set_info["commands"]):
                        time.sleep(1)

                print(f"\n--- Completed {set_info['name']} ---")
                input("\nPress Enter to continue...")
                break
            else:
                print(f"Invalid choice. Please enter 0-{len(SET_COMMANDS)}.")

    def show_monitor_menu(self):
        """Show monitor menu"""
        while True:
            print("\n" + "=" * 50)
            if self.target_imei:
                print(f"MONITORING MENU - IMEI: {self.target_imei}")
            else:
                print("MONITORING MENU - ALL DEVICES")
            print("=" * 50)
            print("1. Check Queue Status (default)")
            print("2. View Messages")
            print("3. Start Consumer")
            print("0. Back to Main Menu")
            print("=" * 50)

            choice = input("Enter your choice (0-3, default=1): ").strip()

            # Default to option 1 if Enter is pressed
            if choice == "":
                choice = "1"

            if choice == "0":
                break
            elif choice == "1":
                self.check_monitor_status()
                input("\nPress Enter to continue...")
            elif choice == "2":
                limit = input("Enter number of messages to peek (default: 5): ").strip()
                try:
                    limit = int(limit) if limit else 5
                except ValueError:
                    limit = 5
                self.peek_messages(limit=limit, show_json=False)
                input("\nPress Enter to continue...")
            elif choice == "3":
                print("Starting real-time monitor... Press Ctrl+C to stop")
                self.monitor_realtime(show_json=False)
                input("\nPress Enter to continue...")
            else:
                print("Invalid choice. Please enter 0-3.")

    def show_commands_menu(self, imei: str):
        """Show commands menu"""
        while True:
            print("\n" + "=" * 50)
            print(f"COMMANDS MENU - IMEI: {imei}")
            print("=" * 50)
            print("1. Send Command")
            print("2. Check Queue Status")
            print("3. List Queue Commands")
            print("4. Purge Queue")
            print("5. Check Duplicate Server Config")
            print("0. Back to Main Menu")
            print("=" * 50)

            choice = input("Enter your choice (0-5): ").strip()

            if choice == "0":
                break
            elif choice == "1":
                self.show_command_menu(imei)
            elif choice == "2":
                self.check_queue_status(imei)
                input("\nPress Enter to continue...")
            elif choice == "3":
                self.list_queue_commands(imei)
                input("\nPress Enter to continue...")
            elif choice == "4":
                self.purge_queue(imei)
                input("\nPress Enter to continue...")
            elif choice == "5":
                self.show_set_commands_menu(imei)
            else:
                print("Invalid choice. Please enter 0-5.")

    def show_queue_operations_menu(self):
        """Show queue operations menu"""
        while True:
            print("\n" + "=" * 50)
            print("QUEUE OPERATIONS MENU")
            print("=" * 50)
            print("1. List Active Queues")
            print("2. List All Queues (including idle)")
            print("3. List Non-IMEI Queues Only")
            print("4. List IMEI Queues Only")
            print("5. Inspect Queue(s) by Name/Partial Match")
            print("0. Back to Main Menu")
            print("=" * 50)

            choice = input("Enter your choice (0-5): ").strip()

            if choice == "0":
                break
            elif choice == "1":
                try:
                    self.list_all_queues("active")
                except Exception as e:
                    print(f"❌ Error listing queues: {e}")
                    logger.error(f"Error in list_all_queues: {e}")
                input("\nPress Enter to continue...")
            elif choice == "2":
                try:
                    self.list_all_queues("all")
                except Exception as e:
                    print(f"❌ Error listing queues: {e}")
                    logger.error(f"Error in list_all_queues: {e}")
                input("\nPress Enter to continue...")
            elif choice == "3":
                try:
                    self.list_all_queues("non-imei")
                except Exception as e:
                    print(f"❌ Error listing queues: {e}")
                    logger.error(f"Error in list_all_queues: {e}")
                input("\nPress Enter to continue...")
            elif choice == "4":
                try:
                    self.list_all_queues("imei-only")
                except Exception as e:
                    print(f"❌ Error listing queues: {e}")
                    logger.error(f"Error in list_all_queues: {e}")
                input("\nPress Enter to continue...")
            elif choice == "5":
                search_term = input("\nEnter queue name or partial name to search: ").strip()
                if search_term:
                    try:
                        # First try exact match
                        try:
                            self.ensure_connection()
                            pika_logger.setLevel(logging.ERROR)
                            queue_info = self.channel.queue_declare(queue=search_term, passive=True)
                            pika_logger.setLevel(logging.WARNING)
                            # Exact match found
                            print(f"✅ Found exact match: {search_term}")
                            success = self.inspect_queue_by_name(search_term)
                        except Exception:
                            # Restore pika logging level
                            pika_logger.setLevel(logging.WARNING)
                            # No exact match, try partial matching
                            print(f"📝 No exact match for '{search_term}', searching for partial matches...")
                            success = self.inspect_queues_by_partial_name(search_term)

                        if not success:
                            print("💡 Tip: Use 'List Active Queues' to see available queues")
                            print("💡 Try broader search terms like: 'device', 'tcp', 'error', 'alert'")
                    except Exception as e:
                        print(f"❌ Error inspecting queue: {e}")
                        logger.error(f"Error in inspect queue operation: {e}")
                else:
                    print("❌ No search term provided")
                input("\nPress Enter to continue...")
            else:
                print("Invalid choice. Please enter 0-5.")

    def get_imei_input(self):
        """Get IMEI from user input"""
        print("\n" + "=" * 50)
        print("IMEI SELECTION")
        print("=" * 50)
        print("1. Enter IMEI")
        print("=" * 50)

        while True:
            choice = input("Enter your choice (1): ").strip()

            if choice == "1":
                imei = input("Enter IMEI (e.g., 350317177240177): ").strip()
                if imei:
                    return imei
                else:
                    print("❌ No IMEI entered")
            else:
                print("Invalid choice. Please enter 1.")

    def show_main_menu(self):
        """Show main menu and handle user input"""
        while True:
            print("\n" + "=" * 50)
            print("RABBITMQ QUEUE MANAGER")
            if self.target_imei:
                print(f"Current IMEI: {self.target_imei}")
            else:
                print("Current IMEI: Not set")
            print("=" * 50)
            print("1. Monitor")
            print("2. Commands")
            print("3. Queue Operations")
            print("0. Exit")
            print("=" * 50)

            choice = input("Enter your choice (0-3): ").strip()

            if choice == "0":
                print("Goodbye!")
                break
            elif choice == "1":
                self.show_monitor_menu()
            elif choice == "2":
                if not self.target_imei:
                    print("\n❌ IMEI is required for command operations")
                    imei = self.get_imei_input()
                    if imei:
                        self.target_imei = imei
                    else:
                        print("❌ Command operations require an IMEI")
                        continue
                self.show_commands_menu(self.target_imei)
            elif choice == "3":
                self.show_queue_operations_menu()
            else:
                print("Invalid choice. Please enter 0-3.")


def main():
    parser = argparse.ArgumentParser(
        description="RabbitMQ Queue Manager"
    )
    parser.add_argument(
        "--imei", "-i",
        type=str,
        help="IMEI of the target device (e.g., 350317177240177)",
    )

    args = parser.parse_args()

    interface = RabbitMQInterface()
    
    # Set target IMEI if specified
    if args.imei:
        interface.target_imei = args.imei

    try:
        interface.connect()
        interface.show_main_menu()

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        interface.close()


if __name__ == "__main__":
    main()