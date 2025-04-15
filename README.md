# ArkanisBot: Telegram Automation System

A high-performance, modular Telegram automation system built with Python and Telethon.

## Features

- Multi-account management through UserBots
- Secure admin control panel
- Real-time monitoring and logging
- Containerized instance isolation
- Rate limiting and API protection
- Automated session management

## System Requirements

- Python 3.8+
- Redis
- PostgreSQL
- Docker (optional)
- Elasticsearch (optional)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/arkanisbot.git
cd arkanisbot
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Project Structure

```
arkanisbot/
├── core/                   # MainBotFoundation
│   ├── __init__.py
│   ├── foundation.py       # Core controller
│   ├── session.py         # Session management
│   └── security.py        # Security utilities
├── control/               # ControlBot
│   ├── __init__.py
│   ├── bot.py            # Telegram bot interface
│   └── handlers/         # Command handlers
├── userbot/              # UserBot implementation
│   ├── __init__.py
│   ├── client.py         # Telethon client
│   └── actions.py        # UserBot actions
├── api/                  # FastAPI implementation
│   ├── __init__.py
│   ├── main.py          # API endpoints
│   └── websocket.py     # WebSocket handlers
└── utils/               # Utility functions
    ├── __init__.py
    ├── database.py     # Database utilities
    └── logger.py       # Logging configuration
```

## Configuration

Create a `.env` file with the following variables:
```
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
BOT_TOKEN=your_bot_token
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql://user:password@localhost:5432/arkanisbot
```

## Usage

1. Start the main bot:
```bash
python -m core.foundation
```

2. Start the API server:
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Security Considerations

- All UserBot instances run in isolated containers
- End-to-end encryption for ControlBot-UserBot communication
- Rate limiting on all API endpoints
- Secure session storage using Redis
- Regular security audits and updates

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 