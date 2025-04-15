# ArkanisBot Documentation

## Overview
ArkanisBot is a Telegram bot that provides user authentication through a Gateway API and allows users to manage their Telegram accounts with features like message forwarding, group management, and various tools.

## Project Structure
```
ArkanisBot/
├── control/
│   ├── auth.py              # Gateway API authentication
│   ├── bot.py              # Main bot class and core functionality
│   ├── handlers/           # Message and callback handlers
│   │   ├── __init__.py
│   │   ├── message_handlers.py
│   │   └── callback_handlers.py
│   └── modules/            # Feature modules
│       ├── __init__.py
│       ├── menu.py
│       └── user_instance.py
├── core/
│   └── session.py         # Session management
├── utils/
│   ├── logger.py          # Logging utilities
│   ├── whitelist.py       # User whitelist management
│   └── database.py        # Database operations
└── data/                  # Data storage
    └── instances.json     # User instances storage
```

## Core Components

### 1. ControlBot (`control/bot.py`)
The main bot class that handles:
- Bot initialization and configuration
- User instance management
- Message routing
- Authentication state management

Key methods:
- `_load_instances()`: Loads saved user instances
- `_save_instances()`: Saves user instances to disk
- `_ensure_authenticated()`: Verifies user authentication
- `_handle_message()`: Routes incoming messages

### 2. Authentication System (`control/auth.py`)
Handles user authentication through Gateway API:

#### GatewayAuth Class
- Manages communication with Telegram Gateway API
- Handles verification code sending and checking
- Maintains authentication states

Key methods:
- `send_verification()`: Sends verification code
- `check_verification()`: Verifies entered code
- `handle_auth_state()`: Manages authentication flow
- `handle_phone_step()`: Processes phone number input
- `handle_code_step()`: Processes verification code input

### 3. User Management (`control/modules/user_instance.py`)
#### UserInstance Class
Represents an authenticated user's session with:
- Basic info (user_id, api_hash, phone)
- Session management
- Autoforwarding configuration
- Status tracking

Methods:
- `to_dict()`: Serializes instance data
- `from_dict()`: Creates instance from saved data

### 4. Menu System (`control/modules/menu.py`)
Handles all menu-related functionality:
- Main menu display
- Forwarding settings
- Account management
- Group management
- Tools and utilities

Key functions:
- `show_main_menu()`: Displays main control panel
- `show_forwarding_menu()`: Shows forwarding options
- `show_account_menu()`: Shows account settings
- `show_groups_menu()`: Shows group management
- `show_tools_menu()`: Shows additional tools

### 5. Message Handlers (`control/handlers/`)
#### Message Handlers (`message_handlers.py`)
Handles command messages:
- `/start`: Initiates authentication
- `/help`: Shows help message
- `/status`: Shows user status
- `/logout`: Ends session

#### Callback Handlers (`callback_handlers.py`)
Handles inline button callbacks for:
- Menu navigation
- Feature activation
- Settings changes

### 6. Session Management (`core/session.py`)
Manages Telegram user sessions:
- Session creation
- Session loading
- Session termination
- Session file management

### 7. Utilities
#### Logger (`utils/logger.py`)
Provides logging functionality across the application

#### Whitelist Manager (`utils/whitelist.py`)
Manages user access control:
- User verification
- API credential storage
- Registration status

#### Database Manager (`utils/database.py`)
Handles data persistence and caching

## Authentication Flow
1. User starts bot with `/start`
2. Bot checks whitelist status
3. User enters phone number
4. Bot validates phone number format and checks if it's registered
5. Gateway API sends verification code
6. User enters verification code
7. Gateway API verifies code
8. Bot creates UserInstance with:
   - User ID from Telegram
   - API hash from whitelist
   - Phone number from input
9. Bot initializes Telethon client:
   - Creates session file
   - Connects to Telegram
   - Verifies authorization
10. User gets access to main menu

### Session Management
The bot uses a multi-layered session system:
1. **Gateway Session**: Managed by Gateway API for initial verification
2. **Telethon Session**: Persistent `.session` files for Telegram MTProto
3. **Bot Session**: Tracks user state and configuration

#### Session Files
- Located in `sessions/` directory
- Named as `{user_id}.session`
- Contain Telegram authorization data
- Automatically loaded on reconnection

### Client Initialization
The client initialization process ensures:
1. **Connection**: Establishes connection to Telegram servers
2. **Authorization**: Verifies session validity
3. **State Management**: 
   - Updates activity timestamp
   - Starts inactivity monitor
   - Sets up cleanup tasks

### Error Recovery
The bot implements several error recovery mechanisms:
1. **Session Errors**:
   - Detects invalid/expired sessions
   - Prompts user to re-authenticate
   - Cleans up invalid session data
2. **Connection Issues**:
   - Attempts reconnection
   - Maintains session state
   - Notifies user of status
3. **Client Errors**:
   - Handles initialization failures
   - Manages disconnections
   - Provides clear error messages

### Security Measures
1. **Session Protection**:
   - Unique session per user
   - Automatic session cleanup
   - Inactivity monitoring
2. **Access Control**:
   - Whitelist verification
   - Phone number validation
   - Rate limiting on attempts
3. **Error Prevention**:
   - Input validation
   - State verification
   - Connection checking

## Data Flow
1. User sends message/command
2. Bot checks authentication
3. Message routed to appropriate handler
4. Handler processes request
5. Response sent to user
6. State changes saved to disk

## Security Features
- Gateway API verification
- Whitelist-based access control
- Session management
- Rate limiting
- Activity tracking

## Configuration
The bot requires:
- `GATEWAY_TOKEN`: For Gateway API access
- `BOT_TOKEN`: Telegram bot token
- Environment variables for API credentials

## Error Handling
- Comprehensive logging
- Graceful error recovery
- User-friendly error messages
- Session recovery mechanisms

## Best Practices
1. Always use Gateway API for verification
2. Maintain user session security
3. Log all important operations
4. Handle errors gracefully
5. Save state changes immediately
6. Validate user input
7. Rate limit operations
8. Keep user informed of status 