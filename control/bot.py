import json
import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from utils.logger import logger
from utils.whitelist import whitelist_manager
from core.session import session_manager
from utils.chat_cleaner import chat_cleaner, MessageContext
from .handlers.message_handlers import (
    handle_start_command,
    handle_help_command,
    handle_status_command,
    handle_logout_command
)
from .handlers.callback_handlers import handle_callback_query
from .auth import (
    ensure_gateway_auth_initialized,
    handle_auth_state
)
from .modules.user_instance import UserInstance
import os
from dotenv import load_dotenv
import sys

class ControlBot:
    def __init__(self, api_id, api_hash, bot_token):
        """Initialize the ControlBot"""
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.client = None
        self.user_instances = {}
        self.auth_states = {}
        self._load_instances()
        self.last_action = {}  # Track last action time for each user
    
    def _load_instances(self):
        """Load user instances from storage"""
        try:
            with open('data/instances.json', 'r') as f:
                data = json.load(f)
                for user_id, instance_data in data.items():
                    self.user_instances[int(user_id)] = UserInstance.from_dict(instance_data)
            logger.info(f"Loaded {len(self.user_instances)} user instances")
        except FileNotFoundError:
            logger.info("No saved instances found")
        except Exception as e:
            logger.error(f"Error loading instances: {str(e)}", exc_info=True)
    
    def _save_instances(self):
        """Save user instances to storage"""
        try:
            # Create data directory if it doesn't exist
            os.makedirs('data', exist_ok=True)
            
            data = {
                str(user_id): instance.to_dict()
                for user_id, instance in self.user_instances.items()
            }
            with open('data/instances.json', 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self.user_instances)} user instances")
        except Exception as e:
            logger.error(f"Error saving instances: {str(e)}", exc_info=True)
    
    async def _ensure_authenticated(self, event):
        """Ensure user is authenticated"""
        user_id = event.sender_id
        
        # Check if user is whitelisted
        if not whitelist_manager.is_whitelisted(user_id):
            logger.warning(f"Non-whitelisted user {user_id} attempted to use bot")
            await event.respond(
                "⚠️ Access denied. You are not authorized to use this bot.\n"
                "Please contact the administrator for access."
            )
            return False
        
        # Check if user is authenticated
        if user_id not in self.user_instances or not self.user_instances[user_id].authenticated:
            logger.warning(f"Unauthenticated user {user_id} attempted to use bot")
            await event.respond(
                "⚠️ You are not authenticated.\n"
                "Please use /start to authenticate."
            )
            return False
        
        # Update last activity
        self.user_instances[user_id].last_activity = datetime.utcnow()
        self._save_instances()
        return True
    
    async def _ensure_clean_chat(self, event) -> None:
        """Ensure chat is clean before processing any action"""
        try:
            user_id = event.sender_id
            current_time = datetime.now()
            last_time = self.last_action.get(user_id)

            # Log the time difference if there was a previous action
            if last_time:
                time_diff = (current_time - last_time).total_seconds()
                logger.info(f"Time since last action for user {user_id}: {time_diff:.2f} seconds")
            else:
                logger.info(f"First action from user {user_id} in this session")

            # If this is first action or it's been more than 5 minutes since last action
            if not last_time or (current_time - last_time).total_seconds() > 300:  # 5 minutes
                logger.info(f"Cleaning chat for user {user_id} - {'First action' if not last_time else 'Inactive for >5min'}")
                await chat_cleaner.clean_messages(
                    event.client,
                    user_id,
                    event.chat_id,
                    context_filter={MessageContext.MENU, MessageContext.COMMAND, MessageContext.TEMP}
                )
                logger.info(f"Chat cleaned successfully for user {user_id}")
            else:
                logger.debug(f"Skipping chat clean for user {user_id} - Recent activity")
            
            # Update last action time
            self.last_action[user_id] = current_time

        except Exception as e:
            logger.error(f"Error in _ensure_clean_chat for user {user_id}: {str(e)}", exc_info=True)
    
    async def _handle_message(self, event):
        """Handle incoming messages"""
        user_id = event.sender_id
        message = event.message
        logger.info(f"Received message from user {user_id}: {message.message}")
        
        try:
            # Track command messages
            if message.text and message.text.startswith('/'):
                await chat_cleaner.track_message(
                    message,
                    user_id,
                    MessageContext.COMMAND
                )

            # Check if user is in setup state
            if user_id in self.user_instances and hasattr(self.user_instances[user_id], 'state'):
                instance = self.user_instances[user_id]
                if instance.state and instance.state.get('waiting_for') == 'custom_delay':
                    try:
                        delay = int(message.message.strip())
                        if delay < 8:
                            msg = await event.respond(
                                "⚠️ Minimum delay is 8 minutes. Please enter a larger value:",
                                buttons=[[Button.inline("🔙 Back", "autoforward_setup_menu")]]
                            )
                            await chat_cleaner.track_message(msg, user_id, MessageContext.TEMP)
                            return
                        
                        # Save the delay
                        if not hasattr(instance, 'autoforward_config'):
                            instance.autoforward_config = {}
                        
                        key = 'test_delay' if instance.state.get('is_test_delay') else 'delay'
                        instance.autoforward_config[key] = delay
                        
                        # Clear state
                        instance.state = {}
                        self._save_instances()
                        
                        # Show confirmation and return to setup menu
                        msg = await event.respond(
                            f"✅ {'Test delay' if key == 'test_delay' else 'Delay'} set to {delay} minutes.",
                            buttons=[[Button.inline("🔙 Back to Setup", "autoforward_setup_menu")]]
                        )
                        await chat_cleaner.track_message(msg, user_id, MessageContext.MENU)
                        return
                    except ValueError:
                        msg = await event.respond(
                            "⚠️ Please enter a valid number:",
                            buttons=[[Button.inline("🔙 Back", "autoforward_setup_menu")]]
                        )
                        await chat_cleaner.track_message(msg, user_id, MessageContext.TEMP)
                        return
            
            # Check if user is in auth state
            if user_id in self.auth_states:
                await handle_auth_state(event, self)
                return
            
            # Handle commands
            if message.message.startswith('/'):
                command = message.message.split()[0].lower()
                if command == '/start':
                    await handle_start_command(event, self)
                elif command == '/help':
                    await handle_help_command(event, self)
                elif command == '/status':
                    await handle_status_command(event, self)
                elif command == '/logout':
                    await handle_logout_command(event, self)
                else:
                    logger.warning(f"Unknown command from user {user_id}: {command}")
                    msg = await event.respond("⚠️ Unknown command. Use /help to see available commands.")
                    await chat_cleaner.track_message(msg, user_id, MessageContext.TEMP)
            
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}", exc_info=True)
            msg = await event.respond("❌ An error occurred. Please try again.")
            await chat_cleaner.track_message(msg, user_id, MessageContext.TEMP)
    
    async def start(self):
        """Start the bot"""
        try:
            # Initialize the client
            self.client = TelegramClient('controlbot', self.api_id, self.api_hash)
            await self.client.start(bot_token=self.bot_token)
            
            # Register message handler
            @self.client.on(events.NewMessage())
            async def message_wrapper(event):
                await self._handle_message(event)
            
            # Register callback handler
            @self.client.on(events.CallbackQuery())
            async def callback_wrapper(event):
                await handle_callback_query(event, self)
            
            logger.info("Bot started successfully")
            
            # Keep the bot running
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Error starting bot: {str(e)}", exc_info=True)
            raise

    async def stop(self):
        """Stop the bot and cleanup all resources"""
        logger.info("=== Starting ControlBot Cleanup ===")
        sys.stdout.flush()
        
        try:
            # Stop chat cleaner
            await chat_cleaner.shutdown()
            
            # Log initial state
            active_instances = len(self.user_instances)
            running_tasks = sum(1 for instance in self.user_instances.values() 
                              if instance.autoforward_status.get('running', False))
            logger.info(f"Found {active_instances} total instances, {running_tasks} running autoforward tasks")
            sys.stdout.flush()
            
            # Stop all autoforward tasks
            stopped_tasks = 0
            failed_tasks = 0
            for user_id, instance in self.user_instances.items():
                try:
                    if instance.autoforward_status.get('running', False):
                        logger.info(f"\nProcessing user {user_id}...")
                        sys.stdout.flush()
                        
                        # Check if instance has the autoforward_task attribute
                        if hasattr(instance, 'autoforward_task') and instance.autoforward_task:
                            logger.info("- Found active task, attempting to cancel...")
                            sys.stdout.flush()
                            instance.autoforward_task.cancel()
                            await asyncio.sleep(0.1)  # Give task time to cancel
                            instance.autoforward_task = None
                            instance.autoforward_status['task'] = None  # Clear task reference in status
                            logger.info("- Task cancelled successfully")
                            sys.stdout.flush()
                        else:
                            logger.info("- No active task found, updating status only")
                            sys.stdout.flush()
                        
                        # Update status regardless of task state
                        instance.autoforward_status.update({
                            'running': False,
                            'stop_time': datetime.utcnow().isoformat(),
                            'stop_reason': 'bot_shutdown'
                        })
                        
                        # Initialize autoforward_task if it doesn't exist
                        if not hasattr(instance, 'autoforward_task'):
                            instance.autoforward_task = None
                            instance.autoforward_status['task'] = None  # Also initialize task in status
                            logger.info("- Initialized missing autoforward_task attribute")
                            sys.stdout.flush()
                        
                        # Disconnect client if it exists and is connected
                        if hasattr(instance, 'client') and instance.client:
                            try:
                                if instance.client.is_connected():
                                    logger.info("- Disconnecting user's Telegram client...")
                                    await instance.client.disconnect()
                                    logger.info("- User's client disconnected successfully")
                                instance.client = None
                            except Exception as client_error:
                                logger.warning(f"- Error disconnecting user's client: {str(client_error)}")
                                instance.client = None
                        
                        stopped_tasks += 1
                        logger.info("- Status updated and marked as stopped")
                        sys.stdout.flush()
                except Exception as e:
                    logger.error(f"\nFailed to stop task for user {user_id}:")
                    logger.error(f"Error: {str(e)}")
                    sys.stderr.flush()
                    # Try to recover by ensuring the status is updated
                    try:
                        instance.autoforward_status = instance.autoforward_status or {}
                        instance.autoforward_status.update({
                            'running': False,
                            'stop_time': datetime.utcnow().isoformat(),
                            'stop_reason': 'bot_shutdown_error'
                        })
                        if not hasattr(instance, 'autoforward_task'):
                            instance.autoforward_task = None
                            instance.autoforward_status['task'] = None
                        if hasattr(instance, 'client'):
                            instance.client = None
                        logger.info("- Recovered status after error")
                        sys.stdout.flush()
                    except Exception as recovery_error:
                        logger.error(f"- Recovery failed: {str(recovery_error)}")
                        sys.stderr.flush()
                    failed_tasks += 1
            
            logger.info(f"\nTask Cleanup Results:")
            logger.info(f"- {stopped_tasks} tasks stopped successfully")
            logger.info(f"- {failed_tasks} tasks failed to stop")
            sys.stdout.flush()
            
            # Save final state
            logger.info("\nSaving final instance states...")
            sys.stdout.flush()
            self._save_instances()
            logger.info("Instance states saved successfully")
            sys.stdout.flush()
            
            # Disconnect main bot client
            if self.client:
                try:
                    if self.client.is_connected():
                        logger.info("\nDisconnecting main bot client...")
                        sys.stdout.flush()
                        await self.client.disconnect()
                        logger.info("Main bot client disconnected successfully")
                        sys.stdout.flush()
                    else:
                        logger.info("\nMain bot client was already disconnected")
                        sys.stdout.flush()
                except Exception as client_error:
                    logger.warning(f"\nError disconnecting main bot client: {str(client_error)}")
                    sys.stdout.flush()
                finally:
                    self.client = None
            else:
                logger.info("\nNo main bot client instance found (normal during early shutdown)")
                sys.stdout.flush()
            
            logger.info("\n=== ControlBot Cleanup Completed ===")
            sys.stdout.flush()
            
        except Exception as e:
            logger.error("\n=== Error During ControlBot Cleanup ===")
            logger.error(f"Error details: {str(e)}", exc_info=True)
            sys.stderr.flush()
            # Don't re-raise the exception - we want to complete the shutdown even if there are errors

# Create bot instance with credentials from environment
load_dotenv()

control_bot = ControlBot(
    api_id=os.getenv("API_ID"),
    api_hash=os.getenv("API_HASH"),
    bot_token=os.getenv("BOT_TOKEN")
) 