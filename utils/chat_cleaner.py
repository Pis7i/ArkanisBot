from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Dict, Set, Optional, List, Any, Callable, Awaitable
import asyncio
import weakref
from telethon import TelegramClient
from telethon.errors import (
    MessageDeleteForbiddenError,
    MessageIdInvalidError,
    FloodWaitError
)
from telethon.tl.custom import Message
from utils.logger import logger
from utils.redis_config import redis_manager
from functools import wraps

# Constants
REDIS_MESSAGE_EXPIRY = 48 * 60 * 60  # 48 hours in seconds
REDIS_KEY_PREFIX = "chatcleaner:"

class MessageContext(Enum):
    """Enum to track the context/type of each message"""
    AUTH = auto()  # Authentication related messages
    MENU = auto()  # Menu messages with buttons
    COMMAND = auto()  # Command messages like /start
    SYSTEM = auto()  # System messages that should persist
    TEMP = auto()  # Temporary messages to be cleaned up

@dataclass
class MessageTracker:
    """Tracks message state and context for a user session"""
    message_id: int
    context: MessageContext
    chat_id: int
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    weak_ref: Optional[weakref.ref] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert tracker to dictionary for Redis storage"""
        return {
            'message_id': self.message_id,
            'context': self.context.name,
            'chat_id': self.chat_id,
            'timestamp': self.timestamp,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MessageTracker':
        """Create tracker from dictionary (Redis storage)"""
        return cls(
            message_id=data['message_id'],
            context=MessageContext[data['context']],
            chat_id=data['chat_id'],
            timestamp=data['timestamp'],
            metadata=data.get('metadata', {})
        )

def with_cleanup(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(message: Message, *args: Any, **kwargs: Any) -> Any:
        if not hasattr(message, 'from_user') or not message.from_user:
            return await func(message, *args, **kwargs)
            
        user_id = message.from_user.id
        cleaner = ChatCleaner()
        
        try:
            # Load and clean old messages before handling new command
            await cleaner.clean_chat(user_id)
            result = await func(message, *args, **kwargs)
            
            # Track the new message for future cleanup
            if isinstance(result, Message):
                await cleaner.track_message(result, MessageContext.MENU)
            return result
            
        except Exception as e:
            logger.error(f"Error in cleanup wrapper: {str(e)}")
            return await func(message, *args, **kwargs)
            
    return wrapper

class ChatCleaner:
    def __init__(self, debug_mode: bool = False):
        # Core state tracking
        self._messages: Dict[int, Dict[int, MessageTracker]] = {}  # user_id -> {msg_id -> tracker}
        self._current_menu: Dict[int, int] = {}  # user_id -> current_menu_id
        self._auth_state: Dict[int, bool] = {}  # user_id -> is_in_auth
        
        # Activity tracking
        self._last_activity: Dict[int, float] = {}
        self._cleanup_locks: Dict[int, asyncio.Lock] = {}
        self._state_lock = asyncio.Lock()
        
        # Configuration
        self.debug_mode = debug_mode
        self.INACTIVE_THRESHOLD = timedelta(hours=1)
        self.CLEANUP_INTERVAL = 300  # 5 minutes
        self.MAX_TRACKED_MESSAGES = 100  # Per user
        self.DELETION_BATCH_SIZE = 50
        self.LOCK_TIMEOUT = 3.0  # seconds
        
        # Async state
        self._cleanup_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        # Optional callback for persistent storage
        self._persistence_callback: Optional[Callable[[int, Dict[int, MessageTracker]], Awaitable[None]]] = None
        
        self._check_redis_persistence()

    async def _check_redis_persistence(self) -> None:
        """Check if Redis is configured for persistence"""
        if not redis_manager.enabled:
            return
            
        try:
            info = await redis_manager.redis.info()
            if info.get("persistence", {}).get("loading") == 0:
                logger.warning("Redis persistence may not be configured - tracked messages could be lost on restart")
        except Exception as e:
            logger.error(f"Failed to check Redis persistence: {str(e)}")

    def _get_redis_key(self, user_id: int) -> str:
        """Get Redis key for user's tracked messages"""
        return f"{REDIS_KEY_PREFIX}{user_id}"

    async def _load_from_redis(self, user_id: int) -> None:
        """Load tracked messages from Redis"""
        if not redis_manager.enabled:
            return
        
        try:
            data = await redis_manager.get_json(self._get_redis_key(user_id))
            if data:
                trackers = {
                    msg_data['message_id']: MessageTracker.from_dict(msg_data)
                    for msg_data in data['messages']
                }
                self._messages[user_id] = trackers
                if 'current_menu' in data:
                    self._current_menu[user_id] = data['current_menu']
                logger.info(f"Loaded {len(trackers)} tracked messages from Redis for user {user_id}")
        except Exception as e:
            logger.error(f"Error loading messages from Redis for user {user_id}: {str(e)}")

    async def _save_to_redis(self, user_id: int) -> None:
        """Save tracked messages to Redis"""
        if not redis_manager.enabled:
            return
        
        try:
            data = {
                'messages': [
                    tracker.to_dict()
                    for tracker in self._messages.get(user_id, {}).values()
                ],
                'current_menu': self._current_menu.get(user_id)
            }
            await redis_manager.set_json(
                self._get_redis_key(user_id),
                data,
                ex=REDIS_MESSAGE_EXPIRY
            )
            logger.debug(f"Saved {len(data['messages'])} messages to Redis for user {user_id}")
        except Exception as e:
            logger.error(f"Error saving messages to Redis for user {user_id}: {str(e)}")

    async def start(self) -> None:
        """Start the chat cleaner service"""
        if not self._is_running:
            self._is_running = True
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.info("Started chat cleaner service")

    async def shutdown(self) -> None:
        """Gracefully shutdown the chat cleaner"""
        self._is_running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            
            # Save all tracked messages to Redis before shutdown
            if redis_manager.enabled:
                for user_id in self._messages.keys():
                    await self._save_to_redis(user_id)
            
        logger.info("Chat cleaner service shutdown complete")

    async def track_message(
        self, 
        user_id: int, 
        message: Message, 
        context: MessageContext,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Track a new message with its context"""
        try:
            async with self._state_lock:
                # Load existing messages from Redis if this is first message for user
                if user_id not in self._messages and redis_manager.enabled:
                    await self._load_from_redis(user_id)
                
                # Initialize user tracking if needed
                if user_id not in self._messages:
                    self._messages[user_id] = {}
                    self._last_activity[user_id] = datetime.now(timezone.utc).timestamp()

                # Create message tracker
                tracker = MessageTracker(
                    message_id=message.id,
                    context=context,
                    chat_id=message.chat_id,
                    weak_ref=weakref.ref(message),
                    metadata=metadata or {}
                )
                
                # Update tracking
                self._messages[user_id][message.id] = tracker
                self._last_activity[user_id] = tracker.timestamp

                # Handle special contexts
                if context == MessageContext.MENU:
                    old_menu = self._current_menu.get(user_id)
                    self._current_menu[user_id] = message.id
                    if old_menu:
                        # Clean previous menu asynchronously
                        asyncio.create_task(self.clean_messages(
                            message.client, 
                            user_id,
                            message.chat_id,
                            context_filter={MessageContext.MENU}
                        ))
                
                elif context == MessageContext.COMMAND:
                    # Schedule command message for deletion after short delay
                    asyncio.create_task(self._delayed_command_cleanup(
                        message.client,
                        user_id,
                        message.chat_id,
                        message.id
                    ))

                # Enforce message limit per user
                if len(self._messages[user_id]) > self.MAX_TRACKED_MESSAGES:
                    await self._prune_old_messages(user_id)

                # Save to Redis
                if redis_manager.enabled:
                    await self._save_to_redis(user_id)

                # Persist state if callback is set
                if self._persistence_callback:
                    await self._persistence_callback(user_id, self._messages[user_id])

        except Exception as e:
            logger.error(f"Error tracking message for user {user_id}: {str(e)}", exc_info=True)

    async def _delayed_command_cleanup(
        self,
        client: TelegramClient,
        user_id: int,
        chat_id: int,
        message_id: int,
        delay: float = 2.0
    ) -> None:
        """Clean up command message after a short delay"""
        await asyncio.sleep(delay)
        await self.clean_messages(
            client,
            user_id,
            chat_id,
            message_ids={message_id}
        )

    async def clean_messages(
        self,
        client: TelegramClient,
        user_id: int,
        chat_id: int,
        context_filter: Optional[Set[MessageContext]] = None,
        message_ids: Optional[Set[int]] = None,
        exclude_current_menu: bool = True
    ) -> None:
        """Clean messages based on context or specific IDs"""
        try:
            # Load messages from Redis if not in memory
            if user_id not in self._messages and redis_manager.enabled:
                await self._load_from_redis(user_id)
            
            # Try to acquire cleanup lock with timeout
            lock = self._cleanup_locks.setdefault(user_id, asyncio.Lock())
            try:
                async with asyncio.timeout(self.LOCK_TIMEOUT):
                    async with lock:
                        await self._do_clean_messages(
                            client,
                            user_id,
                            chat_id,
                            context_filter,
                            message_ids,
                            exclude_current_menu
                        )
            except asyncio.TimeoutError:
                logger.warning(f"Cleanup lock timeout for user {user_id}")
                return

        except Exception as e:
            logger.error(f"Error in clean_messages for user {user_id}: {str(e)}", exc_info=True)

    async def _do_clean_messages(
        self,
        client: TelegramClient,
        user_id: int,
        chat_id: int,
        context_filter: Optional[Set[MessageContext]],
        message_ids: Optional[Set[int]],
        exclude_current_menu: bool
    ) -> None:
        """Internal method to perform message cleanup"""
        try:
            if self.debug_mode:
                logger.debug(f"Would clean messages for user {user_id} with filter {context_filter}")
                return

            # Determine messages to delete
            to_delete = set()
            current_menu = self._current_menu.get(user_id) if exclude_current_menu else None
            
            if message_ids:
                to_delete.update(message_ids)
            
            if context_filter and user_id in self._messages:
                filtered_msgs = {
                    msg_id for msg_id, tracker in self._messages[user_id].items()
                    if tracker.context in context_filter
                }
                to_delete.update(filtered_msgs)
            
            # Remove current menu from deletion set if needed
            if current_menu and current_menu in to_delete:
                to_delete.remove(current_menu)
            
            if not to_delete:
                return

            # Delete messages in batches
            for batch in [list(to_delete)[i:i + self.DELETION_BATCH_SIZE] 
                         for i in range(0, len(to_delete), self.DELETION_BATCH_SIZE)]:
                try:
                    await client.delete_messages(chat_id, batch)
                    # Clean up tracking for deleted messages
                    async with self._state_lock:
                        for msg_id in batch:
                            if user_id in self._messages and msg_id in self._messages[user_id]:
                                del self._messages[user_id][msg_id]
                        # Update Redis after batch deletion
                        if redis_manager.enabled:
                            await self._save_to_redis(user_id)
                except MessageDeleteForbiddenError:
                    logger.warning(f"Delete forbidden for some messages in user {user_id}")
                except MessageIdInvalidError:
                    logger.warning(f"Invalid message IDs for user {user_id}")
                except FloodWaitError as e:
                    logger.warning(f"FloodWait for {e.seconds}s when deleting messages")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logger.error(f"Error deleting message batch: {str(e)}")

        except Exception as e:
            logger.error(f"Error in _do_clean_messages: {str(e)}", exc_info=True)

    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup of inactive users and old messages"""
        while self._is_running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                await self._cleanup_inactive_users()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {str(e)}")

    async def _cleanup_inactive_users(self) -> None:
        """Clean up data for inactive users"""
        try:
            current_time = datetime.now(timezone.utc).timestamp()
            inactive_threshold = current_time - self.INACTIVE_THRESHOLD.total_seconds()
            
            async with self._state_lock:
                inactive_users = [
                    user_id for user_id, last_time in self._last_activity.items()
                    if last_time < inactive_threshold
                ]
                
                for user_id in inactive_users:
                    await self.clear_user_data(user_id)
                    
        except Exception as e:
            logger.error(f"Error cleaning inactive users: {str(e)}")

    async def _prune_old_messages(self, user_id: int) -> None:
        """Remove oldest tracked messages when limit is exceeded"""
        if user_id in self._messages:
            sorted_msgs = sorted(
                self._messages[user_id].items(),
                key=lambda x: x[1].timestamp
            )
            to_remove = len(sorted_msgs) - self.MAX_TRACKED_MESSAGES
            if to_remove > 0:
                for msg_id, _ in sorted_msgs[:to_remove]:
                    del self._messages[user_id][msg_id]
                # Update Redis after pruning
                if redis_manager.enabled:
                    await self._save_to_redis(user_id)

    async def clear_user_data(self, user_id: int) -> None:
        """Clear all tracking data for a user"""
        async with self._state_lock:
            self._messages.pop(user_id, None)
            self._current_menu.pop(user_id, None)
            self._auth_state.pop(user_id, None)
            self._last_activity.pop(user_id, None)
            self._cleanup_locks.pop(user_id, None)
            
            # Clear Redis data
            if redis_manager.enabled:
                await redis_manager.delete(self._get_redis_key(user_id))

    def set_auth_state(self, user_id: int, is_auth: bool) -> None:
        """Set authentication state for a user"""
        self._auth_state[user_id] = is_auth

    def is_in_auth(self, user_id: int) -> bool:
        """Check if user is in authentication process"""
        return self._auth_state.get(user_id, False)

# Global instance
chat_cleaner = ChatCleaner()