from datetime import datetime, timedelta
from typing import Optional
from utils.logger import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
import os
import asyncio
from core.session import session_manager
from utils.security import security_manager

class UserInstance:
    """Represents a user's personal ControlBot instance"""
    INACTIVITY_TIMEOUT = timedelta(hours=1)  # Timeout after 1 hour of inactivity
    DEFAULT_DELAY = 600  # Default delay of 10 minutes in seconds
    
    def __init__(self, user_id: int, api_hash: str, phone: str, session_id: Optional[str] = None):
        logger.info(f"Creating new UserInstance for user_id={user_id}, phone={phone}")
        self.user_id = user_id
        self.api_hash = api_hash
        self.phone = phone
        self.session_id = session_id
        self.last_activity = datetime.utcnow()
        self.authenticated = False
        self.client = None
        self._cleanup_task = None
        # Setup state for handling user input
        self.setup_state = {}
        # Autoforwarding configuration
        self.autoforward_config = {
            'message': None,  # Message to forward
            'source_chat': None,  # Source chat ID
            'target_chats': [],  # List of target chat IDs
            'iterations': 0,  # Number of iterations to run
            'delay': self.DEFAULT_DELAY,  # Delay between forwards in seconds (10 minutes)
            'test_delay': self.DEFAULT_DELAY,  # Test delay in seconds (10 minutes)
            'source_message': None,  # Source message to forward
            'test_group': None  # Test group ID
        }
        # Autoforwarding status
        self.autoforward_status = {
            'running': False,
            'messages_sent': 0,
            'iterations_done': 0,
            'total_iterations': 0,
            'start_time': None,
            'stop_time': None,
            'task': None  # To store the running task
        }
        logger.info(f"UserInstance created successfully for user_id={user_id}")
    
    async def init_client(self, api_id: int, force: bool = False):
        """Initialize the Telethon client for this user"""
        if not self.client or force:
            # Disconnect existing client if any
            await self.disconnect_client()
            
            try:
                # Try to load session from session manager using phone number
                session_data = session_manager.load_session(self.phone)
                if session_data:
                    # Decrypt session string and create client with StringSession
                    session_string = security_manager.decrypt_message(session_data['session'])
                    self.client = TelegramClient(
                        StringSession(session_string),
                        api_id,
                        self.api_hash,
                        device_model="ArkanisUserBot",
                        system_version="1.0",
                        app_version="1.0"
                    )
                    # Store the session ID from the loaded data
                    self.session_id = session_data['session_id']
                    logger.info(f"Created client from stored session for user {self.user_id}")
                else:
                    logger.warning(f"No session data found for phone {self.phone}")
                    return False
                
                # Connect the client
                await self.client.connect()
                
                # Verify the connection
                if await self.client.is_user_authorized():
                    self.authenticated = True
                    logger.info(f"Successfully authenticated client for user {self.user_id}")
                else:
                    logger.warning(f"Client not authorized for user {self.user_id}")
                    await self.disconnect_client()
                    return False
                
                # Start cleanup task
                if self._cleanup_task:
                    self._cleanup_task.cancel()
                self._cleanup_task = asyncio.create_task(self._cleanup_on_inactivity())
                
                # Update session last used timestamp
                if session_data:
                    session_data['last_used'] = datetime.utcnow().isoformat()
                    session_manager.save_session(self.session_id, session_data)
                
                return True
                
            except Exception as e:
                logger.error(f"Error initializing client for user {self.user_id}: {str(e)}", exc_info=True)
                await self.disconnect_client()
                return False
    
    async def _cleanup_on_inactivity(self):
        """Monitor client for inactivity and disconnect if inactive for too long"""
        try:
            while True:
                await asyncio.sleep(60)  # Check every minute
                if datetime.utcnow() - self.last_activity > self.INACTIVITY_TIMEOUT:
                    logger.info(f"Disconnecting inactive client for user {self.user_id}")
                    await self.disconnect_client()
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in cleanup task for user {self.user_id}: {str(e)}")
    
    def update_activity(self):
        """Update the last activity timestamp"""
        self.last_activity = datetime.utcnow()
    
    async def disconnect_client(self):
        """Disconnect the Telethon client"""
        if self.client:
            if self._cleanup_task:
                self._cleanup_task.cancel()
                self._cleanup_task = None
            await self.client.disconnect()
            self.client = None
            logger.info(f"Telethon client disconnected for user {self.user_id}")
    
    def to_dict(self) -> dict:
        logger.debug(f"Converting UserInstance to dict for user_id={self.user_id}")
        return {
            'user_id': self.user_id,
            'api_hash': self.api_hash,
            'phone': self.phone,
            'session_id': self.session_id,
            'last_activity': self.last_activity.isoformat(),
            'authenticated': self.authenticated,
            'setup_state': self.setup_state,
            'autoforward_config': self.autoforward_config,
            'autoforward_status': {
                k: v for k, v in self.autoforward_status.items()
                if k != 'task'  # Don't serialize the task
            }
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UserInstance':
        logger.debug(f"Creating UserInstance from dict: user_id={data['user_id']}")
        instance = cls(
            user_id=data['user_id'],
            api_hash=data['api_hash'],
            phone=data['phone'],
            session_id=data.get('session_id')
        )
        instance.last_activity = datetime.fromisoformat(data['last_activity'])
        instance.authenticated = data['authenticated']
        # Restore setup state
        if 'setup_state' in data:
            instance.setup_state = data['setup_state']
        # Restore autoforwarding configuration and status
        if 'autoforward_config' in data:
            instance.autoforward_config.update(data['autoforward_config'])
        if 'autoforward_status' in data:
            instance.autoforward_status.update(data['autoforward_status'])
            instance.autoforward_status['task'] = None  # Reset task
        logger.debug(f"UserInstance restored from dict: user_id={data['user_id']}, authenticated={instance.authenticated}")
        return instance 