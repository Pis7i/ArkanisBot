import asyncio
import sys
import signal
from datetime import datetime
from control.bot import control_bot
from utils.logger import logger

# Flags to track shutdown state
_shutdown_requested = False
_cleanup_timeout = 10  # seconds

def handle_signal(signum, frame):
    """Handle termination signals"""
    global _shutdown_requested
    signame = signal.Signals(signum).name
    
    if _shutdown_requested:
        logger.warning(f"\nReceived second signal {signame}, immediate exit...")
        sys.stdout.flush()
        sys.exit(1)
    else:
        logger.info(f"\nReceived signal {signame}, starting graceful shutdown...")
        _shutdown_requested = True
    sys.stdout.flush()

async def cleanup():
    """Perform cleanup when the bot is stopping"""
    try:
        logger.info("Initiating graceful shutdown...")
        sys.stdout.flush()

        try:
            # Use wait_for to add timeout to cleanup
            await asyncio.wait_for(control_bot.stop(), timeout=_cleanup_timeout)
            logger.info("Bot stopped successfully")
        except asyncio.TimeoutError:
            logger.warning(f"Cleanup timed out after {_cleanup_timeout} seconds")
        except Exception as e:
            logger.error(f"Error during bot stop: {str(e)}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}", exc_info=True)
    finally:
        # Ensure we flush all logs
        sys.stdout.flush()
        sys.stderr.flush()

async def main():
    """Main entry point"""
    global _shutdown_requested
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    try:
        logger.info("=== Starting ControlBot ===")
        sys.stdout.flush()
        
        # Start the bot
        await control_bot.start()
        
        # Keep running until shutdown is requested
        while not _shutdown_requested:
            await asyncio.sleep(1)
        
        # Perform cleanup
        await cleanup()
            
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt received...")
        sys.stdout.flush()
        await cleanup()
    except Exception as e:
        logger.error("=== Fatal Error in Main Loop ===")
        logger.error(f"Error details: {str(e)}", exc_info=True)
        sys.stdout.flush()
        await cleanup()
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        # Ensure final log message is written before exit
        logger.info("Bot shutdown complete")
        sys.stdout.flush()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        # Final cleanup at top level
        logger.info("Bot shutdown by keyboard interrupt")
        sys.stdout.flush()
        sys.exit(0)
    except Exception as e:
        logger.error("=== Fatal Error ===")
        logger.error(f"Error details: {str(e)}", exc_info=True)
        sys.stdout.flush()
        sys.stderr.flush()
        sys.exit(1)
