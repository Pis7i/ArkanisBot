from datetime import datetime
from telethon.tl.types import User
from telethon.tl.custom import Button
from utils.logger import logger
from utils.whitelist import whitelist_manager
from core.session import session_manager
from control.modules.menu import show_main_menu, clear_chat
from control.auth import ensure_gateway_auth_initialized
from utils.chat_cleaner import chat_cleaner, MessageContext
from utils.decorators import with_cleanup

@with_cleanup
async def handle_start_command(event, bot_instance):
    """Handle /start command"""
    user_id = event.sender_id
    logger.info(f"Received /start command from user_id={user_id}")
    
    try:
        # Clean previous messages
        await chat_cleaner.clean_messages(
            event.client,
            user_id,
            event.chat_id,
            context_filter={MessageContext.MENU, MessageContext.COMMAND, MessageContext.TEMP}
        )
        
        # Check if user is already authenticated from Redis cache
        if user_id in bot_instance.user_instances and bot_instance.user_instances[user_id].authenticated:
            logger.info(f"User {user_id} found in cache and is authenticated")
            instance = bot_instance.user_instances[user_id]
            
            # Initialize client if not already initialized
            if not instance.client:
                await instance.init_client(bot_instance.api_id)
            
            # Update activity
            instance.update_activity()
            bot_instance._save_instances()
            
            # Show welcome back message and menu
            msg = await event.respond(f"👋 Welcome back! Your session is active.")
            await chat_cleaner.track_message(user_id, msg, MessageContext.SYSTEM)
            await show_main_menu(event, user_id)
            return
        
        # Start authentication process for new users
        logger.info(f"Starting authentication process for user {user_id}")
        await start_authentication(event, bot_instance)
    except Exception as e:
        logger.error(f"Error handling /start command for user {user_id}: {str(e)}", exc_info=True)
        await event.respond("❌ An error occurred processing your command. Please try again.")

@with_cleanup
async def handle_help_command(event, bot_instance):
    """Handle /help command"""
    user_id = event.sender_id
    logger.info(f"Received /help command from user_id={user_id}")
    
    try:
        # Clean previous messages
        await chat_cleaner.clean_messages(
            event.client,
            user_id,
            event.chat_id,
            context_filter={MessageContext.MENU, MessageContext.COMMAND, MessageContext.TEMP}
        )
        
        if not await bot_instance._ensure_authenticated(event):
            logger.warning(f"Unauthenticated user {user_id} attempted to use /help command")
            return
        
        help_text = (
            "🤖 **ControlBot Commands**\n\n"
            "/start - Start or resume your session\n"
            "/help - Show this help message\n"
            "/status - Show your current status\n"
            "/logout - End your session"
        )
        msg = await event.respond(
            help_text,
            buttons=[[Button.inline("🔙 Back to Menu", "refresh")]],
            parse_mode='markdown'
        )
        await chat_cleaner.track_message(user_id, msg, MessageContext.MENU)
        logger.info(f"Sent help message to user {user_id}")
    except Exception as e:
        logger.error(f"Error handling /help command for user {user_id}: {str(e)}", exc_info=True)
        await event.respond("❌ An error occurred processing your command. Please try again.")

@with_cleanup
async def handle_status_command(event, bot_instance):
    """Handle /status command"""
    user_id = event.sender_id
    logger.info(f"Received /status command from user_id={user_id}")
    
    try:
        # Clean previous messages
        await chat_cleaner.clean_messages(
            event.client,
            user_id,
            event.chat_id,
            context_filter={MessageContext.MENU, MessageContext.COMMAND, MessageContext.TEMP}
        )
        
        if not await bot_instance._ensure_authenticated(event):
            logger.warning(f"Unauthenticated user {user_id} attempted to use /status command")
            return
        
        instance = bot_instance.user_instances[user_id]
        logger.info(f"Retrieving status for user {user_id}")
        if instance.session_id:
            try:
                userbot = await session_manager.load_session(instance.session_id)
                if userbot:
                    me = await userbot.get_me()
                    logger.info(f"Retrieved user info for {user_id}: username=@{me.username if me.username else 'None'}")
                    status = (
                        "📱 **Your Account Status**\n\n"
                        f"Phone: `{instance.phone}`\n"
                        f"Username: @{me.username if me.username else 'None'}\n"
                        f"Session ID: `{instance.session_id}`\n"
                        f"Last Activity: {instance.last_activity.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"Status: 🟢 Active"
                    )
                else:
                    logger.warning(f"Failed to load session for user {user_id}")
                    status = "❌ Your session is not currently active"
            except Exception as e:
                logger.error(f"Error retrieving status for user {user_id}: {str(e)}", exc_info=True)
                status = "❌ An error occurred while retrieving your status"
        else:
            logger.info(f"No active session found for user {user_id}")
            status = "❌ No active session found"
        
        msg = await event.respond(
            status,
            buttons=[[Button.inline("🔙 Back to Menu", "refresh")]],
            parse_mode='markdown'
        )
        await chat_cleaner.track_message(user_id, msg, MessageContext.SYSTEM)
        logger.info(f"Sent status to user {user_id}")
    except Exception as e:
        logger.error(f"Error handling /status command for user {user_id}: {str(e)}", exc_info=True)
        await event.respond("❌ An error occurred processing your command. Please try again.")

@with_cleanup
async def handle_logout_command(event, bot_instance):
    """Handle /logout command"""
    user_id = event.sender_id
    logger.info(f"Received /logout command from user_id={user_id}")
    
    try:
        # Clean previous messages
        await chat_cleaner.clean_messages(
            event.client,
            user_id,
            event.chat_id,
            context_filter={MessageContext.MENU, MessageContext.COMMAND, MessageContext.TEMP}
        )
        
        if not await bot_instance._ensure_authenticated(event):
            logger.warning(f"Unauthenticated user {user_id} attempted to use /logout command")
            return
        
        # End user's session
        await handle_logout(event, bot_instance)
    except Exception as e:
        logger.error(f"Error handling /logout command for user {user_id}: {str(e)}", exc_info=True)
        await event.respond("❌ An error occurred processing your command. Please try again.")

async def start_authentication(event, bot_instance):
    """Start the authentication process using Gateway API"""
    user_id = event.sender_id
    logger.info(f"Starting authentication process for user {user_id}")
    
    try:
        # Clean previous messages
        await chat_cleaner.clean_messages(
            event.client,
            user_id,
            event.chat_id,
            context_filter={MessageContext.MENU, MessageContext.COMMAND, MessageContext.TEMP}
        )
        
        # Check if user is whitelisted
        if not whitelist_manager.is_whitelisted(user_id):
            logger.warning(f"Non-whitelisted user {user_id} attempted to authenticate")
            await event.respond(
                "⚠️ Access denied. You are not authorized to use this bot.\n"
                "Please contact the administrator for access."
            )
            return
        
        # Check if user is registered
        user_data = whitelist_manager.get_user_data(user_id)
        if not user_data.get('registered'):
            logger.warning(f"User {user_id} is whitelisted but not registered")
            await event.respond(
                "⚠️ Your account is whitelisted but not fully registered.\n"
                "Please contact the administrator to complete registration."
            )
            return
        
        # Get user info
        user: User = await event.get_sender()
        logger.debug(f"Retrieved user info for {user_id}: {user.first_name} {user.last_name if user.last_name else ''}")
        
        # Create authentication state
        bot_instance.auth_states[user_id] = {
            'step': 'phone',
            'attempts': 0,
            'last_attempt': datetime.utcnow()
        }
        logger.info(f"Created authentication state for user {user_id}")
        
        await event.respond(
            "👋 Welcome to ControlBot!\n\n"
            "To get started, I need to verify your identity.\n"
            "Please send me your phone number in international format:\n"
            "Example: +1234567890"
        )
        logger.info(f"Sent welcome message to user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to start authentication for user {user_id}: {str(e)}", exc_info=True)
        await event.respond("❌ An error occurred. Please try again later.")

async def handle_logout(event, bot_instance):
    """Handle user logout while preserving session for future use"""
    user_id = event.sender_id
    logger.info(f"Processing logout request for user {user_id}")
    
    try:
        instance = bot_instance.user_instances[user_id]
        session_id = instance.session_id
        
        # Disconnect Telethon client but preserve session
        await instance.disconnect_client()
        
        # End session (only disconnects client, preserves session file)
        if session_id:
            logger.info(f"Ending session {session_id} for user {user_id} (preserving session file)")
            await session_manager.end_session(session_id)
        
        # Remove user instance from active instances
        del bot_instance.user_instances[user_id]
        bot_instance._save_instances()
        logger.info(f"User instance removed for user {user_id} (session preserved)")
        
        await event.respond(
            "👋 You have been logged out.\n"
            "Your session has been preserved for future use.\n"
            "Use /start to log in again without needing verification."
        )
        logger.info(f"Logout completed for user {user_id} (session preserved)")
    
    except Exception as e:
        logger.error(f"Error handling logout for user {user_id}: {str(e)}", exc_info=True)
        await event.respond("❌ An error occurred during logout. Please try again.") 