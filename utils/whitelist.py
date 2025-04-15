import json
from typing import Optional, Dict, Tuple
from datetime import datetime
from utils.logger import logger
from utils.database import db_manager
from telethon import TelegramClient
import os
from telethon.sessions import StringSession
from models.whitelist import WhitelistedUser
from sqlalchemy.exc import SQLAlchemyError
from utils.security import security_manager
from core.session import session_manager

class WhitelistManager:
    """Manages whitelisted users and their registration data"""
    
    REDIS_KEY = 'controlbot:whitelist'  # For caching
    CACHE_DURATION = 3600  # 1 hour cache
    
    def __init__(self):
        self.whitelist: Dict[int, dict] = {}
        self.registration_states: Dict[int, dict] = {}
        self._load_whitelist()
        logger.info("WhitelistManager initialized")
    
    def _serialize_datetime(self, obj):
        """Helper method to serialize datetime objects"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def _load_whitelist(self):
        """Load whitelist from database and cache"""
        try:
            # Try to get from cache first
            logger.info("Attempting to load whitelist from cache...")
            cached_data = db_manager.get_cache(self.REDIS_KEY)
            if cached_data:
                self.whitelist = json.loads(cached_data)
                logger.info(f"Loaded {len(self.whitelist)} users from cache")
                return

            # If not in cache, load from database
            logger.info("Loading whitelist from database...")
            with db_manager.session_scope() as session:
                users = session.query(WhitelistedUser).all()
                self.whitelist = {
                    str(user.user_id): user.to_dict()
                    for user in users
                }
                
                # Update cache with datetime serialization
                db_manager.set_cache(
                    self.REDIS_KEY,
                    json.dumps(self.whitelist, default=self._serialize_datetime),
                    expire=self.CACHE_DURATION
                )
                
                logger.info(f"Loaded {len(self.whitelist)} users from database")
        except Exception as e:
            logger.error(f"Failed to load whitelist: {str(e)}", exc_info=True)
            self.whitelist = {}
    
    def _save_whitelist(self):
        """Save whitelist to database and update cache"""
        try:
            logger.info(f"Saving {len(self.whitelist)} users to database...")
            with db_manager.session_scope() as session:
                for user_id_str, user_data in self.whitelist.items():
                    user_id = int(user_id_str)
                    user = session.query(WhitelistedUser).get(user_id)
                    
                    if user is None:
                        # Create new user
                        user = WhitelistedUser.from_dict({
                            'user_id': user_id,
                            **user_data
                        })
                        session.add(user)
                    else:
                        # Update existing user
                        for key, value in user_data.items():
                            setattr(user, key, value)
                
                session.commit()
                
                # Update cache with datetime serialization
                db_manager.set_cache(
                    self.REDIS_KEY,
                    json.dumps(self.whitelist, default=self._serialize_datetime),
                    expire=self.CACHE_DURATION
                )
                
                logger.info("Whitelist saved successfully to database and cache")
        except SQLAlchemyError as e:
            logger.error(f"Database error while saving whitelist: {str(e)}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Failed to save whitelist: {str(e)}", exc_info=True)
            raise

    def add_user(self, user_id: int, api_id: str, api_hash: str) -> bool:
        """Add a user to the whitelist"""
        try:
            logger.info(f"Adding user {user_id} to whitelist...")
            user_data = {
                'api_id': int(api_id),  # Convert api_id to integer
                'api_hash': api_hash,
                'added_at': datetime.utcnow(),
                'registered': False,
                'session_string': None,
                'last_updated': datetime.utcnow()
            }
            
            # Update memory and persist
            self.whitelist[str(user_id)] = user_data
            self._save_whitelist()
            
            logger.info(f"Successfully added user {user_id} to whitelist")
            return True
        except Exception as e:
            logger.error(f"Failed to add user {user_id} to whitelist: {str(e)}", exc_info=True)
            return False
    
    def remove_user(self, user_id: int) -> bool:
        """Remove a user from the whitelist"""
        try:
            user_id_str = str(user_id)
            if user_id_str in self.whitelist:
                logger.info(f"Removing user {user_id} from whitelist...")
                
                # Remove from database
                with db_manager.session_scope() as session:
                    user = session.query(WhitelistedUser).get(user_id)
                    if user:
                        session.delete(user)
                
                # Remove from memory and update cache
                del self.whitelist[user_id_str]
                self._save_whitelist()
                
                logger.info(f"Successfully removed user {user_id} from whitelist")
                return True
                
            logger.info(f"User {user_id} not found in whitelist")
            return False
        except Exception as e:
            logger.error(f"Failed to remove user {user_id} from whitelist: {str(e)}", exc_info=True)
            return False
    
    def is_whitelisted(self, user_id: int) -> bool:
        """Check if a user is whitelisted"""
        return str(user_id) in self.whitelist
    
    def get_user_data(self, user_id: int) -> Optional[dict]:
        """Get user's registration data"""
        return self.whitelist.get(str(user_id))
    
    async def register_user(self, user_id: int, phone: str) -> Tuple[bool, str]:
        """Register a whitelisted user with their phone number"""
        try:
            # Check if user is whitelisted
            if not self.is_whitelisted(user_id):
                return False, "User is not whitelisted"
            
            # Get user data
            user_data = self.get_user_data(user_id)
            if not user_data:
                return False, "User data not found"
            
            # Create new Telegram client for registration
            client = TelegramClient(
                StringSession(),
                api_id=int(user_data['api_id']),
                api_hash=user_data['api_hash'],
                device_model="ArkanisUserBot",
                system_version="1.0",
                app_version="1.0"
            )
            
            await client.connect()
            
            # Send code request
            await client.send_code_request(phone)
            
            # Store registration state
            self.registration_states[user_id] = {
                'phone': phone,
                'client': client,
                'attempts': 0
            }
            
            return True, "Verification code sent"
            
        except Exception as e:
            logger.error(f"Failed to register user {user_id}: {str(e)}", exc_info=True)
            if 'client' in locals() and client.is_connected():
                await client.disconnect()
            return False, str(e)
    
    async def verify_code(self, user_id: int, code: str) -> bool:
        """Verify the registration code and create session"""
        try:
            # Get registration state
            state = self.registration_states.get(user_id)
            if not state:
                logger.error(f"No registration state found for user {user_id}")
                return False
            
            client = state['client']
            phone = state['phone']
            
            # Sign in with code
            await client.sign_in(phone, code)
            
            # Get user info
            me = await client.get_me()
            
            # Save session
            session_string = client.session.save()
            
            # Get user data for API credentials
            user_data = self.get_user_data(user_id)
            
            # Generate session ID
            session_id = security_manager.generate_session_id()
            
            # Create session data
            session_data = {
                'phone': phone,
                'session': security_manager.encrypt_message(session_string),
                'created_at': datetime.utcnow().isoformat(),
                'last_used': datetime.utcnow().isoformat(),
                'user_id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'api_id': user_data['api_id'],
                'api_hash': user_data['api_hash']
            }
            
            # Save session to file using session manager
            if not session_manager.save_session(session_id, session_data):
                logger.error(f"Failed to save session for user {user_id}")
                return False
            
            # Update user data
            user_data['registered'] = True
            user_data['phone'] = phone
            user_data['session_id'] = session_id
            self._save_whitelist()
            
            # Clean up
            await client.disconnect()
            del self.registration_states[user_id]
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to verify code for user {user_id}: {str(e)}", exc_info=True)
            if 'client' in locals() and client.is_connected():
                await client.disconnect()
            if user_id in self.registration_states:
                del self.registration_states[user_id]
            return False
    
    def get_all_users(self) -> Dict[str, dict]:
        """Get all whitelisted users"""
        return self.whitelist

# Create a global instance
whitelist_manager = WhitelistManager() 