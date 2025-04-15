from telethon.tl.custom import Button
from utils.logger import logger
from datetime import datetime
import asyncio
from utils.error_handler import error_handler
from utils.chat_cleaner import chat_cleaner, MessageContext

async def send_menu_message(event, text, buttons=None, parse_mode='markdown'):
    """Helper function to send menu messages and track them."""
    try:
        # Clean previous messages before sending new one
        await chat_cleaner.clean_messages(
            event.client,
            event.sender_id,
            event.chat_id,
            context_filter={MessageContext.MENU, MessageContext.COMMAND, MessageContext.TEMP}
        )
        
        # Send new message
        msg = await event.client.send_message(
            event.chat_id,
            text,
            buttons=buttons,
            parse_mode=parse_mode
        )
        
        # Track the new message as a menu message
        await chat_cleaner.track_message(
            event.sender_id,
            msg,
            MessageContext.MENU
        )
        return msg
        
    except Exception as e:
        logger.error(f"Error in send_menu_message: {str(e)}", exc_info=True)
        raise

async def clear_chat(event, user_id):
    """Clear previous bot messages for this user."""
    try:
        await chat_cleaner.clean_messages(
            event.client,
            user_id,
            event.chat_id,
            context_filter={MessageContext.MENU, MessageContext.COMMAND, MessageContext.TEMP}
        )
    except Exception as e:
        logger.error(f"Error clearing chat: {str(e)}")
        # Don't raise the exception - let the menu continue to show

@error_handler
async def show_main_menu(event, user_id):
    """Show main menu with user information and options"""
    try:
        # Get bot instance from the event's client
        bot_instance = event._client._bot_instance
        
        # Get user instance
        instance = bot_instance.user_instances[user_id]
        
        # Ensure client is connected
        if not instance.client or not instance.client.is_connected():
            try:
                logger.info(f"Reconnecting client for user {user_id}")
                await instance.init_client(bot_instance.api_id)
                if not instance.client.is_connected():
                    # If we can't reconnect, send error message
                    await event.respond(
                        "❌ Connection error. Please try /start to reconnect.",
                        parse_mode='markdown'
                    )
                    return
                logger.info(f"Successfully reconnected client for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to reconnect client for user {user_id}: {str(e)}")
                await event.respond(
                    "❌ Failed to reconnect. Please try /start to reconnect.",
                    parse_mode='markdown'
                )
                return
        
        # Get user info
        try:
            me = await instance.client.get_me()
            username = me.username if me.username else me.first_name
        except Exception as e:
            logger.error(f"Error getting user info: {str(e)}")
            await event.respond(
                "❌ Error accessing your account. Please try /start to reconnect.",
                parse_mode='markdown'
            )
            return
        
        # Get autoforward status
        is_running = instance.autoforward_status.get('running', False)
        status_emoji = "🟢" if is_running else "🔴"
        status_text = "Running" if is_running else "Stopped"
        
        # Get group count
        groups_count = 0
        try:
            async for dialog in instance.client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    groups_count += 1
        except Exception as e:
            logger.error(f"Error counting groups: {str(e)}")
            groups_count = "Unknown"
        
        # Create menu text
        menu_text = (
            "🤖 **Welcome to AutoBot Control Panel**\n\n"
            f"👤 **Account:** @{username}\n"
            f"📊 **Autoforward:** {status_emoji} {status_text}\n"
            f"👥 **Groups:** {groups_count}\n\n"
            "Please select an option from the menu below:"
        )
        
        # Create buttons
        buttons = [
            [Button.inline("📱 Forwarding", "forwarding"), Button.inline("👥 Groups", "groups")],
            [Button.inline("🛠 Tools", "tools"), Button.inline("👤 Account", "account")],
            [Button.inline("🔄 Refresh", "refresh"), Button.inline("❌ Log Out", "logout")]
        ]
        
        # Send menu message
        await send_menu_message(event, menu_text, buttons)
        
    except Exception as e:
        logger.error(f"Error showing main menu: {str(e)}")
        # Use respond instead of answer for both Message and CallbackQuery events
        await event.respond(
            "❌ Error showing menu. Please try /start to reconnect.",
            parse_mode='markdown'
        )

@error_handler
async def show_forwarding_menu(event, user_id):
    """Show the main forwarding menu"""
    logger.info(f"Opening forwarding menu for user {user_id}")
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        menu_text = (
            "🔄 **Message Forwarding**\n\n"
            "Choose an option from below:"
        )
        
        buttons = [
            [Button.inline("📱 Auto Forward", "autoforward_menu")],
            [Button.inline("🔄 Test Forward", "test_forward_start")],
            [Button.inline("🔙 Back", "main")]
        ]
        
        # Send menu using helper function
        await send_menu_message(event, menu_text, buttons)
        
        logger.info(f"Forwarding menu shown to user {user_id}")
        
    except Exception as e:
        logger.error(f"Error showing forwarding menu: {str(e)}", exc_info=True)
        await event.answer("❌ Failed to show forwarding menu", alert=True)

@error_handler
async def show_autoforward_menu(event, user_id):
    """Show the autoforward submenu"""
    logger.info(f"Opening autoforward menu for user {user_id}")
    try:
        # First answer the callback query if this is from a button press
        if hasattr(event, 'query'):
            await event.answer()
        
        # Clear previous messages
        await clear_chat(event, user_id)
        
        bot_instance = event.client._bot_instance
        instance = bot_instance.user_instances.get(user_id)
        
        # Initialize status if needed
        if not hasattr(instance, 'autoforward_status'):
            instance.autoforward_status = {
                'running': False,
                'test_running': False,
                'iterations': 0,
                'messages_sent': 0,
                'start_time': None,
                'last_forward': None
            }
        
        # Initialize config if needed
        if not hasattr(instance, 'autoforward_config'):
            instance.autoforward_config = {
                'delay': 10,  # Default delay in minutes
                'test_delay': 10,  # Default test delay in minutes
                'source_message': None,
                'test_group': None
            }
        
        # Save the initialized instance
        bot_instance._save_instances()
        
        # Get status
        status = instance.autoforward_status
        
        menu_text = (
            "⚙️ **Auto Forward Settings**\n\n"
            f"Status: {'🟢 Running' if status.get('running', False) else '🔴 Stopped'}\n"
            f"Test Mode: {'🟢 Running' if status.get('test_running', False) else '🔴 Stopped'}\n\n"
            "Select an option:"
        )
        
        buttons = [
            [Button.inline("⚙️ Setup Auto Forward", "autoforward_setup_menu")],
            [Button.inline("📊 Forwarding Status", "autoforward_status")],
            [
                Button.inline(
                    "⏹ Stop Auto Forward" if status.get('running', False) else "▶️ Start Auto Forward",
                    "autoforward_stop" if status.get('running', False) else "autoforward_start"
                )
            ],
            [
                Button.inline(
                    "⏹ Stop Test Forward" if status.get('test_running', False) else "🔄 Start Test Forward",
                    "test_forward_stop" if status.get('test_running', False) else "test_forward_start"
                )
            ],
            [Button.inline("🔙 Back", "forwarding")]
        ]
        
        # Send new menu message
        await send_menu_message(event, menu_text, buttons)
        
    except Exception as e:
        logger.error(f"Error showing autoforward menu: {str(e)}", exc_info=True)
        # Send error message as new message
        await event.client.send_message(
            event.chat_id,
            "❌ Failed to show menu. Please try again.",
            buttons=[[Button.inline("🔙 Back", "forwarding")]]
        )

async def show_autoforward_setup_menu(event, user_id):
    """Show the autoforward setup submenu"""
    logger.info(f"Opening autoforward setup menu for user {user_id}")
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        bot_instance = event.client._bot_instance
        instance = bot_instance.user_instances.get(user_id)
        config = getattr(instance, 'autoforward_config', {})
        bypass_groups = config.get('bypass_groups', [])
        
        menu_text = (
            "⚙️ **Auto Forward Setup**\n\n"
            f"Source Message: {'✅ Selected' if config.get('source_message') else '❌ Not Set'}\n"
            f"Forward Delay: {config.get('delay', 8)} minutes\n"
            f"Test Group: {'✅ Selected' if config.get('test_group') else '❌ Not Set'}\n"
            f"Test Delay: {config.get('test_delay', 8)} minutes\n"
            f"Bypass Groups: {len(bypass_groups) if bypass_groups else '❌ None'}\n\n"
            "Configure your settings:"
        )
        
        buttons = [
            [Button.inline("📱 Select Source Message", "saved_messages_0")],
            [Button.inline("⏱ Set Forward Delay", "select_delay")],
            [Button.inline("🔄 Select Test Group", "select_test_group")],
            [Button.inline("⚡ Set Test Delay", "custom_delay")],
            [Button.inline("🚫 Bypass Groups", "bypass_groups_menu")],
            [Button.inline("🔙 Back", "autoforward_menu")]
        ]
        
        await send_menu_message(event, menu_text, buttons)
        logger.info(f"Autoforward setup menu shown to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error showing autoforward setup menu to user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ Failed to show setup menu", alert=True)

async def handle_single_forward(event):
    """Handle single forward button press"""
    await event.answer("⚠️ Single Forward feature is not ready yet", alert=True)

async def show_account_menu(event, user_id):
    """Show account menu with user information options"""
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        menu_text = (
            "👤 **Account Menu**\n\n"
            "Select an option to view:"
        )
        
        # Account menu buttons
        buttons = [
            [Button.inline("ℹ️ Account Info", "account_info")],
            [Button.inline("💳 Subscription Info", "subscription_info")],
            [Button.inline("🔙 Back", "main")]
        ]
        
        # Send menu using helper function
        await send_menu_message(event, menu_text, buttons)
        
    except Exception as e:
        logger.error(f"Error showing account menu: {str(e)}")
        await event.answer("❌ Failed to show account menu", alert=True)

async def show_groups_menu(event, user_id):
    """Handle group management"""
    logger.info(f"Opening group management for user {user_id}")
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        menu_text = (
            "👥 **Group Management**\n\n"
            "Select an option:"
        )
        
        # Groups menu buttons
        buttons = [
            [Button.inline("📋 List Groups", "list_groups")],
            [Button.inline("🔄 Resync Groups", "resync_groups")],
            [Button.inline("🔙 Back", "main")]
        ]
        
        await send_menu_message(event, menu_text, buttons)
        logger.info(f"Groups menu shown to user {user_id}")
    except Exception as e:
        logger.error(f"Error showing groups menu to user {user_id}: {str(e)}")
        await event.answer("❌ Failed to show groups menu", alert=True)

async def show_tools_menu(event, user_id):
    """Show tools menu with available tools"""
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        menu_text = (
            "🛠 **Tools Menu**\n\n"
            "Select a tool to use:"
        )
        
        # Tools menu buttons
        buttons = [
            [Button.inline("🔍 Group Finder", "group_finder")],
            [Button.inline("🔙 Back", "main")]
        ]
        
        await send_menu_message(event, menu_text, buttons)
        
    except Exception as e:
        logger.error(f"Error showing tools menu: {str(e)}")
        await event.answer("❌ Failed to show tools menu", alert=True)

async def show_saved_messages(event, user_id, page=0):
    """Show saved messages for selection"""
    logger.info(f"Showing saved messages for user {user_id}")
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        bot_instance = event.client._bot_instance
        instance = bot_instance.user_instances.get(user_id)
        
        # Ensure client is initialized and connected
        if not instance.client or not instance.client.is_connected():
            try:
                await instance.init_client(bot_instance.api_id)
                await instance.client.connect()
                if not instance.client.is_connected():
                    await event.answer("❌ Failed to connect to Telegram. Please try logging out and back in.", alert=True)
                    return
                if not await instance.client.is_user_authorized():
                    await event.answer("❌ Session expired. Please log out and log in again.", alert=True)
                    return
                logger.info(f"Successfully reconnected client for user {user_id}")
            except Exception as e:
                logger.error(f"Error initializing client for user {user_id}: {str(e)}", exc_info=True)
                await event.answer("❌ Error connecting to Telegram. Please try logging out and back in.", alert=True)
                return
        
        # Update activity timestamp
        instance.update_activity()
        
        # Get saved messages using user's client
        messages = []
        try:
            async for msg in instance.client.iter_messages('me', limit=10, offset_id=page*10):
                if msg.text:  # Only show text messages
                    messages.append(msg)
        except Exception as e:
            logger.error(f"Error fetching messages for user {user_id}: {str(e)}", exc_info=True)
            # If we get a key error, the session might be invalid
            if "key is not registered" in str(e).lower():
                await event.answer("❌ Session expired. Please log out and log in again to refresh your session.", alert=True)
            else:
                await event.answer("❌ Error accessing saved messages. Please try logging out and back in.", alert=True)
            return
        
        menu_text = (
            "📝 **Select Source Message**\n\n"
            "Choose a message from your Saved Messages to use as the source for forwarding:"
        )
        
        buttons = []
        for msg in messages:
            preview = msg.text[:50] + "..." if len(msg.text) > 50 else msg.text
            buttons.append([Button.inline(f"📄 {preview}", f"select_message_{msg.id}")])
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(Button.inline("⬅️ Previous", f"saved_messages_{page-1}"))
        if len(messages) == 10:
            nav_buttons.append(Button.inline("➡️ Next", f"saved_messages_{page+1}"))
        if nav_buttons:
            buttons.append(nav_buttons)
            
        buttons.append([Button.inline("🔙 Back", "autoforward_setup_menu")])
        
        await send_menu_message(event, menu_text, buttons)
        logger.info(f"Saved messages shown to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error showing saved messages for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ Failed to show saved messages. Please try logging out and back in.", alert=True)

async def show_message_preview(event, user_id, message_id):
    """Show preview of selected message with confirmation options"""
    logger.info(f"Showing message preview for user {user_id}, message {message_id}")
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        bot_instance = event.client._bot_instance
        instance = bot_instance.user_instances.get(user_id)
        
        # Ensure client is connected
        if not instance.client or not instance.client.is_connected():
            await instance.init_client(bot_instance.api_id)
            if not instance.client or not instance.client.is_connected():
                await event.answer("❌ Failed to connect to Telegram", alert=True)
                return
        
        # Get the message using user's client
        message = await instance.client.get_messages('me', ids=message_id)
        if not message:
            await event.answer("❌ Message not found", alert=True)
            return
        
        # Get all messages if it's a group using user's client
        grouped_messages = []
        if message.grouped_id:
            async for m in instance.client.iter_messages('me', limit=100):
                if m.grouped_id == message.grouped_id:
                    grouped_messages.append(m)
        
        # Create preview text
        menu_text = "📱 **Message Preview**\n\n"
        
        if grouped_messages:
            menu_text += f"📎 Media Group with {len(grouped_messages)} items\n\n"
            for m in grouped_messages:
                # Check if message has text or caption
                msg_text = getattr(m, 'text', None) or getattr(m, 'raw_text', None) or getattr(m, 'message', None) or ''
                if msg_text:
                    menu_text += f"Text: {msg_text}\n"
                menu_text += f"Type: {get_media_type(m)}\n\n"
        else:
            # Check if message has text or caption
            msg_text = getattr(message, 'text', None) or getattr(message, 'raw_text', None) or getattr(message, 'message', None) or ''
            if msg_text:
                menu_text += f"Text: {msg_text}\n\n"
            if message.media:
                menu_text += f"Type: {get_media_type(message)}\n"
        
        menu_text += f"\nDate: {message.date.strftime('%Y-%m-%d %H:%M')}"
        
        # Create buttons
        buttons = [
            [Button.inline("✅ Confirm Selection", f"confirm_message_{message_id}")],
            [Button.inline("🔙 Back to List", "saved_messages_0")],
            [Button.inline("↩️ Back to Setup", "autoforward_setup_menu")]
        ]
        
        await send_menu_message(event, menu_text, buttons)
        logger.info(f"Message preview shown to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error showing message preview for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ Failed to show message preview", alert=True)

def get_media_type(message):
    """Helper function to get media type string"""
    if message.photo:
        return "Photo 📷"
    elif message.video:
        return "Video 🎥"
    elif message.document:
        return "Document 📄"
    elif message.audio:
        return "Audio 🎵"
    elif message.voice:
        return "Voice Message 🎤"
    elif message.sticker:
        return "Sticker 🎨"
    elif message.gif:
        return "GIF 🎞"
    else:
        return "Unknown Media 📎"

async def show_delay_config(event, user_id, is_test_delay=False):
    """Show delay configuration menu"""
    logger.info(f"Showing {'test ' if is_test_delay else ''}delay config for user {user_id}")
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        bot_instance = event.client._bot_instance
        instance = bot_instance.user_instances.get(user_id)
        config = getattr(instance, 'autoforward_config', {})
        
        current_delay = config.get('test_delay' if is_test_delay else 'delay', 8)
        
        menu_text = (
            f"⏱ **{'Test ' if is_test_delay else ''}Forward Delay Configuration**\n\n"
            f"Current delay: {current_delay} minutes\n\n"
            "Select a preset delay or choose custom to set your own:"
        )
        
        # Preset delays
        buttons = [
            [Button.inline("8 minutes", f"{'test_' if is_test_delay else ''}set_delay_8")],
            [Button.inline("15 minutes", f"{'test_' if is_test_delay else ''}set_delay_15")],
            [Button.inline("30 minutes", f"{'test_' if is_test_delay else ''}set_delay_30")],
            [Button.inline("1 hour", f"{'test_' if is_test_delay else ''}set_delay_60")],
            [Button.inline("Custom Delay", f"{'test_' if is_test_delay else ''}custom_delay")],
            [Button.inline("🔙 Back", "autoforward_setup_menu")]
        ]
        
        await send_menu_message(event, menu_text, buttons)
        logger.info(f"Delay config menu shown to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error showing delay config for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ Failed to show delay configuration", alert=True)

async def show_custom_delay_input(event, user_id, is_test_delay=False):
    """Show custom delay input menu"""
    logger.info(f"Showing custom delay input menu for user {user_id}")
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        menu_text = (
            "⏰ **Custom Delay Configuration**\n\n"
            f"Enter the desired {'test ' if is_test_delay else ''}delay in minutes.\n"
            "Send a number between 8 and 1440 (24 hours).\n\n"
            "Or click Back to return to the setup menu."
        )
        
        buttons = [[Button.inline("🔙 Back", "autoforward_setup_menu")]]
        
        await send_menu_message(event, menu_text, buttons)
        
        # Set user state to wait for custom delay input
        bot_instance = event.client._bot_instance
        instance = bot_instance.user_instances.get(user_id)
        instance.state = {
            'waiting_for': 'custom_delay',
            'is_test_delay': is_test_delay
        }
        bot_instance._save_instances()
        
        logger.info(f"Custom delay input menu shown to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error showing custom delay input menu for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ Failed to show custom delay input menu", alert=True)

async def handle_delay_input(event, user_id, delay_text, is_test_delay=False):
    """Handle custom delay input from user"""
    logger.info(f"Handling delay input for user {user_id}: {delay_text}")
    try:
        delay = int(delay_text)
        if delay < 8:
            await event.respond(
                "⚠️ Minimum delay is 8 minutes. Please enter a larger value:",
                buttons=[[Button.inline("🔙 Back", f"setup_{'test_' if is_test_delay else ''}delay")]]
            )
            return
        elif delay > 1440:
            await event.respond(
                "⚠️ Maximum delay is 24 hours (1440 minutes). Please enter a smaller value:",
                buttons=[[Button.inline("🔙 Back", f"setup_{'test_' if is_test_delay else ''}delay")]]
            )
            return
        
        # Save the delay
        bot_instance = event.client._bot_instance
        instance = bot_instance.user_instances.get(user_id)
        if not hasattr(instance, 'autoforward_config'):
            instance.autoforward_config = {}
        
        key = 'test_delay' if is_test_delay else 'delay'
        instance.autoforward_config[key] = delay
        
        # Clear setup state
        if hasattr(instance, 'setup_state'):
            instance.setup_state = {}
        
        # Show confirmation
        await event.respond(
            f"✅ {'Test delay' if is_test_delay else 'Delay'} set to {delay} minutes.",
            buttons=[[Button.inline("🔙 Back to Setup", "autoforward_setup_menu")]]
        )
        
        logger.info(f"Delay set for user {user_id}: {delay} minutes")
    
    except ValueError:
        await event.respond(
            "⚠️ Please enter a valid number:",
            buttons=[[Button.inline("🔙 Back", f"setup_{'test_' if is_test_delay else ''}delay")]]
        )

async def show_group_selection(event, user_id, page=0):
    """Show group selection menu"""
    logger.info(f"Showing group selection for user {user_id}")
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        bot_instance = event.client._bot_instance
        instance = bot_instance.user_instances.get(user_id)
        
        # Ensure client is connected
        if not instance.client or not instance.client.is_connected():
            await instance.init_client(bot_instance.api_id)
            if not instance.client or not instance.client.is_connected():
                await event.answer("❌ Failed to connect to Telegram", alert=True)
                return
        
        client = instance.client  # Get user's Telethon client
        
        # Get dialogs using user's client
        groups = []
        offset_date = None
        offset_id = 0
        offset_peer = None
        
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                groups.append(dialog)
                if len(groups) >= (page + 1) * 10:
                    break
        
        # Get the current page of groups
        start_idx = page * 10
        current_page_groups = groups[start_idx:start_idx + 10]
        
        menu_text = (
            "👥 **Select Test Group**\n\n"
            "Choose a group or channel for test forwarding:"
        )
        
        buttons = []
        for group in current_page_groups:
            name = group.title or "Untitled"  # Fallback if title is None
            # Truncate long names
            if len(name) > 30:
                name = name[:27] + "..."
            buttons.append([Button.inline(
                f"{'📢' if group.is_channel else '👥'} {name}", 
                f"confirm_group_{group.id}"  # Changed to directly confirm
            )])
        
        # Add navigation buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(Button.inline("⬅️ Previous", f"group_list_{page-1}"))
        if len(groups) > (page + 1) * 10:  # If there are more groups
            nav_buttons.append(Button.inline("➡️ Next", f"group_list_{page+1}"))
        if nav_buttons:
            buttons.append(nav_buttons)
            
        buttons.append([Button.inline("🔙 Back", "autoforward_setup_menu")])
        
        await send_menu_message(event, menu_text, buttons)
        logger.info(f"Group selection shown to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error showing group selection for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ Failed to show group selection", alert=True)

async def show_group_preview(event, user_id, group_id):
    """Show group preview with confirmation options"""
    logger.info(f"Showing group preview for user {user_id}, group {group_id}")
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        bot_instance = event.client._bot_instance
        instance = bot_instance.user_instances.get(user_id)
        
        # Get group info
        entity = await bot_instance.client.get_entity(group_id)
        
        # Create preview text
        menu_text = (
            "👥 **Group Preview**\n\n"
            f"Title: {entity.title}\n"
            f"Type: {'Channel' if entity.broadcast else 'Group'}\n"
            f"Members: {entity.participants_count if hasattr(entity, 'participants_count') else 'Unknown'}\n\n"
            "Would you like to use this group for test forwarding?"
        )
        
        # Create buttons
        buttons = [
            [Button.inline("✅ Confirm Selection", f"confirm_group_{group_id}")],
            [Button.inline("🔙 Back to List", "select_test_group")],
            [Button.inline("↩️ Back to Setup", "autoforward_setup_menu")]
        ]
        
        await send_menu_message(event, menu_text, buttons)
        logger.info(f"Group preview shown to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error showing group preview for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ Failed to show group preview", alert=True)

async def show_forwarding_status(event, user_id):
    """Show autoforward status and statistics"""
    logger.info(f"Showing forwarding status for user {user_id}")
    try:
        # Clear previous bot messages
        await clear_chat(event, user_id)
        
        bot_instance = event.client._bot_instance
        instance = bot_instance.user_instances.get(user_id)
        status = instance.autoforward_status
        config = instance.autoforward_config
        
        # Calculate duration if running
        duration = ""
        if status['start_time']:
            delta = datetime.now() - status['start_time']
            hours = delta.total_seconds() // 3600
            minutes = (delta.total_seconds() % 3600) // 60
            duration = f"{int(hours)}h {int(minutes)}m"
        
        menu_text = (
            "📊 **Auto Forward Status**\n\n"
            f"Status: {'🟢 Running' if status['running'] else '🔴 Stopped'}\n"
            f"Test Mode: {'🟢 Running' if status['test_running'] else '🔴 Stopped'}\n\n"
            f"Messages Sent: {status['messages_sent']}\n"
            f"Iterations: {status['iterations']}\n"
            f"Running Time: {duration if duration else 'Not running'}\n\n"
            "Configuration:\n"
            f"• Delay: {config.get('delay', 8)} minutes\n"
            f"• Test Delay: {config.get('test_delay', 8)} minutes\n"
            f"• Source Message: {config.get('source_message', 'Not set')}\n"
            f"• Test Group: {config.get('test_group', 'Not set')}"
        )
        
        buttons = [[Button.inline("🔙 Back", "autoforward_menu")]]
        
        await send_menu_message(event, menu_text, buttons)
        logger.info(f"Forwarding status shown to user {user_id}")
    
    except Exception as e:
        logger.error(f"Error showing forwarding status for user {user_id}: {str(e)}", exc_info=True)
        await event.answer("❌ Failed to show status", alert=True)

async def handle_autoforward_stop(event, instance):
    """Handle stopping autoforward"""
    user_id = instance.user_id
    logger.info(f"Starting autoforward stop process for user {user_id}")
    
    try:
        # First, answer the callback query with a notification
        await event.answer("Stopping autoforward task...")
        
        # Clear any existing messages
        await clear_chat(event, user_id)
        
        # Send the stopping message as a new message
        stopping_msg = await event.client.send_message(
            event.chat_id,
            "⏳ Stopping autoforward task...\n\n"
            "Please wait while the task is being stopped.",
            buttons=[[Button.inline("Please wait...", "noop")]]
        )
        
        # Stop the autoforward task
        success = await stop_autoforward(event, instance)
        logger.debug(f"Stop autoforward result: {success}")
        
        # Always show a menu after stopping, regardless of success
        if success:
            menu_text = (
                "✅ **Auto Forward Stopped**\n\n"
                "The autoforward task has been stopped successfully.\n\n"
                "What would you like to do next?"
            )
        else:
            menu_text = (
                "❌ **Failed to Stop Auto Forward**\n\n"
                "There was an error stopping the autoforward task.\n\n"
                "What would you like to do?"
            )
        
        # Common buttons for both success and failure cases
        buttons = [
            [Button.inline("▶️ Start Auto Forward", "autoforward_start")],
            [Button.inline("📊 Check Status", "autoforward_status")],
            [Button.inline("🔙 Back", "autoforward_menu")]
        ]
        
        # Send the final menu as a new message
        final_msg = await event.client.send_message(
            event.chat_id,
            menu_text,
            buttons=buttons
        )
        
        return success
        
    except Exception as e:
        logger.error(f"Error in handle_autoforward_stop: {str(e)}", exc_info=True)
        
        try:
            # Try to answer the callback query if not already answered
            if hasattr(event, 'query'):
                await event.answer("Error stopping autoforward")
            
            # Show error menu as a new message
            error_msg = await event.client.send_message(
                event.chat_id,
                "❌ **Error Stopping Auto Forward**\n\n"
                "There was an unexpected error.\n"
                "Please try again or return to the menu.",
                buttons=[
                    [Button.inline("🔄 Try Again", "autoforward_stop")],
                    [Button.inline("🔙 Back", "autoforward_menu")]
                ]
            )
        except Exception as e2:
            logger.error(f"Failed to send error message: {str(e2)}", exc_info=True)
        
        return False 