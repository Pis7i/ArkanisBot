"""Message tracking utility for menu messages."""

class MenuMessageTracker:
    def __init__(self):
        self.messages = {}  # user_id -> list of message_ids
    
    def add_message(self, user_id, message):
        """Add a message to track. Can handle both Message objects and message IDs."""
        if user_id not in self.messages:
            self.messages[user_id] = []
            
        # Handle both Message objects and raw message IDs
        msg_id = message.id if hasattr(message, 'id') else message
        if msg_id not in self.messages[user_id]:
            self.messages[user_id].append(msg_id)
    
    def get_messages(self, user_id):
        """Get list of message IDs for a user."""
        return self.messages.get(user_id, [])
    
    def clear_messages(self, user_id):
        """Clear tracked messages for a user."""
        self.messages[user_id] = []

# Global message tracker instance
message_tracker = MenuMessageTracker() 