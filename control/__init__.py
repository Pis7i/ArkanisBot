"""
ControlBot module for managing Telegram user accounts.
This module provides a Telegram bot interface for users to control their accounts
and an admin interface for managing the bot and its users.
"""

from .bot import ControlBot, control_bot

__all__ = ['ControlBot', 'control_bot'] 