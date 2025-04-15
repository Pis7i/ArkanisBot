from functools import wraps
from typing import Callable, Any
from utils.logger import logger
from utils.chat_cleaner import ChatCleaner
from utils.redis_config import redis_manager

def with_cleanup(func: Callable) -> Callable:
    """
    Decorator that runs message cleanup before executing the handler.
    Ensures old messages are deleted on user interaction, even after bot restarts.
    
    Usage:
        @with_cleanup
        async def some_handler(event):
            # Your handler code here
    """
    @wraps(func)
    async def wrapper(event, *args: Any, **kwargs: Any) -> Any:
        try:
            # Extract user_id from event/message
            user_id = getattr(event, 'sender_id', None) or getattr(event.from_user, 'id', None)
            if not user_id:
                logger.warning(f"Could not extract user_id from event in {func.__name__}")
                return await func(event, *args, **kwargs)
            
            # Get chat cleaner instance
            chat_cleaner = ChatCleaner()
            
            # Run cleanup before handler
            logger.debug(f"Running pre-handler cleanup for user {user_id} in {func.__name__}")
            await chat_cleaner.clean_chat(user_id)
            
            # Execute handler
            result = await func(event, *args, **kwargs)
            
            # Track the new message if result is a Message object
            if hasattr(result, 'id'):
                await chat_cleaner.track_message(result, user_id)
                logger.debug(f"Tracked new message {result.id} for user {user_id} in {func.__name__}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in with_cleanup decorator for {func.__name__}: {str(e)}")
            return await func(event, *args, **kwargs)
    
    return wrapper 