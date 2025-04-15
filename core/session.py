from typing import Dict, Optional
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
import os
import json
from utils.logger import logger
from utils.security import security_manager

class SessionManager:
    def __init__(self):
        self.api_id = int(os.getenv('API_ID', '0'))
        self.api_hash = os.getenv('API_HASH', '')
        self.active_sessions: Dict[str, TelegramClient] = {}
        self.sessions_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sessions')
        # Create sessions directory if it doesn't exist
        if not os.path.exists(self.sessions_dir):
            os.makedirs(self.sessions_dir)
            logger.info(f"Created sessions directory at {self.sessions_dir}")
    
    def _get_session_path(self, phone: str) -> str:
        """Get the file path for a session file"""
        # Remove any special characters from phone number for filename
        safe_phone = ''.join(c for c in phone if c.isalnum())
        return os.path.join(self.sessions_dir, f"session_{safe_phone}.json")

    def save_session(self, session_id: str, session_data: dict) -> bool:
        """Save session data to file"""
        try:
            # Use phone number for file path
            file_path = self._get_session_path(session_data['phone'])
            # Add session_id to data for reference
            session_data['session_id'] = session_id
            with open(file_path, 'w') as f:
                json.dump(session_data, f, indent=2)
            logger.info(f"Saved session {session_id} to file {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {str(e)}")
            return False

    def load_session(self, phone: str) -> Optional[dict]:
        """Load session data from file using phone number"""
        try:
            file_path = self._get_session_path(phone)
            if not os.path.exists(file_path):
                logger.warning(f"Session file not found: {file_path}")
                return None
            
            with open(file_path, 'r') as f:
                session_data = json.load(f)
            logger.info(f"Loaded session for phone {phone} from file")
            return session_data
        except Exception as e:
            logger.error(f"Failed to load session for phone {phone}: {str(e)}")
            return None

    async def create_session(self, phone: str, api_id: Optional[str] = None, api_hash: Optional[str] = None, reuse_session: bool = False) -> Optional[dict]:
        """Create a new Telegram session for a phone number or reuse existing one"""
        try:
            # Check for existing session if reuse is enabled
            if reuse_session:
                existing_session = await self.get_session_by_phone(phone)
                if existing_session:
                    logger.info(f"[Session Flow] Reusing existing session for {phone}")
                    session_data = existing_session['session_data']
                    # Update last used time
                    session_data['last_used'] = datetime.utcnow().isoformat()
                    self.save_session(existing_session['session_id'], session_data)
                    return {
                        'session_id': session_data['session_id'],
                        'user_info': {
                            'id': session_data['user_id'],
                            'username': session_data['username'],
                            'first_name': session_data['first_name'],
                            'last_name': session_data.get('last_name')
                        }
                    }
            
            # Generate a unique session ID
            session_id = security_manager.generate_session_id()
            logger.info(f"[Session Flow] Creating new session with ID {session_id} for phone {phone}")
            
            # Use provided API credentials or fall back to bot's credentials
            client_api_id = int(api_id) if api_id else self.api_id
            client_api_hash = api_hash if api_hash else self.api_hash
            
            # Create a new Telegram client
            client = TelegramClient(
                StringSession(),
                client_api_id,
                client_api_hash,
                device_model="ArkanisUserBot",
                system_version="1.0",
                app_version="1.0",
                lang_code="en",
                system_lang_code="en"
            )
            
            # Start the client and get the session string
            await client.connect()
            
            # Send code request if not authorized
            if not await client.is_user_authorized():
                logger.info(f"[Session Flow] Sending code request for {phone}")
                await client.send_code_request(phone)
                await client.disconnect()
                return None
            
            session_string = client.session.save()
            logger.info(f"[Session Flow] Session string generated for {phone}")
            
            # Get user information
            me = await client.get_me()
            logger.info(f"[Session Flow] Session created for user: ID={me.id}, Username=@{me.username if me.username else 'None'}")
            
            # Encrypt the session string
            encrypted_session = security_manager.encrypt_message(session_string)
            
            # Store session data in file
            session_data = {
                'phone': phone,
                'session': encrypted_session,
                'created_at': datetime.utcnow().isoformat(),
                'last_used': datetime.utcnow().isoformat(),
                'user_id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'api_id': client_api_id,
                'api_hash': client_api_hash
            }
            
            self.save_session(session_id, session_data)
            
            # Store the active client
            self.active_sessions[session_id] = client
            
            return {'session_id': session_id, 'user_info': {
                'id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name
            }}
            
        except Exception as e:
            logger.error(f"[Session Flow] Failed to create session for {phone}: {str(e)}", exc_info=True)
            if 'client' in locals() and client.is_connected():
                await client.disconnect()
            return None

    async def get_session_by_phone(self, phone: str) -> Optional[dict]:
        """Find a session by phone number"""
        try:
            session_data = self.load_session(phone)
            if session_data:
                return {
                    'session_id': session_data['session_id'],
                    'session_data': session_data
                }
            return None
        except Exception as e:
            logger.error(f"Error finding session for phone {phone}: {str(e)}")
            return None

    async def end_session(self, session_id: str) -> bool:
        """End a session by disconnecting the client but preserve the session file"""
        try:
            logger.info(f"Ending session {session_id}")
            
            # Disconnect and remove from active sessions if exists
            if session_id in self.active_sessions:
                client = self.active_sessions[session_id]
                if client.is_connected():
                    await client.disconnect()
                del self.active_sessions[session_id]
            
            # Update last used time in session file
            session_data = self.load_session(session_data['phone'])
            if session_data:
                session_data['last_used'] = datetime.utcnow().isoformat()
                self.save_session(session_id, session_data)
            
            logger.info(f"Ended session {session_id} (session file preserved)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to end session {session_id}: {str(e)}", exc_info=True)
            return False
    
    async def list_sessions(self) -> list:
        """List all active sessions"""
        try:
            sessions = []
            # List all session files in the sessions directory
            if os.path.exists(self.sessions_dir):
                for filename in os.listdir(self.sessions_dir):
                    if filename.endswith('.json'):
                        file_path = os.path.join(self.sessions_dir, filename)
                        try:
                            with open(file_path, 'r') as f:
                                data = json.load(f)
                                session_id = data.get('session_id')
                                if session_id:
                                    sessions.append({
                                        'session_id': session_id,
                                        'phone': data.get('phone'),
                                        'created_at': data.get('created_at'),
                                        'last_used': data.get('last_used'),
                                        'active': session_id in self.active_sessions
                                    })
                        except Exception as e:
                            logger.error(f"Error reading session file {filename}: {e}")
                            continue
            
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    async def sign_in(self, phone: str, code: str, api_id: Optional[str] = None, api_hash: Optional[str] = None) -> Optional[dict]:
        """Sign in with the provided verification code"""
        try:
            # Use provided API credentials or fall back to bot's credentials
            client_api_id = int(api_id) if api_id else self.api_id
            client_api_hash = api_hash if api_hash else self.api_hash
            
            # Create a new client
            client = TelegramClient(
                StringSession(),
                client_api_id,
                client_api_hash,
                device_model="ArkanisUserBot",
                system_version="1.0",
                app_version="1.0",
                lang_code="en",
                system_lang_code="en"
            )
            
            await client.connect()
            
            try:
                # Try signing in with the code
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                logger.error(f"[Session Flow] 2FA is enabled for {phone}, cannot proceed")
                await client.disconnect()
                return None
            except Exception as e:
                logger.error(f"[Session Flow] Failed to sign in with code for {phone}: {str(e)}")
                await client.disconnect()
                return None
            
            # Generate session ID and continue with session creation
            session_id = security_manager.generate_session_id()
            session_string = client.session.save()
            
            # Get user information
            me = await client.get_me()
            
            # Encrypt session string
            encrypted_session = security_manager.encrypt_message(session_string)
            
            # Store in Redis
            session_data = {
                'phone': phone,
                'session': encrypted_session,
                'created_at': datetime.utcnow().isoformat(),
                'last_used': datetime.utcnow().isoformat(),
                'user_id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'api_id': client_api_id,
                'api_hash': client_api_hash
            }
            
            db_manager.set_cache(
                f'session:{session_id}',
                json.dumps(session_data),
                expire=86400 * 30
            )
            
            # Store active client
            self.active_sessions[session_id] = client
            
            return {'session_id': session_id, 'user_info': {
                'id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name
            }}
            
        except Exception as e:
            logger.error(f"[Session Flow] Failed to sign in for {phone}: {str(e)}", exc_info=True)
            if 'client' in locals() and client.is_connected():
                await client.disconnect()
            return None

# Create a default session manager instance
session_manager = SessionManager() 