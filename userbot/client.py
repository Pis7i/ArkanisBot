from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import InputPeerEmpty, Channel, User, Chat
from telethon.errors import (
    FloodWaitError,
    UserAlreadyParticipantError,
    ChannelPrivateError
)
import asyncio
from typing import List, Dict, Optional, Union
from datetime import datetime
import json
import os
from utils.logger import logger
from utils.database import db_manager

class UserBot:
    def __init__(self, session_id: str, client: TelegramClient):
        self.session_id = session_id
        self.client = client
        self.active = False
        self.last_action = datetime.utcnow()
        self.action_queue = asyncio.Queue()
        self.running_tasks: List[asyncio.Task] = []
    
    async def start(self):
        """Start the UserBot"""
        try:
            if not self.client.is_connected():
                await self.client.connect()
            
            self.active = True
            logger.info(f"UserBot {self.session_id} started")
            
            # Start action processor
            self.running_tasks.append(
                asyncio.create_task(self._process_actions())
            )
            
        except Exception as e:
            logger.error(f"Failed to start UserBot {self.session_id}: {e}")
            self.active = False
            raise
    
    async def stop(self):
        """Stop the UserBot"""
        try:
            self.active = False
            
            # Cancel all running tasks
            for task in self.running_tasks:
                task.cancel()
            
            # Wait for tasks to complete
            await asyncio.gather(*self.running_tasks, return_exceptions=True)
            
            # Disconnect client
            if self.client.is_connected():
                await self.client.disconnect()
            
            logger.info(f"UserBot {self.session_id} stopped")
            
        except Exception as e:
            logger.error(f"Error stopping UserBot {self.session_id}: {e}")
            raise
    
    async def _process_actions(self):
        """Process actions from the queue"""
        while self.active:
            try:
                action = await self.action_queue.get()
                self.last_action = datetime.utcnow()
                
                action_type = action['type']
                params = action['params']
                
                if action_type == 'join_chat':
                    await self._join_chat(**params)
                elif action_type == 'leave_chat':
                    await self._leave_chat(**params)
                elif action_type == 'send_message':
                    await self._send_message(**params)
                elif action_type == 'forward_message':
                    await self._forward_message(**params)
                
                self.action_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing action for {self.session_id}: {e}")
    
    async def queue_action(self, action_type: str, **params):
        """Queue an action for processing"""
        await self.action_queue.put({
            'type': action_type,
            'params': params
        })
    
    async def _join_chat(self, chat_id: Union[str, int], **kwargs):
        """Join a chat or channel"""
        try:
            if isinstance(chat_id, str) and chat_id.startswith('+'):
                # Join private chat
                await self.client(ImportChatInviteRequest(chat_id[1:]))
            else:
                # Join public chat
                await self.client(JoinChannelRequest(chat_id))
            
            logger.info(f"UserBot {self.session_id} joined chat {chat_id}")
            return True
            
        except UserAlreadyParticipantError:
            logger.info(f"UserBot {self.session_id} already in chat {chat_id}")
            return True
        except FloodWaitError as e:
            logger.warning(f"FloodWait for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error(f"Failed to join chat {chat_id}: {e}")
            return False
    
    async def _leave_chat(self, chat_id: Union[str, int], **kwargs):
        """Leave a chat or channel"""
        try:
            await self.client(LeaveChannelRequest(chat_id))
            logger.info(f"UserBot {self.session_id} left chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to leave chat {chat_id}: {e}")
            return False
    
    async def _send_message(self, chat_id: Union[str, int], text: str, **kwargs):
        """Send a message to a chat"""
        try:
            await self.client.send_message(chat_id, text)
            logger.info(f"UserBot {self.session_id} sent message to {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            return False
    
    async def _forward_message(
        self,
        from_chat: Union[str, int],
        to_chat: Union[str, int],
        message_ids: Union[int, List[int]],
        **kwargs
    ):
        """Forward message(s) between chats"""
        try:
            if isinstance(message_ids, int):
                message_ids = [message_ids]
            
            await self.client.forward_messages(
                to_chat,
                message_ids,
                from_chat
            )
            
            logger.info(
                f"UserBot {self.session_id} forwarded messages "
                f"from {from_chat} to {to_chat}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to forward messages: {e}")
            return False
    
    async def get_dialogs(self, limit: int = 100) -> List[Dict]:
        """Get user's dialogs (chats and channels)"""
        try:
            dialogs = []
            async for dialog in self.client.iter_dialogs(limit=limit):
                entity = dialog.entity
                
                dialog_info = {
                    'id': entity.id,
                    'title': getattr(entity, 'title', None) or (
                        f"{getattr(entity, 'first_name', '')} "
                        f"{getattr(entity, 'last_name', '')}"
                    ).strip(),
                    'type': (
                        'channel' if isinstance(entity, Channel) and entity.broadcast
                        else 'group' if isinstance(entity, (Channel, Chat))
                        else 'user' if isinstance(entity, User)
                        else 'unknown'
                    ),
                    'username': getattr(entity, 'username', None),
                    'participants_count': getattr(entity, 'participants_count', None)
                }
                
                dialogs.append(dialog_info)
            
            return dialogs
            
        except Exception as e:
            logger.error(f"Failed to get dialogs: {e}")
            return []
    
    def to_dict(self) -> dict:
        """Convert UserBot instance to dictionary"""
        return {
            'session_id': self.session_id,
            'active': self.active,
            'last_action': self.last_action.isoformat(),
            'queue_size': self.action_queue.qsize()
        } 