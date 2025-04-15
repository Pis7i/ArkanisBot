import os
import asyncio
import sys
from typing import Dict, Optional
from datetime import datetime
import json
from dotenv import load_dotenv
from utils.logger import logger
from utils.database import db_manager
from utils.security import security_manager
from .session import session_manager
import time
import subprocess
from utils.whitelist import whitelist_manager
import signal

# Load environment variables from .env file
load_dotenv()

class MainBotFoundation:
    def __init__(self):
        self.running = True
        self.current_menu = "main"
        self.menu_stack = []
        self.controlbot_process = None
        
        # Load configuration
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load configuration from environment or config file"""
        return {
            'api_id': os.getenv('API_ID', ''),
            'api_hash': os.getenv('API_HASH', ''),
            'redis_url': os.getenv('REDIS_URL', 'redis://localhost:6379'),
            'database_url': os.getenv('DATABASE_URL', ''),
            'max_sessions': int(os.getenv('MAX_CONCURRENT_SESSIONS', '10'))
        }
    
    def _clear_screen(self):
        """Clear the terminal screen"""
        # Ensure all output is flushed
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Clear screen based on OS
        if sys.platform == 'win32':
            os.system('cls')
        else:
            # More thorough clearing for Unix-like systems
            os.system('clear && printf "\033c\033[3J"')
        
        # Ensure terminal is ready
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Small delay to ensure terminal is ready
        time.sleep(0.1)
    
    def _print_menu(self, title: str, options: list, show_status: bool = False):
        """Print a menu with the given title and options"""
        self._clear_screen()
        
        # Print header
        print("=" * 50, flush=True)
        print(f"ArkanisBot Admin Control Panel{' - ' + title if title != 'Main Menu' else ''}", flush=True)
        print("=" * 50, flush=True)
        print(f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        print("-" * 50, flush=True)
        
        # Print status if requested
        if show_status:
            status = "🟢 Running" if (self.controlbot_process and self.controlbot_process.poll() is None) else "🔴 Stopped"
            print(f"\nCurrent Status: {status}", flush=True)
        
        # Print menu options
        print(f"\n{title}:", flush=True)
        for option in options:
            print(option, flush=True)
        print("-" * 50, flush=True)
    
    async def _handle_configuration(self):
        """Handle configuration menu"""
        while True:
            # Define configuration menu options
            config_menu = [
                "1. View Current Configuration",
                "2. Edit API Credentials",
                "3. Edit Rate Limits",
                "4. Edit System Parameters",
                "\n0. Back to Main Menu"
            ]
            
            self._print_menu("Configuration", config_menu)
            
            choice = input("\nEnter your choice: ").strip()
            sys.stdout.flush()
            
            if choice == "1":
                self._clear_screen()
                print("\nCurrent Configuration:", flush=True)
                for key, value in self.config.items():
                    # Mask sensitive data
                    if key in ['api_hash', 'api_id']:
                        value = f"{value[:4]}..." if value else "Not set"
                    print(f"{key}: {value}", flush=True)
                input("\nPress Enter to continue...")
                sys.stdout.flush()
            
            elif choice == "2":
                self._clear_screen()
                print("\nEdit API Credentials:", flush=True)
                api_id = input("Enter API ID (press Enter to keep current): ").strip()
                api_hash = input("Enter API Hash (press Enter to keep current): ").strip()
                sys.stdout.flush()
                
                if api_id:
                    self.config['api_id'] = api_id
                if api_hash:
                    self.config['api_hash'] = api_hash
                
                print("\nCredentials updated!", flush=True)
                input("Press Enter to continue...")
                sys.stdout.flush()
            
            elif choice == "0":
                break
            else:
                print("\nInvalid choice. Please try again.", flush=True)
                await asyncio.sleep(1)
    
    async def _handle_user_settings(self):
        """Handle user settings menu"""
        while True:
            # Define user settings menu options
            user_menu = [
                "1. View Whitelisted Users",
                "2. Add User to Whitelist",
                "3. Remove User from Whitelist",
                "4. Register Whitelisted User",
                "\n0. Back to Main Menu"
            ]
            
            self._print_menu("User Settings", user_menu)
            
            choice = input("\nEnter your choice: ").strip()
            sys.stdout.flush()
            
            if choice == "1":
                self._clear_screen()
                print("\nWhitelisted Users:", flush=True)
                users = whitelist_manager.get_all_users()
                if users:
                    for user_id, data in users.items():
                        status = "✅ Registered" if data['registered'] else "⏳ Not Registered"
                        print(f"\nUser ID: {user_id}", flush=True)
                        print(f"Added: {data['added_at']}", flush=True)
                        print(f"Status: {status}", flush=True)
                        print(f"API ID: {data['api_id']}", flush=True)
                        print("-" * 30, flush=True)
                else:
                    print("\nNo users in whitelist.", flush=True)
                input("\nPress Enter to continue...")
                sys.stdout.flush()
                
            elif choice == "2":
                self._clear_screen()
                print("\nAdd User to Whitelist:", flush=True)
                try:
                    user_id = int(input("Enter Telegram User ID: ").strip())
                    api_id = input("Enter API ID (from my.telegram.org): ").strip()
                    api_hash = input("Enter API Hash (from my.telegram.org): ").strip()
                    
                    if whitelist_manager.is_whitelisted(user_id):
                        print("\n❌ User is already whitelisted.", flush=True)
                    else:
                        success = whitelist_manager.add_user(user_id, api_id, api_hash)
                        if success:
                            print(f"\n✅ User {user_id} has been added to the whitelist.", flush=True)
                        else:
                            print("\n❌ Failed to add user to whitelist.", flush=True)
                except ValueError:
                    print("\n❌ Invalid user ID. Please enter a valid number.", flush=True)
                input("\nPress Enter to continue...")
                sys.stdout.flush()
            
            elif choice == "3":
                self._clear_screen()
                print("\nRemove User from Whitelist:", flush=True)
                users = whitelist_manager.get_all_users()
                
                if not users:
                    print("\nNo users in whitelist.", flush=True)
                    input("\nPress Enter to continue...")
                    sys.stdout.flush()
                    continue
                
                # Show numbered list of users
                user_list = list(users.items())
                print("\nSelect a user to remove:", flush=True)
                for idx, (user_id, data) in enumerate(user_list, 1):
                    status = "✅ Registered" if data['registered'] else "⏳ Not Registered"
                    print(f"\n{idx}. User ID: {user_id}", flush=True)
                    print(f"   Added: {data['added_at']}", flush=True)
                    print(f"   Status: {status}", flush=True)
                    print(f"   API ID: {data['api_id']}", flush=True)
                    print("-" * 30, flush=True)
                
                print("\n0. Cancel", flush=True)
                
                try:
                    choice = input("\nEnter number: ").strip()
                    if choice == "0":
                        continue
                    
                    idx = int(choice)
                    if 1 <= idx <= len(user_list):
                        user_id = int(user_list[idx-1][0])
                        confirm = input(f"\nAre you sure you want to remove user {user_id}? (y/N): ").strip().lower()
                        if confirm == 'y':
                            success = whitelist_manager.remove_user(user_id)
                            if success:
                                print(f"\n✅ User {user_id} has been removed from the whitelist.", flush=True)
                            else:
                                print("\n❌ Failed to remove user from whitelist.", flush=True)
                        else:
                            print("\nOperation cancelled.", flush=True)
                    else:
                        print("\n❌ Invalid selection.", flush=True)
                except ValueError:
                    print("\n❌ Invalid input. Please enter a number.", flush=True)
                input("\nPress Enter to continue...")
                sys.stdout.flush()
            
            elif choice == "4":
                self._clear_screen()
                print("\nRegister Whitelisted User:", flush=True)
                
                # Get all unregistered whitelisted users
                users = whitelist_manager.get_all_users()
                unregistered_users = {
                    user_id: data for user_id, data in users.items() 
                    if not data.get('registered', False)
                }
                
                if not unregistered_users:
                    print("\n❌ No unregistered users found in whitelist.", flush=True)
                    input("\nPress Enter to continue...")
                    sys.stdout.flush()
                    continue
                
                # Show menu of unregistered users
                print("\nSelect a user to register:", flush=True)
                user_list = list(unregistered_users.items())
                for idx, (user_id, data) in enumerate(user_list, 1):
                    added_date = data.get('added_at', 'Unknown')
                    print(f"{idx}. User ID: {user_id}", flush=True)
                    print(f"   Added: {added_date}", flush=True)
                    print(f"   API ID: {data['api_id']}", flush=True)
                    print("-" * 30, flush=True)
                
                print("\n0. Cancel", flush=True)
                
                try:
                    selection = input("\nEnter number of user to register: ").strip()
                    if selection == "0":
                        continue
                    
                    try:
                        idx = int(selection) - 1
                        if idx < 0 or idx >= len(user_list):
                            raise ValueError("Invalid selection")
                        
                        user_id, user_data = user_list[idx]
                        phone = input("\nEnter user's phone number (international format, e.g. +1234567890): ").strip()
                        
                        # Start registration process
                        print(f"\nAttempting to register User {user_id}...", flush=True)
                        
                        # Loop for phone number attempts
                        max_phone_attempts = 3
                        registration_successful = False
                        
                        for phone_attempt in range(max_phone_attempts):
                            try:
                                success, result = await whitelist_manager.register_user(user_id, phone)
                                
                                if success:
                                    print("\n✅ Verification code has been sent to the user's phone.", flush=True)
                                    print("⚠️ You have 2 minutes to enter the code before it expires!", flush=True)
                                    print("Enter the code as soon as you receive it.", flush=True)
                                    
                                    # Loop for code verification attempts
                                    max_code_attempts = 3
                                    for code_attempt in range(max_code_attempts):
                                        try:
                                            code = input("\nEnter the verification code from user (or 'r' to request new code): ").strip()
                                            
                                            if code.lower() == 'r':
                                                print("\nRequesting new verification code...", flush=True)
                                                break  # Break inner loop to request new code
                                            
                                            # Verify the code
                                            verify_success = await whitelist_manager.verify_code(user_id, code)
                                            
                                            if verify_success:
                                                print(f"\n✅ User {user_id} has been successfully registered!", flush=True)
                                                registration_successful = True
                                                break  # Break the code verification loop
                                            else:
                                                remaining = max_code_attempts - code_attempt - 1
                                                print(f"\n❌ Verification failed. Please try again.", flush=True)
                                                if remaining > 0:
                                                    print(f"You have {remaining} attempts remaining.", flush=True)
                                                else:
                                                    print("\n❌ Maximum code attempts reached.", flush=True)
                                                    break
                                        
                                        except Exception as e:
                                            print(f"\n❌ Error during code verification: {str(e)}", flush=True)
                                            logger.error(f"Code verification error for user {user_id}: {str(e)}")
                                            if code_attempt < max_code_attempts - 1:
                                                print("Trying again...", flush=True)
                                            else:
                                                print("\n❌ Maximum code attempts reached.", flush=True)
                                                break
                                
                                if registration_successful:
                                    break  # Break the phone number attempts loop if registration was successful
                                
                            except Exception as e:
                                print(f"\n❌ Error during registration: {str(e)}", flush=True)
                                logger.error(f"Registration error for user {user_id}: {str(e)}")
                                if phone_attempt < max_phone_attempts - 1:
                                    print("Trying again...", flush=True)
                                else:
                                    print("\n❌ Maximum registration attempts reached.", flush=True)
                                    break
                    
                    except ValueError:
                        print("\n❌ Invalid selection. Please enter a valid number.", flush=True)
                    
                except Exception as e:
                    print(f"\n❌ An error occurred: {str(e)}", flush=True)
                    logger.error(f"Error during user registration: {str(e)}")
                
                input("\nPress Enter to continue...")
                sys.stdout.flush()
            
            elif choice == "0":
                break
            else:
                print("\nInvalid choice. Please try again.", flush=True)
                await asyncio.sleep(1)
    
    async def _handle_database_settings(self):
        """Handle database settings menu"""
        while True:
            self._clear_screen()
            print("\nDatabase Settings:")
            print("1. View Database Status")
            print("2. Test Connections")
            print("3. Backup Database")
            print("4. Clear Cache")
            print("\n0. Back to Main Menu")
            
            choice = input("\nEnter your choice: ")
            
            if choice == "1":
                # Test database connections
                redis_status = "Connected" if db_manager.redis.ping() else "Disconnected"
                print(f"\nRedis Status: {redis_status}")
                try:
                    with db_manager.session_scope() as session:
                        postgres_status = "Connected"
                except Exception as e:
                    postgres_status = f"Error: {str(e)}"
                print(f"PostgreSQL Status: {postgres_status}")
                input("\nPress Enter to continue...")
            
            elif choice == "0":
                break
    
    async def _handle_sessions(self):
        """Handle sessions menu"""
        while True:
            self._clear_screen()
            print("\nSessions Management:")
            print("1. View Active Sessions")
            print("2. View Session Logs")
            print("3. Terminate Session")
            print("4. Export Session Data")
            print("\n0. Back to Main Menu")
            
            choice = input("\nEnter your choice: ")
            
            if choice == "1":
                sessions = await session_manager.list_sessions()
                if sessions:
                    print("\nActive Sessions:")
                    for session in sessions:
                        print(f"\nID: {session['session_id']}")
                        print(f"Phone: {session['phone']}")
                        print(f"Status: {'🟢 Active' if session['active'] else '🔴 Inactive'}")
                        print(f"Last Used: {session['last_used']}")
                else:
                    print("\nNo active sessions found.")
                input("\nPress Enter to continue...")
            
            elif choice == "0":
                break
    
    async def _start_controlbot(self):
        """Start the ControlBot process"""
        if self.controlbot_process and self.controlbot_process.poll() is None:
            print("\nControlBot is already running!")
            return False
        
        try:
            # Debug: Print API credentials and bot token
            api_id = os.getenv('API_ID')
            api_hash = os.getenv('API_HASH')
            bot_token = os.getenv('BOT_TOKEN')
            
            print("\nDebug - Loading credentials:", flush=True)
            print(f"API_ID: {api_id}", flush=True)
            print(f"API_HASH: {api_hash[:4]}..." if api_hash else "API_HASH: None", flush=True)
            print(f"BOT_TOKEN: {bot_token[:4]}..." if bot_token else "BOT_TOKEN: None", flush=True)
            
            if not all([api_id, api_hash, bot_token]):
                print("\nError: Missing required credentials!", flush=True)
                print("Please configure API_ID, API_HASH, and BOT_TOKEN in your .env file", flush=True)
                return False
            
            print("\nStarting ControlBot...", flush=True)
            
            # Start the bot in a new Python process
            bot_script = os.path.join(os.path.dirname(__file__), '..', 'run_bot.py')
            
            # Create the run_bot.py script if it doesn't exist
            if not os.path.exists(bot_script):
                print(f"\nCreating bot script at {bot_script}", flush=True)
                with open(bot_script, 'w') as f:
                    f.write("""import asyncio
import sys
from control.bot import control_bot
import logging
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Handle graceful shutdown
def signal_handler(signum, frame):
    print("Received shutdown signal...", flush=True)
    asyncio.create_task(shutdown())

async def shutdown():
    try:
        await control_bot.stop()
    except Exception as e:
        print(f"Error during shutdown: {str(e)}", flush=True)
    finally:
        sys.exit(0)

async def main():
    try:
        # Register signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        print("Starting ControlBot...", flush=True)
        await control_bot.start()
    except KeyboardInterrupt:
        print("Received shutdown signal...", flush=True)
        await control_bot.stop()
    except Exception as e:
        print(f"Error starting ControlBot: {str(e)}", flush=True)
        import traceback
        print(f"Traceback:\\n{traceback.format_exc()}", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Fatal error: {str(e)}", flush=True)
        sys.exit(1)
""")
                print("Bot script created successfully", flush=True)
            
            # Create subprocess with pipes
            print("\nExecuting bot process...", flush=True)
            
            # Create the process without output capture first
            self.controlbot_process = subprocess.Popen(
                [sys.executable, bot_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                bufsize=0,  # Unbuffered
                universal_newlines=False,  # Binary mode
                preexec_fn=os.setsid if sys.platform != 'win32' else None
            )
            
            # Wait a moment to check for immediate failures
            await asyncio.sleep(2)
            
            # Check if process started successfully
            if self.controlbot_process.poll() is not None:
                print(f"\nBot failed to start! Exit code: {self.controlbot_process.poll()}", flush=True)
                stdout, stderr = self.controlbot_process.communicate()
                print("\nProcess output:", flush=True)
                if stdout:
                    print(f"\nStandard output:\n{stdout.decode()}", flush=True)
                if stderr:
                    print(f"\nError output:\n{stderr.decode()}", flush=True)
                self.controlbot_process = None
                return False
            
            print("\nControlBot process started successfully!", flush=True)
            print("The bot will continue running in the background.", flush=True)
            
            # Create async streams
            stdout_reader = asyncio.StreamReader()
            stderr_reader = asyncio.StreamReader()
            
            stdout_protocol = asyncio.StreamReaderProtocol(stdout_reader)
            stderr_protocol = asyncio.StreamReaderProtocol(stderr_reader)
            
            # Get the event loop
            loop = asyncio.get_event_loop()
            
            # Create connections
            await loop.connect_read_pipe(lambda: stdout_protocol, self.controlbot_process.stdout)
            await loop.connect_read_pipe(lambda: stderr_protocol, self.controlbot_process.stderr)
            
            # Start a background task to monitor the process output
            async def monitor_output():
                try:
                    while self.controlbot_process and self.controlbot_process.poll() is None:
                        try:
                            # Read output with timeout
                            stdout_line = await asyncio.wait_for(stdout_reader.readline(), timeout=0.1)
                            if stdout_line:
                                line = stdout_line.decode().strip()
                                if line:
                                    print(f"[ControlBot] {line}", flush=True)
                            
                            # Check stderr
                            stderr_line = await asyncio.wait_for(stderr_reader.readline(), timeout=0.1)
                            if stderr_line:
                                line = stderr_line.decode().strip()
                                if line:
                                    print(f"[ControlBot Error] {line}", flush=True)
                            
                        except asyncio.TimeoutError:
                            # No output available, continue
                            await asyncio.sleep(0.1)
                        except Exception as e:
                            print(f"[ControlBot Monitor] Error reading output: {str(e)}", flush=True)
                            await asyncio.sleep(0.1)
                    
                    # Process has ended
                    if self.controlbot_process:
                        exit_code = self.controlbot_process.poll()
                        print(f"\n[ControlBot] Process ended with exit code: {exit_code}", flush=True)
                        
                        # Close process
                        self.controlbot_process = None
                
                except Exception as e:
                    print(f"[ControlBot Monitor] Fatal error: {str(e)}", flush=True)
                    if self.controlbot_process:
                        self.controlbot_process.terminate()
                        self.controlbot_process = None
            
            # Start monitoring in background
            asyncio.create_task(monitor_output())
            return True
            
        except Exception as e:
            logger.error(f"Failed to start ControlBot: {e}")
            print(f"\nFailed to start ControlBot: {str(e)}", flush=True)
            import traceback
            print(f"Error details:\n{traceback.format_exc()}", flush=True)
            if self.controlbot_process:
                self.controlbot_process.terminate()
                self.controlbot_process = None
            return False

    async def _stop_controlbot(self):
        """Stop the ControlBot process"""
        if not self.controlbot_process:
            print("\nControlBot is not running!")
            return False
        
        try:
            print("\nStopping ControlBot...", flush=True)
            
            # Import the control_bot instance
            from control.bot import control_bot
            
            # Call stop directly
            await control_bot.stop()
            
            # Wait for the process to stop
            try:
                await asyncio.sleep(1)  # Give time for logs to be written
                self.controlbot_process.terminate()
                await asyncio.sleep(0.5)  # Give process time to terminate
                
                if self.controlbot_process.poll() is None:
                    print("\nForcing ControlBot to stop...", flush=True)
                    self.controlbot_process.kill()
                    await asyncio.sleep(0.5)  # Give process time to die
            except Exception as e:
                print(f"\nError during process cleanup: {e}", flush=True)
            
            # Get any remaining output
            try:
                stdout, stderr = self.controlbot_process.communicate(timeout=2)
                if stdout:
                    print(f"\nBot output:\n{stdout.decode()}", flush=True)
                if stderr:
                    print(f"\nBot errors:\n{stderr.decode()}", flush=True)
            except Exception as e:
                print(f"\nError getting process output: {e}", flush=True)
            
            self.controlbot_process = None
            print("\nControlBot stopped successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop ControlBot: {e}")
            print(f"\nFailed to stop ControlBot: {e}")
            # Force kill if all else fails
            try:
                if self.controlbot_process:
                    self.controlbot_process.kill()
                    self.controlbot_process = None
            except:
                pass
            return False

    async def _handle_controlbot_settings(self):
        """Handle ControlBot settings menu"""
        while True:
            # Define ControlBot menu options
            controlbot_menu = [
                "1. Start ControlBot",
                "2. Stop ControlBot",
                "3. View Bot Status",
                "4. Edit Bot Settings",
                "5. View Command Permissions",
                "6. Edit Command Permissions",
                "\n0. Back to Main Menu"
            ]
            
            self._print_menu("ControlBot Settings", controlbot_menu, show_status=True)
            
            choice = input("\nEnter your choice: ").strip()
            sys.stdout.flush()
            
            if choice == "1":
                await self._start_controlbot()
                input("\nPress Enter to continue...")
                sys.stdout.flush()
            elif choice == "2":
                await self._stop_controlbot()
                input("\nPress Enter to continue...")
                sys.stdout.flush()
            elif choice == "3":
                self._clear_screen()
                print("\nControlBot Status:", flush=True)
                status = "🟢 Running" if (self.controlbot_process and self.controlbot_process.poll() is None) else "🔴 Stopped"
                print(f"Status: {status}", flush=True)
                if self.controlbot_process and self.controlbot_process.poll() is None:
                    from control.bot import control_bot
                    instances = len(control_bot.user_instances)
                    print(f"Active User Instances: {instances}", flush=True)
                    print("\nLast 5 Authentication States:", flush=True)
                    for user_id, state in list(control_bot.auth_states.items())[:5]:
                        print(f"User {user_id}: {state['step']}", flush=True)
                input("\nPress Enter to continue...")
                sys.stdout.flush()
            elif choice == "0":
                break
            else:
                print("\nInvalid choice. Please try again.", flush=True)
                await asyncio.sleep(1)
    
    async def _handle_shutdown(self):
        """Handle system shutdown"""
        print("\nInitiating shutdown sequence...")
        
        # Ask if user wants to stop ControlBot
        if self.controlbot_process and self.controlbot_process.poll() is None:
            choice = input("\nDo you want to stop the ControlBot as well? (y/N): ").strip().lower()
            if choice == 'y':
                print("Stopping ControlBot...")
                await self._stop_controlbot()
            else:
                print("ControlBot will continue running in the background.")
        
        # Close all active sessions
        sessions = await session_manager.list_sessions()
        for session in sessions:
            if session['active']:
                print(f"Ending session {session['session_id']}...")
                await session_manager.end_session(session['session_id'])
        
        # Close database connections
        print("Closing database connections...")
        db_manager.clear_cache()
        
        print("Shutdown complete!")
        self.running = False
    
    async def start(self):
        """Start the admin control panel"""
        # Define main menu options once
        main_menu = [
            "1. Configuration",
            "2. User Settings",
            "3. Database Settings",
            "4. Sessions",
            "5. ControlBot Settings",
            "6. Shutdown",
            "\n0. Exit"
        ]
        
        try:
            while self.running:
                # Wait a small amount to ensure terminal is ready
                await asyncio.sleep(0.1)
                
                # Display menu
                self._print_menu("Main Menu", main_menu)
                
                # Get user input
                choice = input("\nEnter your choice: ").strip()
                
                # Process the choice in a controlled manner
                if choice in ["1", "2", "3", "4", "5", "6", "0"]:
                    if choice == "1":
                        await self._handle_configuration()
                    elif choice == "2":
                        await self._handle_user_settings()
                    elif choice == "3":
                        await self._handle_database_settings()
                    elif choice == "4":
                        await self._handle_sessions()
                    elif choice == "5":
                        await self._handle_controlbot_settings()
                    elif choice == "6":
                        print("\nInitiating shutdown...", flush=True)
                        await asyncio.sleep(0.1)
                        await self._handle_shutdown()
                        break
                    elif choice == "0":
                        print("\nExiting admin panel...", flush=True)
                        break
                else:
                    print("\nInvalid choice. Please try again.", flush=True)
                    await asyncio.sleep(1)
                
                # Ensure output is flushed before next iteration
                sys.stdout.flush()
                sys.stderr.flush()
                
        except KeyboardInterrupt:
            print("\nReceived shutdown signal...", flush=True)
            await self._handle_shutdown()
        except Exception as e:
            logger.critical(f"Admin panel crashed: {e}")
            raise
        finally:
            # Ensure final messages are displayed
            print("\nAdmin panel stopped.", flush=True)
            sys.stdout.flush()
            sys.stderr.flush()

def main():
    """Main entry point"""
    try:
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Initialize the admin panel
        admin_panel = MainBotFoundation()
        
        # Run the admin panel in the event loop
        loop.run_until_complete(admin_panel.start())
        
    except KeyboardInterrupt:
        logger.info("Admin panel stopped by user.")
    except Exception as e:
        logger.critical(f"Admin panel crashed: {e}")
        raise
    finally:
        # Clean up
        try:
            pending = asyncio.all_tasks(loop)
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        
        loop.close()
        
        # Force flush any remaining output
        sys.stdout.flush()
        sys.stderr.flush()

if __name__ == "__main__":
    # Ensure proper terminal handling
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Disable output buffering
    sys.stdout.reconfigure(line_buffering=True)
    
    main() 