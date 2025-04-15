import os
import json
import aiohttp
import hashlib
import hmac
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from telethon.tl.types import User
from utils.logger import logger
from utils.whitelist import whitelist_manager
from core.session import session_manager
from control.modules.menu import show_main_menu
from control.modules.user_instance import UserInstance

class GatewayAuth:
    """Handles authentication using Telegram Gateway API"""
    
    def __init__(self):
        logger.info("Initializing Gateway Authentication...")
        self.access_token = os.getenv('GATEWAY_TOKEN')
        
        if not self.access_token:
            logger.error("GATEWAY_TOKEN not found in environment variables")
            raise ValueError("GATEWAY_TOKEN is required for Gateway API authentication")
        
        self.auth_header = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        self.verification_states: Dict[str, dict] = {}
        self._initialized = False
    
    async def initialize(self):
        if self._initialized:
            return
        success, error = await self.test_connection()
        if not success:
            logger.warning(f"Gateway API connection test failed: {error}")
        else:
            logger.info("Gateway API connection successful")
        self._initialized = True
    
    async def _make_request(self, method: str, endpoint: str, payload: dict) -> Tuple[bool, dict, Optional[str]]:
        url = f"https://gatewayapi.telegram.org/{endpoint}"
        logger.info(f"Making {method} request to {url}")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.request(method, url, headers=self.auth_header, json=payload) as response:
                    response_text = await response.text()
                    
                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON response from {url}: {response_text}")
                        return False, {}, "Invalid JSON response."
                    
                    if response.status == 200 and data.get('ok'):
                        return True, data, None
                    else:
                        error_msg = data.get('error', 'Unknown error')
                        logger.error(f"API error {response.status}: {error_msg}")
                        return False, data, error_msg
        except aiohttp.ClientError as e:
            return False, {}, f"Network error: {str(e)}"
        except asyncio.TimeoutError:
            return False, {}, "Request timeout."
        except Exception as e:
            return False, {}, f"Unexpected error: {str(e)}"
    
    async def test_connection(self) -> Tuple[bool, Optional[str]]:
        logger.info("Testing Gateway API connection...")
        payload = {'phone_number': os.getenv('TEST_PHONE', '+1234567890')}
        success, _, error = await self._make_request('POST', 'checkSendAbility', payload)
        return success, error
    
    async def send_verification(self, phone_number: str) -> Tuple[bool, str, Optional[str]]:
        logger.info(f"Sending verification code to {phone_number}")
        check_success, check_data, check_error = await self._make_request('POST', 'checkSendAbility', {'phone_number': phone_number})
        if not check_success:
            return False, "", check_error
        
        request_id = check_data['result'].get('request_id')
        payload = {'phone_number': phone_number, 'request_id': request_id, 'code_length': 6}
        success, data, error = await self._make_request('POST', 'sendVerificationMessage', payload)
        if success:
            return True, data['result'].get('request_id', ''), None
        return False, "", error
    
    async def check_verification(self, request_id: str, code: str) -> Tuple[bool, Optional[str]]:
        logger.info(f"Checking verification for request_id: {request_id}")
        payload = {'request_id': request_id, 'code': code}
        success, data, error = await self._make_request('POST', 'checkVerificationStatus', payload)
        return success, error
    
    async def revoke_verification(self, request_id: str) -> Tuple[bool, Optional[str]]:
        logger.info(f"Revoking verification for request_id: {request_id}")
        payload = {'request_id': request_id}
        success, _, error = await self._make_request('POST', 'revokeVerificationMessage', payload)
        return success, error

# Initialize GatewayAuth instance
gateway_auth = GatewayAuth()

# Ensure initialization before use
async def ensure_gateway_auth_initialized(bot_instance=None):
    """Initialize gateway auth if not already initialized"""
    if not gateway_auth._initialized:
        await gateway_auth.initialize()
    return gateway_auth

async def handle_phone_step(event, bot_instance, auth_state):
    """Handle phone number verification step"""
    user_id = event.sender_id
    phone = event.message.message.strip()
    logger.info(f"Processing phone step for user {user_id}, phone: {phone}")
    
    try:
        # Validate phone number format
        if not phone.startswith('+') or not phone[1:].isdigit():
            logger.warning(f"Invalid phone format from user {user_id}: {phone}")
            auth_state['attempts'] += 1
            auth_state['last_attempt'] = datetime.utcnow()
            await event.respond(
                "⚠️ Invalid phone number format.\n"
                "Please send your phone number in international format:\n"
                "Example: +1234567890"
            )
            return
        
        # Get user's API credentials from whitelist
        user_data = whitelist_manager.get_user_data(user_id)
        if not user_data:
            logger.error(f"User {user_id} not found in whitelist")
            await event.respond("❌ You are not authorized to use this bot. Please contact the administrator.")
            del bot_instance.auth_states[user_id]
            return
        
        # Check if session exists for this phone
        existing_session = await session_manager.get_session_by_phone(phone)
        if not existing_session:
            logger.error(f"No registered session found for phone {phone}")
            await event.respond("❌ This phone number is not registered. Please contact the administrator to register your account.")
            del bot_instance.auth_states[user_id]
            return
        
        # Initialize Gateway API if needed
        await ensure_gateway_auth_initialized(bot_instance)
        
        # Send verification code through Gateway API
        success, request_id, error = await gateway_auth.send_verification(phone)
        if not success:
            logger.error(f"Failed to send verification code for user {user_id}: {error}")
            await event.respond("❌ Failed to send verification code. Please try again later.")
            auth_state['attempts'] += 1
            auth_state['last_attempt'] = datetime.utcnow()
            return
        
        # Store session info and request_id in auth state
        auth_state.update({
            'step': 'code',
            'phone': phone,
            'request_id': request_id,
            'session_id': existing_session['session_id'],
            'attempts': 0
        })
        
        await event.respond(
            "📱 Code sent!\n\n"
            "Please enter the verification code you received:"
        )
    
    except Exception as e:
        logger.error(f"Error in phone step for user {user_id}: {str(e)}", exc_info=True)
        auth_state['attempts'] += 1
        auth_state['last_attempt'] = datetime.utcnow()
        await event.respond("❌ An error occurred. Please try again.")

async def handle_code_step(event, bot_instance, auth_state):
    """Handle verification code step"""
    user_id = event.sender_id
    code = event.message.message.strip()
    logger.info(f"Processing code step for user {user_id}")
    
    try:
        # Validate code format
        if not code.isdigit():
            logger.warning(f"Invalid code format from user {user_id}: {code}")
            auth_state['attempts'] += 1
            auth_state['last_attempt'] = datetime.utcnow()
            await event.respond("⚠️ Invalid code format. Please enter only numbers.")
            return
        
        # Verify code through Gateway API
        success, error = await gateway_auth.check_verification(auth_state['request_id'], code)
        if not success:
            logger.error(f"Code verification failed for user {user_id}: {error}")
            auth_state['attempts'] += 1
            auth_state['last_attempt'] = datetime.utcnow()
            await event.respond("❌ Invalid code. Please try again.")
            return
        
        # Get user's API credentials from whitelist
        user_data = whitelist_manager.get_user_data(user_id)
        if not user_data:
            logger.error(f"User {user_id} not found in whitelist")
            await event.respond("❌ Authorization failed. Please contact the administrator.")
            del bot_instance.auth_states[user_id]
            return
        
        # Create new UserInstance with proper parameters including session_id
        logger.info(f"Creating new UserInstance for user_id={user_id}, phone={auth_state['phone']}")
        instance = UserInstance(
            user_id=user_id,
            api_hash=user_data['api_hash'],
            phone=auth_state['phone'],
            session_id=auth_state['session_id']  # Use session_id from auth_state instead of user_data
        )
        
        # Initialize and connect the client
        try:
            logger.info(f"Initializing client for user {user_id} with session_id {auth_state['session_id']}")
            await instance.init_client(bot_instance.api_id)
            await instance.client.connect()
            if not instance.client.is_connected():
                raise ConnectionError("Failed to connect to Telegram")
            if not await instance.client.is_user_authorized():
                raise ConnectionError("Session not authorized")
            logger.info(f"Telethon client initialized and connected for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to initialize client for user {user_id}: {str(e)}", exc_info=True)
            await event.respond("❌ Failed to initialize session. Please try again.")
            return
        
        # Save instance and clear auth state
        bot_instance.user_instances[user_id] = instance
        bot_instance._save_instances()
        del bot_instance.auth_states[user_id]
        
        # Show success message and main menu
        await event.respond(
            "✅ *Authentication successful!*\n\n"
            "Welcome to the bot. You can now use all features.",
            parse_mode='markdown'
        )
        await show_main_menu(event, user_id)
        
    except Exception as e:
        logger.error(f"Error in code step for user {user_id}: {str(e)}", exc_info=True)
        auth_state['attempts'] += 1
        auth_state['last_attempt'] = datetime.utcnow()
        await event.respond("❌ An error occurred. Please try again.")

async def handle_auth_state(event, bot_instance):
    """Handle authentication state for users"""
    user_id = event.sender_id
    message = event.message.message
    logger.info(f"Processing auth state for user {user_id}, message: {message}")
    
    try:
        # Get current auth state
        auth_state = bot_instance.auth_states.get(user_id)
        if not auth_state:
            logger.warning(f"No auth state found for user {user_id}")
            await event.respond("⚠️ Authentication session expired. Please use /start to begin again.")
            return
        
        # Check for too many attempts
        if auth_state['attempts'] >= 3:
            time_since_last = datetime.utcnow() - auth_state['last_attempt']
            if time_since_last < timedelta(minutes=15):
                remaining = 15 - (time_since_last.total_seconds() / 60)
                logger.warning(f"Too many auth attempts for user {user_id}")
                await event.respond(
                    f"⚠️ Too many attempts. Please wait {int(remaining)} minutes before trying again."
                )
                return
            else:
                # Reset attempts after timeout
                auth_state['attempts'] = 0
        
        # Handle phone number step
        if auth_state['step'] == 'phone':
            await handle_phone_step(event, bot_instance, auth_state)
        
        # Handle code verification step
        elif auth_state['step'] == 'code':
            await handle_code_step(event, bot_instance, auth_state)
        
        else:
            logger.error(f"Invalid auth step for user {user_id}: {auth_state['step']}")
            await event.respond("❌ An error occurred during authentication. Please use /start to begin again.")
            del bot_instance.auth_states[user_id]
    
    except Exception as e:
        logger.error(f"Error handling auth state for user {user_id}: {str(e)}", exc_info=True)
        await event.respond("❌ An error occurred during authentication. Please try again.")
        # Reset auth state on error
        if user_id in bot_instance.auth_states:
            del bot_instance.auth_states[user_id]
