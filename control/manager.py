import os
import asyncio
from typing import Optional, Dict
from datetime import datetime
from utils.logger import logger
from utils.database import db_manager
from utils.security import security_manager
from .bot import control_bot, UserInstance

class ControlBotManager:
    """Manages the ControlBot instance and its operations"""
    def __init__(self):
        self.is_running: bool = False
        self.start_time: Optional[datetime] = None
        self.allowed_users: Dict[int, dict] = {}
        self._load_allowed_users()
    
    def _load_allowed_users(self):
        """Load allowed users from database"""
        try:
            users_data = db_manager.get_cache('controlbot:allowed_users')
            if users_data:
                self.allowed_users = json.loads(users_data)
        except Exception as e:
            logger.error(f"Failed to load allowed users: {e}")
    
    def _save_allowed_users(self):
        """Save allowed users to database"""
        try:
            db_manager.set_cache(
                'controlbot:allowed_users',
                json.dumps(self.allowed_users),
                expire=86400 * 30  # 30 days
            )
        except Exception as e:
            logger.error(f"Failed to save allowed users: {e}")
    
    async def start(self):
        """Start the ControlBot"""
        if self.is_running:
            return False, "ControlBot is already running."
        
        try:
            # Start the bot
            asyncio.create_task(control_bot.start())
            
            self.is_running = True
            self.start_time = datetime.utcnow()
            
            logger.info("ControlBot manager started successfully.")
            return True, "ControlBot started successfully."
            
        except Exception as e:
            logger.error(f"Failed to start ControlBot: {e}")
            return False, f"Failed to start ControlBot: {e}"
    
    async def stop(self):
        """Stop the ControlBot"""
        if not self.is_running:
            return False, "ControlBot is not running."
        
        try:
            # Stop the bot
            await control_bot.stop()
            
            self.is_running = False
            self.start_time = None
            
            logger.info("ControlBot manager stopped successfully.")
            return True, "ControlBot stopped successfully."
            
        except Exception as e:
            logger.error(f"Failed to stop ControlBot: {e}")
            return False, f"Failed to stop ControlBot: {e}"
    
    def add_allowed_user(self, user_id: int, phone: str) -> tuple[bool, str]:
        """Add a user to allowed users list"""
        try:
            if user_id in self.allowed_users:
                return False, "User is already allowed."
            
            self.allowed_users[user_id] = {
                'phone': phone,
                'added_at': datetime.utcnow().isoformat(),
                'status': 'active'
            }
            
            self._save_allowed_users()
            logger.info(f"Added user {user_id} to allowed users list.")
            return True, "User added successfully."
            
        except Exception as e:
            logger.error(f"Failed to add allowed user: {e}")
            return False, f"Failed to add user: {e}"
    
    def remove_allowed_user(self, user_id: int) -> tuple[bool, str]:
        """Remove a user from allowed users list"""
        try:
            if user_id not in self.allowed_users:
                return False, "User is not in allowed list."
            
            # Remove user instance if exists
            if user_id in control_bot.user_instances:
                instance = control_bot.user_instances[user_id]
                if instance.session_id:
                    asyncio.create_task(
                        session_manager.end_session(instance.session_id)
                    )
                del control_bot.user_instances[user_id]
            
            # Remove from allowed users
            del self.allowed_users[user_id]
            self._save_allowed_users()
            
            logger.info(f"Removed user {user_id} from allowed users list.")
            return True, "User removed successfully."
            
        except Exception as e:
            logger.error(f"Failed to remove allowed user: {e}")
            return False, f"Failed to remove user: {e}"
    
    def get_status(self) -> dict:
        """Get current status of ControlBot"""
        try:
            status = {
                'is_running': self.is_running,
                'uptime': str(datetime.utcnow() - self.start_time) if self.start_time else None,
                'allowed_users_count': len(self.allowed_users),
                'active_instances': len(control_bot.user_instances),
                'memory_usage': self._get_memory_usage()
            }
            return status
            
        except Exception as e:
            logger.error(f"Failed to get ControlBot status: {e}")
            return {
                'error': str(e),
                'is_running': self.is_running
            }
    
    def _get_memory_usage(self) -> str:
        """Get current memory usage"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory = process.memory_info().rss / 1024 / 1024  # Convert to MB
            return f"{memory:.2f} MB"
        except:
            return "N/A"
    
    def list_allowed_users(self) -> list:
        """Get list of allowed users"""
        users = []
        for user_id, data in self.allowed_users.items():
            user_data = {
                'user_id': user_id,
                'phone': data['phone'],
                'added_at': data['added_at'],
                'status': data['status']
            }
            
            # Add instance info if exists
            if user_id in control_bot.user_instances:
                instance = control_bot.user_instances[user_id]
                user_data.update({
                    'authenticated': instance.authenticated,
                    'session_id': instance.session_id,
                    'last_activity': instance.last_activity.isoformat()
                })
            
            users.append(user_data)
        
        return users
    
    def get_user_info(self, user_id: int) -> Optional[dict]:
        """Get detailed information about a user"""
        if user_id not in self.allowed_users:
            return None
        
        user_data = {
            'user_id': user_id,
            **self.allowed_users[user_id]
        }
        
        # Add instance info if exists
        if user_id in control_bot.user_instances:
            instance = control_bot.user_instances[user_id]
            user_data.update({
                'authenticated': instance.authenticated,
                'session_id': instance.session_id,
                'last_activity': instance.last_activity.isoformat()
            })
        
        return user_data
    
    async def broadcast_message(self, message: str) -> tuple[bool, str]:
        """Broadcast a message to all authenticated users"""
        if not self.is_running:
            return False, "ControlBot is not running."
        
        try:
            sent_count = 0
            for user_id, instance in control_bot.user_instances.items():
                if instance.authenticated:
                    try:
                        await control_bot.bot.send_message(
                            user_id,
                            f"📢 **Broadcast Message**\n\n{message}"
                        )
                        sent_count += 1
                    except Exception as e:
                        logger.error(f"Failed to send broadcast to user {user_id}: {e}")
            
            return True, f"Message broadcast to {sent_count} users."
            
        except Exception as e:
            logger.error(f"Failed to broadcast message: {e}")
            return False, f"Failed to broadcast message: {e}"

# Create a default ControlBot manager instance
control_bot_manager = ControlBotManager() 