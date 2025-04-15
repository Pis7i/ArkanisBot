import os
import asyncio
from typing import Optional
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from utils.logger import logger
from .manager import control_bot_manager

console = Console()

class ControlBotAdmin:
    """Admin interface for managing ControlBot"""
    def __init__(self):
        self.manager = control_bot_manager
    
    async def show_menu(self):
        """Show the ControlBot admin menu"""
        while True:
            console.clear()
            console.print("[bold blue]ControlBot Admin Menu[/bold blue]\n")
            
            # Show current status
            status = self.manager.get_status()
            self._display_status(status)
            
            # Menu options
            console.print("\n[bold cyan]Available Options:[/bold cyan]")
            console.print("1. Start/Stop ControlBot")
            console.print("2. Manage Allowed Users")
            console.print("3. View Active Sessions")
            console.print("4. Send Broadcast Message")
            console.print("5. View Logs")
            console.print("6. Back to Main Menu")
            
            choice = Prompt.ask("\nEnter your choice", choices=["1", "2", "3", "4", "5", "6"])
            
            if choice == "1":
                await self._handle_start_stop()
            elif choice == "2":
                await self._handle_user_management()
            elif choice == "3":
                await self._handle_view_sessions()
            elif choice == "4":
                await self._handle_broadcast()
            elif choice == "5":
                await self._handle_view_logs()
            elif choice == "6":
                break
    
    def _display_status(self, status: dict):
        """Display current ControlBot status"""
        console.print("\n[bold green]Current Status:[/bold green]")
        console.print(f"Running: {'✅' if status['is_running'] else '❌'}")
        if status['uptime']:
            console.print(f"Uptime: {status['uptime']}")
        console.print(f"Allowed Users: {status['allowed_users_count']}")
        console.print(f"Active Instances: {status['active_instances']}")
        console.print(f"Memory Usage: {status['memory_usage']}")
    
    async def _handle_start_stop(self):
        """Handle starting/stopping the ControlBot"""
        if not self.manager.is_running:
            if Confirm.ask("Start ControlBot?"):
                success, message = await self.manager.start()
                console.print(f"\n{'[bold green]✓' if success else '[bold red]✗'} {message}")
        else:
            if Confirm.ask("Stop ControlBot?"):
                success, message = await self.manager.stop()
                console.print(f"\n{'[bold green]✓' if success else '[bold red]✗'} {message}")
        
        input("\nPress Enter to continue...")
    
    async def _handle_user_management(self):
        """Handle user management menu"""
        while True:
            console.clear()
            console.print("[bold blue]User Management[/bold blue]\n")
            
            # Show current users
            users = self.manager.list_allowed_users()
            self._display_users_table(users)
            
            console.print("\n[bold cyan]Options:[/bold cyan]")
            console.print("1. Add User")
            console.print("2. Remove User")
            console.print("3. View User Details")
            console.print("4. Back")
            
            choice = Prompt.ask("\nEnter your choice", choices=["1", "2", "3", "4"])
            
            if choice == "1":
                user_id = Prompt.ask("Enter user ID (Telegram ID)")
                phone = Prompt.ask("Enter phone number (with country code)")
                
                success, message = self.manager.add_allowed_user(int(user_id), phone)
                console.print(f"\n{'[bold green]✓' if success else '[bold red]✗'} {message}")
                
            elif choice == "2":
                user_id = Prompt.ask("Enter user ID to remove")
                
                if Confirm.ask(f"Remove user {user_id}?"):
                    success, message = self.manager.remove_allowed_user(int(user_id))
                    console.print(f"\n{'[bold green]✓' if success else '[bold red]✗'} {message}")
                
            elif choice == "3":
                user_id = Prompt.ask("Enter user ID to view")
                user_info = self.manager.get_user_info(int(user_id))
                
                if user_info:
                    self._display_user_details(user_info)
                else:
                    console.print("[bold red]User not found.[/bold red]")
                
            elif choice == "4":
                break
            
            if choice != "4":
                input("\nPress Enter to continue...")
    
    def _display_users_table(self, users: list):
        """Display table of allowed users"""
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("User ID")
        table.add_column("Phone")
        table.add_column("Status")
        table.add_column("Added At")
        table.add_column("Session")
        
        for user in users:
            session_status = "✅ Active" if user.get('authenticated') else "❌ Inactive"
            table.add_row(
                str(user['user_id']),
                user['phone'],
                user['status'],
                user['added_at'].split('T')[0],
                session_status
            )
        
        console.print(table)
    
    def _display_user_details(self, user_info: dict):
        """Display detailed information about a user"""
        console.print("\n[bold green]User Details:[/bold green]")
        console.print(f"User ID: {user_info['user_id']}")
        console.print(f"Phone: {user_info['phone']}")
        console.print(f"Status: {user_info['status']}")
        console.print(f"Added At: {user_info['added_at']}")
        
        if 'authenticated' in user_info:
            console.print(f"Authenticated: {'✅' if user_info['authenticated'] else '❌'}")
        if 'session_id' in user_info:
            console.print(f"Session ID: {user_info['session_id']}")
        if 'last_activity' in user_info:
            console.print(f"Last Activity: {user_info['last_activity']}")
    
    async def _handle_view_sessions(self):
        """Handle viewing active sessions"""
        console.clear()
        console.print("[bold blue]Active Sessions[/bold blue]\n")
        
        users = self.manager.list_allowed_users()
        active_users = [u for u in users if u.get('authenticated')]
        
        if not active_users:
            console.print("[yellow]No active sessions found.[/yellow]")
        else:
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("User ID")
            table.add_column("Phone")
            table.add_column("Session ID")
            table.add_column("Last Activity")
            
            for user in active_users:
                table.add_row(
                    str(user['user_id']),
                    user['phone'],
                    user.get('session_id', 'N/A'),
                    user.get('last_activity', 'N/A').split('T')[1].split('.')[0]
                )
            
            console.print(table)
        
        input("\nPress Enter to continue...")
    
    async def _handle_broadcast(self):
        """Handle sending broadcast messages"""
        console.clear()
        console.print("[bold blue]Send Broadcast Message[/bold blue]\n")
        
        if not self.manager.is_running:
            console.print("[bold red]ControlBot must be running to send broadcasts.[/bold red]")
            input("\nPress Enter to continue...")
            return
        
        message = Prompt.ask("Enter your message")
        
        if Confirm.ask("Send this broadcast message?"):
            success, result = await self.manager.broadcast_message(message)
            console.print(f"\n{'[bold green]✓' if success else '[bold red]✗'} {result}")
        
        input("\nPress Enter to continue...")
    
    async def _handle_view_logs(self):
        """Handle viewing ControlBot logs"""
        console.clear()
        console.print("[bold blue]ControlBot Logs[/bold blue]\n")
        
        try:
            # Get last 50 log entries related to ControlBot
            logs = logger.get_logs(
                component="controlbot",
                limit=50,
                level="INFO"
            )
            
            if not logs:
                console.print("[yellow]No logs found.[/yellow]")
            else:
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Time")
                table.add_column("Level")
                table.add_column("Message")
                
                for log in logs:
                    table.add_row(
                        log['timestamp'].split('T')[1].split('.')[0],
                        log['level'],
                        log['message']
                    )
                
                console.print(table)
            
        except Exception as e:
            console.print(f"[bold red]Failed to fetch logs: {e}[/bold red]")
        
        input("\nPress Enter to continue...")

# Create a default ControlBot admin interface
control_bot_admin = ControlBotAdmin() 