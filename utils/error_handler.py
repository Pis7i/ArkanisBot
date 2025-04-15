import functools
import traceback
import inspect
import sys
from datetime import datetime
from utils.logger import logger

def get_function_context(func, args, kwargs):
    """Get detailed information about the function and its arguments"""
    # Get function details
    module = inspect.getmodule(func)
    module_name = module.__name__ if module else "unknown_module"
    
    # Get source code information
    try:
        source_lines, start_line = inspect.getsourcelines(func)
        source_code = ''.join(source_lines)
        file_name = inspect.getfile(func)
    except Exception:
        source_code = "Could not retrieve source code"
        start_line = 0
        file_name = "unknown_file"

    # Format arguments
    arg_spec = inspect.getfullargspec(func)
    formatted_args = []
    
    # Handle positional arguments
    for i, arg in enumerate(args):
        arg_name = arg_spec.args[i] if i < len(arg_spec.args) else f'arg{i}'
        formatted_args.append(f"{arg_name}={repr(arg)}")
    
    # Handle keyword arguments
    for key, value in kwargs.items():
        formatted_args.append(f"{key}={repr(value)}")
    
    return {
        'function_name': func.__name__,
        'module_name': module_name,
        'file_name': file_name,
        'start_line': start_line,
        'source_code': source_code,
        'arguments': ', '.join(formatted_args)
    }

def format_error_details(error, context):
    """Format error details into a readable string"""
    timestamp = datetime.now().isoformat()
    error_type = type(error).__name__
    error_msg = str(error)
    
    # Get full traceback
    exc_type, exc_value, exc_traceback = sys.exc_info()
    tb_list = traceback.extract_tb(exc_traceback)
    
    # Format traceback into readable lines
    tb_formatted = []
    for filename, line, func, text in tb_list:
        tb_formatted.append(f"  File '{filename}', line {line}, in {func}")
        if text:
            tb_formatted.append(f"    {text}")
    
    # Build detailed error message
    details = [
        "🚨 ERROR DETAILS 🚨",
        "=" * 50,
        f"Timestamp: {timestamp}",
        f"Error Type: {error_type}",
        f"Error Message: {error_msg}",
        "",
        "FUNCTION CONTEXT",
        "=" * 50,
        f"Function: {context['function_name']}",
        f"Module: {context['module_name']}",
        f"File: {context['file_name']}",
        f"Line: {context['start_line']}",
        f"Arguments: {context['arguments']}",
        "",
        "SOURCE CODE",
        "=" * 50,
        context['source_code'],
        "",
        "TRACEBACK",
        "=" * 50,
        *tb_formatted,
        "=" * 50
    ]
    
    return '\n'.join(details)

def error_handler(func):
    """Decorator that provides detailed error handling and logging."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # Get the full traceback
            exc_type, exc_value, exc_traceback = sys.exc_info()
            
            # Get the last frame from the traceback (where the error occurred)
            tb = traceback.extract_tb(exc_traceback)
            error_frame = tb[-1]  # Last frame is where the error occurred
            
            # Format error location
            error_location = f"{error_frame.filename}:{error_frame.lineno}"
            
            # Get the function context
            frame = inspect.currentframe()
            func_name = func.__name__
            module = inspect.getmodule(func)
            module_name = module.__name__ if module else "unknown_module"
            
            # Format timestamp
            timestamp = datetime.now().isoformat()
            
            # Build detailed error message
            error_details = [
                "🚨 ERROR DETAILS 🚨",
                "=" * 50,
                f"Timestamp: {timestamp}",
                f"Error Type: {type(e).__name__}",
                f"Error Message: {str(e)}",
                f"Error Location: {error_location}",
                "",
                "FUNCTION CONTEXT",
                "=" * 50,
                f"Function: {func_name}",
                f"Module: {module_name}",
                "",
                "TRACEBACK",
                "=" * 50
            ]
            
            # Add formatted traceback
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            error_details.extend(tb_lines)
            
            # Log the detailed error
            for line in error_details:
                logger.error(line)
            
            # If this is a Telegram-related function (has 'event' in args)
            # Try to send error message to user
            try:
                event = next((arg for arg in args if hasattr(arg, 'respond')), None)
                if event:
                    error_msg = (
                        f"❌ **Error Occurred**\n\n"
                        f"**Type:** {type(e).__name__}\n"
                        f"**Message:** {str(e)}\n"
                        f"**Location:** {error_location}\n"
                        f"**Function:** {func_name}\n"
                        f"**Module:** {module_name}"
                    )
                    await event.respond(error_msg)
            except Exception as notify_error:
                logger.error(f"Failed to notify user of error: {str(notify_error)}")
            
            # Re-raise the original exception
            raise
            
    return wrapper 