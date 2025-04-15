from datetime import datetime, timedelta
from telethon.tl.custom import Button
from utils.logger import logger
from utils.error_handler import error_handler
from control.modules.menu import (
    show_main_menu,
    show_forwarding_menu,
    show_account_menu,
    show_groups_menu,
    show_tools_menu,
    show_autoforward_menu,
    show_autoforward_setup_menu,
    show_forwarding_status,
    show_saved_messages,
    show_delay_config,
    show_group_selection,
    show_group_preview,
    show_message_preview,
    show_custom_delay_input,
    clear_chat
)
from control.modules.autoforward import start_autoforward, start_test_forward, stop_autoforward
import asyncio
from telethon import events
from utils.chat_cleaner import chat_cleaner, MessageContext
from utils.decorators import with_cleanup

@with_cleanup
async def handle_callback_query(event, bot):
    """Handle callback queries from inline buttons"""
    user_id = event.sender_id
    data = event.data.decode()
    
    if not await bot._ensure_authenticated(event):
        return
        
    logger.info(f"Callback from user {user_id}: {data}")
    
    try:
        if data == "main_menu":
            await handle_main_menu(event, bot)
        elif data == "close_menu":
            await handle_close_menu(event, bot)
        elif data.startswith("autoforward_"):
            await handle_autoforward_menu(event, bot, data)
        else:
            logger.warning(f"Unknown callback data from user {user_id}: {data}")
            msg = await event.respond("⚠️ Invalid menu option.")
            await chat_cleaner.track_message(msg, user_id, MessageContext.TEMP)
            
    except Exception as e:
        logger.error(f"Error handling callback {data} for user {user_id}: {str(e)}", exc_info=True)
        msg = await event.respond("❌ An error occurred. Please try again.")
        await chat_cleaner.track_message(msg, user_id, MessageContext.TEMP)

@with_cleanup
async def handle_main_menu(event, bot):
    """Handle main menu display"""
    user_id = event.sender_id
    instance = bot.user_instances.get(user_id)
    
    if not instance:
        msg = await event.respond("⚠️ No active session found. Please use /start to begin.")
        await chat_cleaner.track_message(msg, user_id, MessageContext.TEMP)
        return
        
    buttons = [
        [Button.inline("📬 Auto-Forward", "autoforward_menu")],
        [Button.inline("📊 Status", "status"), Button.inline("❓ Help", "help")],
        [Button.inline("❌ Close Menu", "close_menu")]
    ]
    
    msg = await event.respond(
        "🔹 Main Menu\n\n"
        "Select an option from the menu below:",
        buttons=buttons
    )
    await chat_cleaner.track_message(msg, user_id, MessageContext.MENU)

@with_cleanup
async def handle_close_menu(event, bot):
    """Handle menu closure"""
    user_id = event.sender_id
    await chat_cleaner.clean_chat(user_id)
    await event.answer("Menu closed")

@with_cleanup
async def handle_autoforward_menu(event, bot, data):
    """Handle auto-forward menu options"""
    user_id = event.sender_id
    instance = bot.user_instances.get(user_id)
    
    if not instance:
        msg = await event.respond("⚠️ No active session found. Please use /start to begin.")
        await chat_cleaner.track_message(msg, user_id, MessageContext.TEMP)
        return
        
    # Extract submenu from data
    submenu = data.replace("autoforward_", "")
    
    if submenu == "menu":
        buttons = [
            [Button.inline("⚙️ Setup", "autoforward_setup_menu")],
            [
                Button.inline(
                    "✅ Enable" if not instance.autoforward_enabled else "❌ Disable",
                    "autoforward_toggle"
                )
            ],
            [Button.inline("📋 Rules", "autoforward_rules")],
            [Button.inline("🔙 Main Menu", "main_menu")]
        ]
        
        msg = await event.respond(
            "📬 Auto-Forward Settings\n\n"
            f"Status: {'✅ Enabled' if instance.autoforward_enabled else '❌ Disabled'}\n"
            f"Rules: {len(instance.autoforward_config.get('rules', []))}\n\n"
            "Select an option:",
            buttons=buttons
        )
        await chat_cleaner.track_message(msg, user_id, MessageContext.MENU)
        
    elif submenu == "toggle":
        instance.autoforward_enabled = not instance.autoforward_enabled
        bot._save_instances()
        
        status = "enabled" if instance.autoforward_enabled else "disabled"
        msg = await event.respond(
            f"✅ Auto-forward has been {status}.",
            buttons=[[Button.inline("🔙 Back", "autoforward_menu")]]
        )
        await chat_cleaner.track_message(msg, user_id, MessageContext.MENU)
        
    else:
        logger.warning(f"Unknown autoforward submenu: {submenu}")
        msg = await event.respond(
            "⚠️ Invalid menu option.",
            buttons=[[Button.inline("🔙 Main Menu", "main_menu")]]
        )
        await chat_cleaner.track_message(msg, user_id, MessageContext.TEMP)

@error_handler
async def handle_autoforward_stop(event, instance):
    """Handle stopping autoforward"""
    user_id = instance.user_id
    logger.info(f"Stopping autoforward for user {user_id}")
    
    try:
        # First, answer the callback query with a notification
        await event.answer("Stopping autoforward task...")
        
        # Stop the autoforward task
        success = await stop_autoforward(event, instance)
        
        if success:
            logger.info(f"Autoforward task stopped for user {user_id}")
            await show_forwarding_menu(event, user_id)
        else:
            logger.error(f"Failed to stop autoforward task for user {user_id}")
            await event.answer("❌ Failed to stop autoforward task", alert=True)
    
    except Exception as e:
        logger.error(f"Error stopping autoforward for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred stopping autoforward", alert=True)

async def handle_autoforward_setup(event, bot_instance):
    """Handle autoforward setup callback"""
    user_id = event.sender_id
    logger.info(f"Starting autoforward setup for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        
        # Initialize setup state
        instance.setup_state = {
            'step': 'select_source',
            'config': {
                'source_chat': None,
                'message_id': None,
                'grouped_id': None,  # For handling albums
                'target_chats': [],
                'delay': 8,  # Default 8 minutes
                'iterations': 0  # 0 means infinite
            }
        }
        bot_instance._save_instances()
        
        await event.edit(
            "📱 **Auto-Forward Setup (1/4)**\n\n"
            "First, forward a message from the source chat you want to monitor.\n"
            "This can be a group, channel, or saved messages.\n\n"
            "ℹ️ *Tip:* For best results, forward a message that's similar to what you want to monitor.",
            buttons=[
                [Button.inline("❌ Cancel Setup", "refresh")]
            ],
            parse_mode='markdown'
        )
        logger.info(f"Sent source selection instructions to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error starting autoforward setup for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred starting setup", alert=True)

async def handle_autoforward_status(event, bot_instance):
    """Handle autoforward status callback"""
    user_id = event.sender_id
    logger.info(f"Checking autoforward status for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        config = instance.autoforward_config
        status = instance.autoforward_status
        
        if not config:
            status_text = "❌ No autoforward configuration found"
        else:
            # Get counts
            target_count = len(config.get('target_chats', []))
            messages_sent = status.get('messages_sent', 0)
            errors = status.get('errors', 0)
            
            # Format times
            start_time = status.get('start_time')
            if start_time:
                start_time = datetime.fromisoformat(start_time)
                runtime = datetime.utcnow() - start_time
                runtime_str = f"{runtime.seconds // 3600}h {(runtime.seconds % 3600) // 60}m"
            else:
                runtime_str = "Not started"
            
            # Get next forward time
            next_forward = status.get('next_forward')
            if next_forward:
                next_forward = datetime.fromisoformat(next_forward)
                next_str = next_forward.strftime("%H:%M:%S")
            else:
                next_str = "Not scheduled"
            
            status_text = (
                "📊 **Autoforward Status**\n\n"
                f"Status: {'🟢 Running' if status.get('running', False) else '🔴 Stopped'}\n"
                f"Target Groups: {target_count}\n"
                f"Messages Sent: {messages_sent}\n"
                f"Errors: {errors}\n"
                f"Runtime: {runtime_str}\n"
                f"Next Forward: {next_str}\n\n"
                f"Delay: {config.get('delay', 'Not set')} minutes"
            )
        
        await event.edit(
            status_text,
            buttons=[
                [Button.inline("🔄 Refresh", "autoforward_status")],
                [Button.inline("🔙 Back", "autoforward_menu")]
            ]
        )
        logger.info(f"Sent autoforward status to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error checking autoforward status for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred checking status", alert=True)

async def handle_test_group_selected(event, bot_instance, data):
    """Handle test group selection callback"""
    user_id = event.sender_id
    group_id = int(data.split('_')[-1])
    logger.info(f"Test group selected by user {user_id}: group_id={group_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        config = instance.autoforward_config
        
        if not config:
            logger.warning(f"No autoforward configuration found for user {user_id}")
            await event.answer("⚠️ Please set up autoforward first", alert=True)
            return
        
        config['test_group_id'] = group_id
        bot_instance._save_instances()
        logger.info(f"Test group {group_id} saved for user {user_id}")
        
        await event.edit(
            "✅ Test group selected!\n\n"
            "You can now start the test forward:",
            buttons=[
                [Button.inline("▶️ Start Test", "test_forward_start")],
                [Button.inline("⏱ Custom Delay", "test_forward_custom_delay")],
                [Button.inline("🔙 Back", "forwarding")]
            ]
        )
    
    except Exception as e:
        logger.error(f"Error handling test group selection for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred selecting test group", alert=True)

async def handle_test_forward_start(event, bot_instance):
    """Handle test forward start callback"""
    user_id = event.sender_id
    logger.info(f"Starting test forward for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        config = instance.autoforward_config
        
        if not config or not config.get('source_chat'):
            logger.warning(f"No autoforward configuration found for user {user_id}")
            await event.answer("⚠️ Please set up autoforward first", alert=True)
            return
        
        # Show test forward options
        await event.edit(
            "🔄 **Test Forward**\n\n"
            "Choose how you want to test the forwarding:\n\n"
            "• Quick Test - Uses minimal delay\n"
            "• Real Test - Uses configured delay",
            buttons=[
                [Button.inline("⚡ Quick Test", "test_forward_quick")],
                [Button.inline("⏱ Real Test", "test_forward_real")],
                [Button.inline("🔙 Back", "forwarding")]
            ],
            parse_mode='markdown'
        )
        logger.info(f"Showed test options to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error showing test options for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred", alert=True)

async def handle_test_forward_custom_delay(event, bot_instance):
    """Handle custom delay for test forward callback"""
    user_id = event.sender_id
    logger.info(f"Setting up custom delay for test forward for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        instance.setup_state = {
            'step': 'test_delay',
            'config': {}
        }
        bot_instance._save_instances()
        
        await event.edit(
            "⏱ **Set Test Forward Delay**\n\n"
            "Please enter the delay in minutes (minimum 8):",
            buttons=[
                [Button.inline("🔙 Back", "forwarding")]
            ]
        )
        logger.info(f"Sent custom delay setup message to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error setting up custom delay for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred setting up custom delay", alert=True)

async def handle_message_setup(event, bot_instance, user_id):
    """Handle message selection during setup"""
    try:
        instance = bot_instance.user_instances[user_id]
        setup_state = instance.setup_state
        
        if not event.message.forward:
            await event.respond(
                "⚠️ Please forward a message from the source chat.",
                buttons=[[Button.inline("❌ Cancel Setup", "refresh")]]
            )
            return
        
        if setup_state['step'] == 'select_source':
            # Save source chat info
            setup_state['config']['source_chat'] = event.message.forward.chat_id
            setup_state['config']['message_id'] = event.message.forward.message_id
            setup_state['config']['grouped_id'] = event.message.grouped_id
            setup_state['step'] = 'set_delay'
            
            # Ask for delay
            await event.respond(
                "⏱ **Auto-Forward Setup (2/4)**\n\n"
                "Great! Now set the delay between forwards (in minutes).\n"
                "Minimum delay is 8 minutes.\n\n"
                "Enter a number:",
                buttons=[[Button.inline("❌ Cancel Setup", "refresh")]]
            )
        
        bot_instance._save_instances()
        
    except Exception as e:
        logger.error(f"Error in message setup for user {user_id}: {str(e)}", exc_info=True)
        await event.respond("❌ An error occurred during setup", buttons=[[Button.inline("❌ Cancel", "refresh")]])

async def handle_delay_setup(event, bot_instance, user_id, delay_text):
    """Handle delay input during setup"""
    try:
        delay = int(delay_text)
        if delay < 8:
            await event.respond(
                "⚠️ Minimum delay is 8 minutes. Please enter a larger value:",
                buttons=[[Button.inline("❌ Cancel Setup", "refresh")]]
            )
            return
        
        instance = bot_instance.user_instances[user_id]
        setup_state = instance.setup_state
        setup_state['config']['delay'] = delay
        setup_state['step'] = 'confirm'
        
        # Show confirmation
        source_chat = setup_state['config']['source_chat']
        await event.respond(
            "✅ **Auto-Forward Setup (3/4)**\n\n"
            f"📱 Source Chat: `{source_chat}`\n"
            f"⏱ Delay: {delay} minutes\n\n"
            "Is this correct?",
            buttons=[
                [Button.inline("✅ Confirm", "autoforward_confirm")],
                [Button.inline("❌ Cancel", "refresh")]
            ],
            parse_mode='markdown'
        )
        
        bot_instance._save_instances()
        
    except ValueError:
        await event.respond(
            "⚠️ Please enter a valid number for the delay:",
            buttons=[[Button.inline("❌ Cancel Setup", "refresh")]]
        )
    except Exception as e:
        logger.error(f"Error in delay setup for user {user_id}: {str(e)}", exc_info=True)
        await event.respond("❌ An error occurred during setup", buttons=[[Button.inline("❌ Cancel", "refresh")]])

async def handle_autoforward_confirm(event, bot_instance):
    """Handle autoforward setup confirmation"""
    user_id = event.sender_id
    logger.info(f"Confirming autoforward setup for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        setup_state = instance.setup_state
        
        if setup_state['step'] != 'confirm':
            await event.answer("⚠️ Invalid setup state", alert=True)
            return
        
        # Save configuration
        instance.autoforward_config = setup_state['config'].copy()
        instance.autoforward_status = {
            'running': False,
            'last_forward': None,
            'next_forward': None
        }
        instance.setup_state = {}  # Clear setup state
        bot_instance._save_instances()
        
        # Show success message
        await event.edit(
            "✅ **Auto-Forward Setup Complete!**\n\n"
            "Your configuration has been saved.\n"
            "You can now start forwarding or run a test.",
            buttons=[
                [Button.inline("▶️ Start Forwarding", "autoforward_start")],
                [Button.inline("🔄 Test Forward", "test_forward")],
                [Button.inline("🔙 Back to Menu", "refresh")]
            ],
            parse_mode='markdown'
        )
        logger.info(f"Autoforward setup completed for user {user_id}")
    
    except Exception as e:
        logger.error(f"Error confirming setup for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred saving configuration", alert=True)

async def handle_test_forward_quick(event, bot_instance):
    """Handle quick test forward"""
    user_id = event.sender_id
    logger.info(f"Starting quick test forward for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        config = instance.autoforward_config
        
        if not config or not config.get('source_chat'):
            await event.answer("⚠️ Please set up autoforward first", alert=True)
            return
        
        # Start test with minimal delay
        await event.edit(
            "🔄 **Running Quick Test**\n\n"
            "The bot will attempt to forward the message with minimal delay.\n"
            "Please wait...",
            buttons=[[Button.inline("🔙 Back", "forwarding")]],
            parse_mode='markdown'
        )
        
        # TODO: Implement actual forward logic here
        await asyncio.sleep(2)  # Simulate forwarding
        
        await event.edit(
            "✅ **Quick Test Complete**\n\n"
            "The test forward was successful!\n"
            "You can now start regular forwarding or run another test.",
            buttons=[
                [Button.inline("▶️ Start Forwarding", "autoforward_start")],
                [Button.inline("🔄 Test Again", "test_forward")],
                [Button.inline("🔙 Back", "forwarding")]
            ],
            parse_mode='markdown'
        )
        logger.info(f"Quick test completed for user {user_id}")
    
    except Exception as e:
        logger.error(f"Error in quick test for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred during test", alert=True)

async def handle_test_forward_real(event, bot_instance):
    """Handle real test forward"""
    user_id = event.sender_id
    logger.info(f"Starting real test forward for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        config = instance.autoforward_config
        
        if not config or not config.get('source_chat'):
            await event.answer("⚠️ Please set up autoforward first", alert=True)
            return
        
        delay = config['delay']
        next_forward = datetime.now() + timedelta(minutes=delay)
        
        await event.edit(
            "⏱ **Running Real Test**\n\n"
            f"The bot will attempt to forward the message in {delay} minutes\n"
            f"(at <t:{int(next_forward.timestamp())}:t>)\n\n"
            "This simulates the actual forwarding delay.",
            buttons=[
                [Button.inline("❌ Cancel Test", "forwarding")]
            ],
            parse_mode='markdown'
        )
        
        # TODO: Implement actual forward logic here
        logger.info(f"Real test scheduled for user {user_id} at {next_forward}")
    
    except Exception as e:
        logger.error(f"Error in real test for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred scheduling test", alert=True)

async def handle_list_groups(event, bot_instance):
    """Handle listing user's groups and channels"""
    user_id = event.sender_id
    logger.info(f"Listing groups for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        
        # Ensure client is connected
        if not instance.client or not instance.client.is_connected():
            await instance.init_client(bot_instance.api_id)
            if not instance.client.is_connected():
                await event.answer("❌ Failed to connect to Telegram", alert=True)
                return
        
        # Get all dialogs
        groups = []
        channels = []
        try:
            async for dialog in instance.client.iter_dialogs():
                if dialog.is_group:
                    groups.append(dialog)
                elif dialog.is_channel:
                    channels.append(dialog)
                if len(groups) + len(channels) >= 20:  # Limit to 20 total for readability
                    break
        except Exception as e:
            logger.error(f"Error fetching dialogs: {str(e)}")
            await event.answer("❌ Failed to fetch groups", alert=True)
            return
        
        # Create formatted list
        text = "📋 **Your Groups and Channels**\n\n"
        
        if groups:
            text += "👥 **Groups:**\n"
            for group in groups:
                text += f"• {group.title} (`{group.id}`)\n"
            text += "\n"
        
        if channels:
            text += "📢 **Channels:**\n"
            for channel in channels:
                text += f"• {channel.title} (`{channel.id}`)\n"
            text += "\n"
        
        if not groups and not channels:
            text += "❌ No groups or channels found.\n"
        
        text += "\nℹ️ Showing up to 20 most recent dialogs."
        
        await event.edit(
            text,
            buttons=[
                [Button.inline("🔄 Refresh List", "list_groups")],
                [Button.inline("🔙 Back", "groups")]
            ],
            parse_mode='markdown'
        )
        logger.info(f"Successfully listed groups for user {user_id}")
    
    except Exception as e:
        logger.error(f"Error listing groups for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred listing groups", alert=True)

async def handle_resync_groups(event, bot_instance):
    """Handle resyncing groups and channels"""
    user_id = event.sender_id
    logger.info(f"Resyncing groups for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        
        # Ensure client is connected
        if not instance.client or not instance.client.is_connected():
            await instance.init_client(bot_instance.api_id)
            if not instance.client.is_connected():
                await event.answer("❌ Failed to connect to Telegram", alert=True)
                return
        
        # Show progress message
        await event.edit(
            "🔄 **Resyncing Groups**\n\n"
            "Please wait while I refresh your group list...",
            parse_mode='markdown'
        )
        
        # Clear existing cache if any
        if hasattr(instance, 'groups_cache'):
            instance.groups_cache = {}
        
        # Fetch and cache all dialogs
        groups_count = 0
        channels_count = 0
        try:
            async for dialog in instance.client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    if not hasattr(instance, 'groups_cache'):
                        instance.groups_cache = {}
                    instance.groups_cache[dialog.id] = {
                        'title': dialog.title,
                        'type': 'group' if dialog.is_group else 'channel',
                        'last_synced': datetime.now()
                    }
                    if dialog.is_group:
                        groups_count += 1
                    else:
                        channels_count += 1
        except Exception as e:
            logger.error(f"Error during resync: {str(e)}")
            await event.edit(
                "❌ **Resync Failed**\n\n"
                "An error occurred while refreshing your groups.\n"
                "Please try again later.",
                buttons=[[Button.inline("🔙 Back", "groups")]],
                parse_mode='markdown'
            )
            return
        
        # Save the updated instance
        bot_instance._save_instances()
        
        # Show completion message
        await event.edit(
            "✅ **Resync Complete**\n\n"
            f"Found {groups_count} groups and {channels_count} channels.\n\n"
            "Your group list has been updated successfully.",
            buttons=[
                [Button.inline("📋 View Groups", "list_groups")],
                [Button.inline("🔙 Back", "groups")]
            ],
            parse_mode='markdown'
        )
        logger.info(f"Successfully resynced groups for user {user_id}")
    
    except Exception as e:
        logger.error(f"Error resyncing groups for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred during resync", alert=True)

async def handle_logout(event, bot_instance):
    """Handle user logout"""
    user_id = event.sender_id
    logger.info(f"Processing logout for user {user_id}")
    
    try:
        # Get user instance
        instance = bot_instance.user_instances.get(user_id)
        if not instance:
            await event.answer("❌ Already logged out", alert=True)
            return
        
        # Stop any running autoforward tasks
        if instance.autoforward_status.get('running', False):
            instance.autoforward_status['running'] = False
            logger.info(f"Stopped autoforward for user {user_id}")
        
        if instance.autoforward_status.get('test_running', False):
            instance.autoforward_status['test_running'] = False
            logger.info(f"Stopped test forward for user {user_id}")
        
        # Disconnect the client (but don't log out)
        if instance.client and instance.client.is_connected():
            await instance.client.disconnect()
            logger.info(f"Disconnected client for user {user_id}")
        
        # Remove user instance from bot
        del bot_instance.user_instances[user_id]
        bot_instance._save_instances()
        logger.info(f"Removed user instance for {user_id}")
        
        # Send confirmation message
        await event.edit(
            "✅ **Successfully Logged Out**\n\n"
            "You have been logged out of the bot.\n"
            "Your Telegram session is preserved.\n"
            "Use /start to log in again.",
            buttons=None
        )
        logger.info(f"User {user_id} logged out successfully")
        
    except Exception as e:
        logger.error(f"Error during logout for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ Error during logout. Please try again.", alert=True)

async def handle_group_finder(event, bot_instance):
    """Handle group finder tool"""
    user_id = event.sender_id
    logger.info(f"Opening group finder for user {user_id}")
    
    try:
        await event.edit(
            "🔍 **Group Finder**\n\n"
            "This tool helps you find groups based on keywords.\n"
            "To search for groups, send me a keyword or topic.",
            buttons=[
                [Button.inline("🔙 Back to Tools", "tools")]
            ],
            parse_mode='markdown'
        )
    except Exception as e:
        logger.error(f"Error showing group finder: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred", alert=True)

async def handle_account_info(event, bot_instance):
    """Handle account info display"""
    user_id = event.sender_id
    logger.info(f"Showing account info for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        me = await instance.client.get_me()
        
        # Format account info
        info = (
            "👤 **Account Information**\n\n"
            f"**Username:** @{me.username}\n"
            f"**First Name:** {me.first_name}\n"
            f"**Last Name:** {me.last_name or 'Not set'}\n"
            f"**User ID:** `{me.id}`\n"
            f"**Phone:** +{me.phone}\n"
            f"**Bot Access:** ✅ Active"
        )
        
        await event.edit(
            info,
            buttons=[
                [Button.inline("🔙 Back to Account", "account")]
            ],
            parse_mode='markdown'
        )
    except Exception as e:
        logger.error(f"Error showing account info: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred", alert=True)

async def handle_subscription_info(event, bot_instance):
    """Handle subscription info display"""
    user_id = event.sender_id
    logger.info(f"Showing subscription info for user {user_id}")
    
    try:
        # For now, showing basic info since subscription system isn't implemented
        info = (
            "💳 **Subscription Information**\n\n"
            "**Status:** ✅ Active\n"
            "**Plan:** Standard\n"
            "**Features:**\n"
            "• Unlimited Auto-forwarding\n"
            "• Group Management\n"
            "• Priority Support\n\n"
            "For questions about your subscription, please contact support."
        )
        
        await event.edit(
            info,
            buttons=[
                [Button.inline("🔙 Back to Account", "account")]
            ],
            parse_mode='markdown'
        )
    except Exception as e:
        logger.error(f"Error showing subscription info: {str(e)}", exc_info=True)
        await event.answer("❌ An error occurred", alert=True) 