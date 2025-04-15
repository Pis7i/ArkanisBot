import asyncio
import traceback
from datetime import datetime, timedelta
from telethon.tl.custom import Button
from utils.logger import logger
from core.session import session_manager
from .menu import send_menu_message  # Import the send_menu_message function
from telethon import TelegramClient
from telethon.sessions import StringSession
from utils.security import security_manager  # Fix import path
from utils.error_handler import error_handler

MAX_RUNTIME = timedelta(hours=3)  # Maximum 3 hours runtime

def log_function_entry_exit(func):
    """Decorator to log function entry and exit"""
    async def wrapper(*args, **kwargs):
        func_name = func.__name__
        logger.debug(f"Entering function: {func_name}")
        try:
            result = await func(*args, **kwargs)
            logger.debug(f"Exiting function: {func_name} (Success)")
            return result
        except Exception as e:
            logger.error(f"Error in function {func_name}:")
            logger.error(f"Error message: {str(e)}")
            logger.error("Stack trace:")
            for line in traceback.format_exc().split('\n'):
                logger.error(line)
            logger.debug(f"Exiting function: {func_name} (Error)")
            raise
    return wrapper

@error_handler
async def run_autoforward_task(instance, client):
    """Run the auto forwarding task"""
    config = instance.autoforward_config
    status = instance.autoforward_status
    
    try:
        logger.info(f"Starting autoforward task for user {instance.user_id}")
        logger.debug(f"Initial config: {config}")
        logger.debug(f"Initial status: {status}")
        
        start_time = datetime.utcnow()
        try:
            status.update({
                'running': True,
                'start_time': start_time.isoformat(),
                'messages_sent': 0,
                'last_forward': None,
                'errors': 0
            })
            logger.debug(f"Updated status: {status}")
        except Exception as e:
            logger.error(f"Error updating status: {str(e)}", exc_info=True)
            raise
        
        # Validate configuration
        source_message = config.get('source_message')
        target_chats = config.get('target_chats', [])
        test_group = config.get('test_group')
        bypass_groups = config.get('bypass_groups', [])
        
        logger.debug(f"Source message: {source_message}")
        logger.debug(f"Target chats: {target_chats}")
        logger.debug(f"Test group: {test_group}")
        logger.debug(f"Bypass groups: {bypass_groups}")
        
        # Source message is required
        if not source_message:
            logger.error(f"No source message configured for user {instance.user_id}")
            status.update({
                'running': False,
                'error': 'No source message configured',
                'stop_time': datetime.utcnow().isoformat()
            })
            return
            
        # Need at least one target (either test group or target chats)
        if not test_group and not target_chats:
            logger.error(f"No targets configured for user {instance.user_id}")
            status.update({
                'running': False,
                'error': 'No target chats configured',
                'stop_time': datetime.utcnow().isoformat()
            })
            return
        
        # Get the message(s) to forward
        try:
            messages = await get_messages_to_forward(client, source_message)
        except Exception as e:
            logger.error(f"Failed to get source message(s): {str(e)}", exc_info=True)
            status.update({
                'running': False,
                'error': str(e),
                'stop_time': datetime.utcnow().isoformat()
            })
            return
        
        # Get delay from configuration (convert minutes to seconds)
        delay = config.get('delay', 600) * 60  # Convert minutes to seconds (default 10 minutes)
        logger.debug(f"Using delay of {delay} seconds ({delay/60} minutes) between forwards")
        
        # Main forwarding loop - runs until stopped or max time reached
        while status['running']:
            current_time = datetime.utcnow()
            
            # Check if max runtime reached
            if current_time - start_time >= MAX_RUNTIME:
                logger.info(f"Maximum runtime reached for user {instance.user_id}")
                status.update({
                    'running': False,
                    'stop_reason': 'max_runtime_reached',
                    'stop_time': current_time.isoformat()
                })
                break
            
            try:
                # Create unique set of targets to avoid duplicates, excluding bypass groups
                targets = set(chat_id for chat_id in target_chats if chat_id not in bypass_groups)
                if test_group and test_group not in bypass_groups:
                    targets.add(test_group)
                
                # Forward to each target
                for target in targets:
                    try:
                        # Forward all messages together to maintain album grouping
                        await client.forward_messages(target, messages)
                        status['messages_sent'] += len(messages)
                        status['last_forward'] = current_time.isoformat()
                        logger.info(f"Forwarded {len(messages)} message(s) to target {target}")
                    except Exception as e:
                        logger.error(f"Failed to forward to target {target}: {str(e)}")
                        status['errors'] += 1
                        if status['errors'] >= 5:  # Stop if too many errors
                            status.update({
                                'running': False,
                                'stop_reason': 'too_many_errors',
                                'error': str(e),
                                'stop_time': current_time.isoformat()
                            })
                            return
                        continue
                
                # Sleep between iterations
                if status['running']:
                    next_forward_time = current_time + timedelta(seconds=delay)
                    status['next_forward'] = next_forward_time.isoformat()
                    logger.debug(f"Sleeping for {delay} seconds until {next_forward_time}")
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        logger.info(f"Task cancelled during sleep for user {instance.user_id}")
                        raise
            
            except asyncio.CancelledError:
                logger.info(f"Task cancelled for user {instance.user_id}")
                status.update({
                    'running': False,
                    'stop_reason': 'cancelled',
                    'stop_time': datetime.utcnow().isoformat()
                })
                raise
            except Exception as e:
                logger.error(f"Error in forwarding iteration: {str(e)}")
                status['errors'] += 1
                if status['errors'] >= 5:  # Stop if too many errors
                    status.update({
                        'running': False,
                        'stop_reason': 'too_many_errors',
                        'error': str(e),
                        'stop_time': datetime.utcnow().isoformat()
                    })
                    return
                continue
        
        # Task completed or stopped
        if status['running']:  # If we haven't set a stop reason yet
            status.update({
                'running': False,
                'stop_reason': 'completed',
                'stop_time': datetime.utcnow().isoformat()
            })
        logger.info(f"Autoforward task completed for user {instance.user_id}")
        
    except asyncio.CancelledError:
        logger.info(f"Autoforward task cancelled for user {instance.user_id}")
        status.update({
            'running': False,
            'stop_reason': 'cancelled',
            'stop_time': datetime.utcnow().isoformat()
        })
        raise
    except Exception as e:
        logger.error(f"Autoforward task failed: {str(e)}", exc_info=True)
        status.update({
            'running': False,
            'error': str(e),
            'stop_reason': 'task_error',
            'stop_time': datetime.utcnow().isoformat()
        })

@log_function_entry_exit
async def get_messages_to_forward(client, source_message):
    """Helper function to get messages to forward"""
    try:
        logger.debug(f"Getting messages to forward from source: {source_message}")
        
        # Handle both dict and integer source_message formats
        if isinstance(source_message, dict):
            message_id = source_message.get('id')
            is_album = source_message.get('is_album', False)
        else:
            message_id = source_message
            is_album = False
            
        if not message_id:
            raise ValueError("Invalid message ID")
            
        logger.debug(f"Processing message_id: {message_id}, is_album: {is_album}")
        
        if is_album:
            logger.debug("Processing album message")
            # For albums, we need to get all messages with the same grouped_id
            first_message = await client.get_messages('me', ids=[message_id])
            if not first_message or not first_message[0]:
                raise ValueError("Album first message not found")
            first_message = first_message[0]
            
            # Get the grouped_id from the first message
            grouped_id = first_message.grouped_id
            if not grouped_id:
                raise ValueError("Album ID not found")
            
            logger.debug(f"Found album with grouped_id: {grouped_id}")
            
            # Get all messages from this album
            album_messages = []
            async for msg in client.iter_messages('me', limit=50):
                if hasattr(msg, 'grouped_id') and msg.grouped_id == grouped_id:
                    album_messages.append(msg)
                if len(album_messages) >= source_message.get('album_length', 10):
                    break
            
            if not album_messages:
                raise ValueError("No album messages found")
            
            # Sort messages by ID to maintain order
            album_messages.sort(key=lambda x: x.id)
            messages = album_messages
            logger.debug(f"Found {len(messages)} messages in album")
        else:
            logger.debug("Processing single message")
            # For single messages, just get that one message
            message = await client.get_messages('me', ids=[message_id])
            if not message or not message[0]:
                raise ValueError("Message not found")
            messages = [message[0]]
            logger.debug("Successfully retrieved single message")
        
        return messages
    except Exception as e:
        logger.error("Error in get_messages_to_forward:")
        logger.error(f"Error message: {str(e)}")
        logger.error("Stack trace:")
        for line in traceback.format_exc().split('\n'):
            logger.error(line)
        raise

async def get_all_user_groups(client):
    """Get all groups and channels the user is in"""
    groups = []
    try:
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                groups.append({
                    'id': dialog.id,
                    'title': dialog.title
                })
        return groups
    except Exception as e:
        logger.error(f"Error getting user groups: {str(e)}")
        return []

@error_handler
async def start_autoforward(event, instance):
    """Start the autoforward task for a user"""
    user_id = instance.user_id
    logger.info(f"Starting autoforward for user {user_id}")
    
    try:
        # Load user's session using phone number
        session_data = session_manager.load_session(instance.phone)
        if not session_data:
            logger.error(f"Failed to load session data for user {user_id}")
            await send_menu_message(
                event,
                "❌ Failed to load session.",
                buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
            )
            return False
            
        # Create client from session data
        try:
            session_string = security_manager.decrypt_message(session_data['session'])
            client = TelegramClient(
                StringSession(session_string),
                session_data['api_id'],
                session_data['api_hash'],
                device_model="ArkanisUserBot",
                system_version="1.0",
                app_version="1.0"
            )
            await client.connect()
            if not await client.is_user_authorized():
                logger.error(f"Client not authorized for user {user_id}")
                await send_menu_message(
                    event,
                    "❌ Session expired. Please log in again.",
                    buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
                )
                return False
        except Exception as e:
            logger.error(f"Failed to create client for user {user_id}: {str(e)}")
            await send_menu_message(
                event,
                "❌ Failed to initialize session.",
                buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
            )
            return False
            
        logger.debug(f"Session loaded successfully for user {user_id}")
            
        # Validate configuration
        config = instance.autoforward_config
        source_message = config.get('source_message')
        test_group = config.get('test_group')
        bypass_groups = config.get('bypass_groups', [])
        
        logger.debug(f"Configuration loaded - source_message: {source_message}, test_group: {test_group}, bypass_groups: {bypass_groups}")
        
        # Source message is required for autoforwarding
        if not source_message:
            await send_menu_message(
                event,
                "⚠️ Please select a source message first.\n\n"
                "Go to Setup Auto Forward and select a message to forward.",
                buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
            )
            return False
            
        # Sync all user groups as target chats
        logger.info(f"Syncing groups for user {user_id}")
        all_groups = await get_all_user_groups(client)
        target_chats = [group['id'] for group in all_groups if group['id'] not in bypass_groups]
        config['target_chats'] = target_chats
        logger.info(f"Found {len(target_chats)} active groups (excluding {len(bypass_groups)} bypassed groups) for user {user_id}")
        
        # Create and start the task
        logger.debug(f"Creating autoforward task for user {user_id}")
        instance.autoforward_task = asyncio.create_task(run_autoforward_task(instance, client))
        instance.autoforward_status['task'] = instance.autoforward_task
        logger.debug(f"Task created successfully for user {user_id}")
        
        # Build status message
        targets_info = []
        if test_group and test_group not in bypass_groups:
            targets_info.append("Test Group")
        if target_chats:
            targets_info.append(f"{len(target_chats)} Target Groups")
        if bypass_groups:
            targets_info.append(f"{len(bypass_groups)} Bypassed Groups")
        targets_str = ", ".join(targets_info)
        
        # Update UI
        await send_menu_message(
            event,
            f"✅ **Auto Forward Started**\n\n"
            f"The bot will forward messages to {targets_str}.\n"
            "Maximum runtime: 3 hours\n\n"
            "Use the menu to check status or stop forwarding.",
            buttons=[
                [Button.inline("📊 Check Status", "autoforward_status")],
                [Button.inline("⏹ Stop Forwarding", "autoforward_stop")],
                [Button.inline("🔙 Back", "autoforward_menu")]
            ]
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error in start_autoforward for user {user_id}:")
        logger.error(f"Error message: {str(e)}")
        logger.error("Stack trace:")
        for line in traceback.format_exc().split('\n'):
            logger.error(line)
        await send_menu_message(
            event,
            "❌ Failed to start auto forwarding.\n"
            f"Error: {str(e)}",
            buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
        )
        return False

@log_function_entry_exit
async def start_test_forward(event, instance, use_custom_delay: bool = False):
    """Start test forwarding to selected group"""
    user_id = instance.user_id
    logger.info(f"Starting test forward for user {user_id}")
    
    try:
        # Load user's session using phone number
        session_data = session_manager.load_session(instance.phone)  # This is not async
        if not session_data:
            logger.error(f"Failed to load session data for user {user_id}")
            await send_menu_message(
                event,
                "❌ Failed to load session.",
                buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
            )
            return False
            
        # Create client from session data
        try:
            session_string = security_manager.decrypt_message(session_data['session'])
            client = TelegramClient(
                StringSession(session_string),
                session_data['api_id'],
                session_data['api_hash'],
                device_model="ArkanisUserBot",
                system_version="1.0",
                app_version="1.0"
            )
            await client.connect()
            if not await client.is_user_authorized():
                logger.error(f"Client not authorized for user {user_id}")
                await send_menu_message(
                    event,
                    "❌ Session expired. Please log in again.",
                    buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
                )
                return False
        except Exception as e:
            logger.error(f"Failed to create client for user {user_id}: {str(e)}")
            await send_menu_message(
                event,
                "❌ Failed to initialize session.",
                buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
            )
            return False
        
        # Validate configuration
        config = instance.autoforward_config
        source_message = config.get('source_message')
        test_group = config.get('test_group')
        
        # Validate required settings for test forward
        if not source_message:
            await send_menu_message(
                event,
                "⚠️ Please select a source message first.\n\n"
                "Go to Setup Auto Forward and select a message to forward.",
                buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
            )
            return False
            
        if not test_group:
            await send_menu_message(
                event,
                "⚠️ Please select a test group first.\n\n"
                "Go to Setup Auto Forward and select a group for testing.",
                buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
            )
            return False
        
        try:
            # Get the messages to forward using the helper function
            messages = await get_messages_to_forward(client, source_message)
            
            # Get delay from configuration (convert minutes to seconds)
            delay = config.get('test_delay' if use_custom_delay else 'delay', 600) * 60  # Convert minutes to seconds
            logger.debug(f"Using delay of {delay} seconds ({delay/60} minutes) for test forward")
            
            # Send status message
            await send_menu_message(
                event,
                "🧪 **Test Forward Started**\n\n"
                f"• Messages to forward: {len(messages)}\n"
                f"• Delay: {delay // 60} minutes\n"
                "• Status: Waiting for delay...\n\n"
                "The test will run once with your configured delay.",
                buttons=[[Button.inline("❌ Cancel Test", "test_forward_stop")]]
            )
            
            # Update status
            instance.autoforward_status.update({
                'test_running': True,
                'test_start_time': datetime.utcnow().isoformat(),
                'test_messages': len(messages)
            })
            
            # Wait for delay
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                logger.info(f"Test forward cancelled for user {user_id}")
                instance.autoforward_status['test_running'] = False
                await send_menu_message(
                    event,
                    "❌ Test forward cancelled.",
                    buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
                )
                return False
            
            # Check if test was stopped
            if not instance.autoforward_status.get('test_running'):
                return False
            
            # Update status
            await send_menu_message(
                event,
                "🧪 **Test Forward**\n\n"
                "• Status: Forwarding messages..."
            )
            
            # Forward messages
            success_count = 0
            for message in messages:
                try:
                    await client.forward_messages(test_group, message)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error forwarding message in test: {str(e)}")
                    logger.error("Stack trace:")
                    for line in traceback.format_exc().split('\n'):
                        logger.error(line)
                    continue
            
            # Update final status
            instance.autoforward_status.update({
                'test_running': False,
                'test_end_time': datetime.utcnow().isoformat(),
                'test_success_count': success_count
            })
            
            # Show success message
            await send_menu_message(
                event,
                "✅ **Test Forward Complete**\n\n"
                f"• Messages Sent: {success_count}/{len(messages)}\n"
                f"• Delay Used: {delay // 60} minutes\n\n"
                "You can now start regular forwarding or run another test.",
                buttons=[
                    [Button.inline("▶️ Start Auto Forward", "autoforward_start")],
                    [Button.inline("🔄 Test Again", "test_forward_start")],
                    [Button.inline("🔙 Back", "autoforward_menu")]
                ]
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error in test forward for user {user_id}:")
            logger.error(f"Error message: {str(e)}")
            logger.error("Stack trace:")
            for line in traceback.format_exc().split('\n'):
                logger.error(line)
            await send_menu_message(
                event,
                "❌ Failed to forward message(s).\n"
                f"Error: {str(e)}",
                buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
            )
            return False
            
    except Exception as e:
        logger.error(f"Error in test forward for user {user_id}:")
        logger.error(f"Error message: {str(e)}")
        logger.error("Stack trace:")
        for line in traceback.format_exc().split('\n'):
            logger.error(line)
        await send_menu_message(
            event,
            "❌ An error occurred during test forward.",
            buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
        )
        return False

@error_handler
async def stop_autoforward(event, instance):
    """Stop the autoforward task for a user"""
    user_id = instance.user_id
    logger.info(f"Stopping autoforward for user {user_id}")
    
    try:
        # Always update status if it shows as running
        if instance.autoforward_status.get('running', False):
            instance.autoforward_status.update({
                'running': False,
                'stop_time': datetime.now().isoformat(),
                'stop_reason': 'cancelled'
            })
            
            # Try to cancel task if it exists
            task = instance.autoforward_status.get('task')
            if task:
                task.cancel()
                instance.autoforward_status['task'] = None
                logger.info(f"Active task cancelled for user {user_id}")
            else:
                logger.warning(f"No active task found for user {user_id}")
            
            logger.info(f"Autoforward stopped for user {user_id}")
            return True
        else:
            logger.info(f"Autoforward was not running for user {user_id}")
            return True
            
    except Exception as e:
        logger.error(f"Error in stop_autoforward for user {user_id}:")
        logger.error(f"Error type: {type(e)}")
        logger.error(f"Error message: {str(e)}")
        logger.error("Full stack trace:", exc_info=True)
        logger.error(f"Instance state: {instance.__dict__}")
        
        try:
            # Emergency cleanup
            instance.autoforward_status.update({
                'running': False,
                'stop_time': datetime.now().isoformat(),
                'stop_reason': 'error'
            })
            task = instance.autoforward_status.get('task')
            if task:
                task.cancel()
                instance.autoforward_status['task'] = None
                logger.info("Emergency task cleanup successful")
        except Exception as cleanup_e:
            logger.error(f"Error in emergency task cleanup: {str(cleanup_e)}")
        
        logger.error(f"Failed to stop autoforward task for user {user_id}")
        return False

async def handle_setup_complete(event, instance):
    """Handle completion of autoforward setup"""
    user_id = instance.user_id
    logger.info(f"Completing autoforward setup for user {user_id}")
    
    try:
        # Save configuration from setup state
        setup_state = instance.setup_state
        instance.autoforward_config = setup_state['config'].copy()
        instance.autoforward_status = {
            'running': False,
            'last_forward': None,
            'next_forward': None
        }
        instance.setup_state = {}  # Clear setup state
        
        # Show success message
        await event.edit(
            "✅ **Auto-Forward Setup Complete!**\n\n"
            "Your configuration has been saved.\n"
            "You can now start forwarding or run a test.",
            buttons=[
                [Button.inline("▶️ Start Forwarding", "autoforward_start")],
                [Button.inline("🔄 Test Forward", "test_forward_start")],
                [Button.inline("🔙 Back", "autoforward_menu")]
            ],
            parse_mode='markdown'
        )
        logger.info(f"Autoforward setup completed for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error completing setup for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred saving configuration", alert=True)
        return False

@error_handler
async def handle_bypass_groups_menu(event, instance):
    """Show the bypass groups management menu"""
    user_id = instance.user_id
    logger.info(f"Showing bypass groups menu for user {user_id}")
    
    try:
        # Load user's session
        session_data = session_manager.load_session(instance.phone)
        if not session_data:
            await send_menu_message(
                event,
                "❌ Failed to load session.",
                buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
            )
            return False
            
        # Create client
        try:
            session_string = security_manager.decrypt_message(session_data['session'])
            client = TelegramClient(
                StringSession(session_string),
                session_data['api_id'],
                session_data['api_hash'],
                device_model="ArkanisUserBot",
                system_version="1.0",
                app_version="1.0"
            )
            await client.connect()
            if not await client.is_user_authorized():
                await send_menu_message(
                    event,
                    "❌ Session expired. Please log in again.",
                    buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
                )
                return False
        except Exception as e:
            logger.error(f"Failed to create client: {str(e)}")
            await send_menu_message(
                event,
                "❌ Failed to initialize session.",
                buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
            )
            return False
            
        # Get all groups and current bypass groups
        all_groups = await get_all_user_groups(client)
        bypass_groups = instance.autoforward_config.get('bypass_groups', [])
        
        # Create message showing current bypass groups
        message = "🚫 **Bypass Groups Management**\n\n"
        if bypass_groups:
            message += "Currently bypassed groups:\n"
            for group in all_groups:
                if group['id'] in bypass_groups:
                    message += f"• {group['title']}\n"
            message += "\n"
        else:
            message += "No groups are currently bypassed.\n\n"
        
        message += "Select an action below to manage bypass groups."
        
        # Create buttons
        buttons = [
            [Button.inline("➕ Add Groups", "bypass_add_groups")],
            [Button.inline("➖ Remove Groups", "bypass_remove_groups")],
            [Button.inline("🗑 Clear All", "bypass_clear_all")],
            [Button.inline("🔙 Back", "autoforward_menu")]
        ]
        
        await send_menu_message(event, message, buttons=buttons)
        return True
        
    except Exception as e:
        logger.error(f"Error showing bypass groups menu: {str(e)}")
        await send_menu_message(
            event,
            "❌ An error occurred showing bypass groups menu.",
            buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
        )
        return False

@error_handler
async def handle_bypass_add_groups(event, instance):
    """Show menu to add groups to bypass list"""
    user_id = instance.user_id
    logger.info(f"Showing add bypass groups menu for user {user_id}")
    
    try:
        # Load user's session and create client
        session_data = session_manager.load_session(instance.phone)
        if not session_data:
            await send_menu_message(
                event,
                "❌ Failed to load session.",
                buttons=[[Button.inline("🔙 Back", "bypass_groups_menu")]]
            )
            return False
            
        session_string = security_manager.decrypt_message(session_data['session'])
        client = TelegramClient(
            StringSession(session_string),
            session_data['api_id'],
            session_data['api_hash']
        )
        await client.connect()
        
        # Get all groups and current bypass groups
        all_groups = await get_all_user_groups(client)
        bypass_groups = instance.autoforward_config.get('bypass_groups', [])
        
        # Create buttons for non-bypassed groups
        buttons = []
        for group in all_groups:
            if group['id'] not in bypass_groups:
                # Create callback data with group info
                callback_data = f"add_bypass_{group['id']}"
                buttons.append([Button.inline(f"➕ {group['title']}", callback_data)])
        
        if not buttons:
            message = "❌ No available groups to bypass.\nAll groups are already in bypass list."
            buttons = [[Button.inline("🔙 Back", "bypass_groups_menu")]]
        else:
            message = "Select groups to add to bypass list:"
            buttons.append([Button.inline("🔙 Back", "bypass_groups_menu")])
        
        await send_menu_message(event, message, buttons=buttons)
        return True
        
    except Exception as e:
        logger.error(f"Error showing add bypass groups menu: {str(e)}")
        await send_menu_message(
            event,
            "❌ An error occurred.",
            buttons=[[Button.inline("🔙 Back", "bypass_groups_menu")]]
        )
        return False

@error_handler
async def handle_bypass_remove_groups(event, instance):
    """Show menu to remove groups from bypass list"""
    user_id = instance.user_id
    logger.info(f"Showing remove bypass groups menu for user {user_id}")
    
    try:
        # Load user's session and create client
        session_data = session_manager.load_session(instance.phone)
        if not session_data:
            await send_menu_message(
                event,
                "❌ Failed to load session.",
                buttons=[[Button.inline("🔙 Back", "bypass_groups_menu")]]
            )
            return False
            
        session_string = security_manager.decrypt_message(session_data['session'])
        client = TelegramClient(
            StringSession(session_string),
            session_data['api_id'],
            session_data['api_hash']
        )
        await client.connect()
        
        # Get all groups and current bypass groups
        all_groups = await get_all_user_groups(client)
        bypass_groups = instance.autoforward_config.get('bypass_groups', [])
        
        # Create buttons for bypassed groups
        buttons = []
        for group in all_groups:
            if group['id'] in bypass_groups:
                # Create callback data with group info
                callback_data = f"remove_bypass_{group['id']}"
                buttons.append([Button.inline(f"➖ {group['title']}", callback_data)])
        
        if not buttons:
            message = "❌ No groups in bypass list."
            buttons = [[Button.inline("🔙 Back", "bypass_groups_menu")]]
        else:
            message = "Select groups to remove from bypass list:"
            buttons.append([Button.inline("🔙 Back", "bypass_groups_menu")])
        
        await send_menu_message(event, message, buttons=buttons)
        return True
        
    except Exception as e:
        logger.error(f"Error showing remove bypass groups menu: {str(e)}")
        await send_menu_message(
            event,
            "❌ An error occurred.",
            buttons=[[Button.inline("🔙 Back", "bypass_groups_menu")]]
        )
        return False

@error_handler
async def handle_bypass_group_action(event, instance, action: str, group_id: int):
    """Handle adding or removing a group from bypass list"""
    user_id = instance.user_id
    logger.info(f"Handling bypass group action for user {user_id}: {action} {group_id}")
    
    try:
        bypass_groups = instance.autoforward_config.get('bypass_groups', [])
        
        if action == "add":
            if group_id not in bypass_groups:
                bypass_groups.append(group_id)
                instance.autoforward_config['bypass_groups'] = bypass_groups
                await event.answer("✅ Group added to bypass list", alert=True)
        elif action == "remove":
            if group_id in bypass_groups:
                bypass_groups.remove(group_id)
                instance.autoforward_config['bypass_groups'] = bypass_groups
                await event.answer("✅ Group removed from bypass list", alert=True)
        
        # Refresh the menu
        if action == "add":
            await handle_bypass_add_groups(event, instance)
        else:
            await handle_bypass_remove_groups(event, instance)
        
        return True
        
    except Exception as e:
        logger.error(f"Error handling bypass group action: {str(e)}")
        await event.answer("❌ Failed to update bypass list", alert=True)
        return False

@error_handler
async def handle_bypass_clear_all(event, instance):
    """Clear all groups from bypass list"""
    user_id = instance.user_id
    logger.info(f"Clearing all bypass groups for user {user_id}")
    
    try:
        instance.autoforward_config['bypass_groups'] = []
        await event.answer("✅ All groups removed from bypass list", alert=True)
        await handle_bypass_groups_menu(event, instance)
        return True
        
    except Exception as e:
        logger.error(f"Error clearing bypass groups: {str(e)}")
        await event.answer("❌ Failed to clear bypass list", alert=True)
        return False 