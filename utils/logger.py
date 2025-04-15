import logging
import os
from datetime import datetime
from elasticsearch import Elasticsearch
from typing import Optional
import sys

class CustomLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Create logs directory if it doesn't exist
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handlers
        # Main log file
        main_log_file = os.path.join(logs_dir, 'arkanisbot.log')
        file_handler = logging.FileHandler(main_log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Error log file
        error_log_file = os.path.join(logs_dir, 'error.log')
        error_handler = logging.FileHandler(error_log_file)
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s\n'
            'File: %(pathname)s\n'
            'Line: %(lineno)d\n'
            'Function: %(funcName)s\n'
            '%(exc_info)s\n'
        )
        error_handler.setFormatter(error_formatter)
        self.logger.addHandler(error_handler)
        
        # Elasticsearch handler (if configured)
        self.es: Optional[Elasticsearch] = None
        self.setup_elasticsearch()
        
        # Log startup
        self.logger.info(f"Logger initialized. Logs will be written to {logs_dir}")
    
    def setup_elasticsearch(self):
        """Initialize Elasticsearch connection if URL is provided"""
        es_url = os.getenv('ELASTICSEARCH_URL')
        if es_url:
            try:
                # Suppress Elasticsearch warnings
                import warnings
                warnings.filterwarnings("ignore", category=Warning, module="elasticsearch")
                
                # Initialize with security disabled warning suppressed
                self.es = Elasticsearch(
                    es_url,
                    verify_certs=False,
                    ssl_show_warn=False
                )
                
                if not self.es.ping():
                    self.logger.warning("Could not connect to Elasticsearch - logging will continue without it")
                    self.es = None
                else:
                    self.logger.info("Successfully connected to Elasticsearch")
            except Exception as e:
                self.logger.warning(f"Elasticsearch initialization failed (logging will continue without it): {e}")
                self.es = None
        else:
            # Elasticsearch is optional, so just log a debug message
            self.logger.debug("No ELASTICSEARCH_URL provided - logging will continue without it")
            self.es = None
    
    def _log_to_elasticsearch(self, level: str, message: str, **kwargs):
        """Log message to Elasticsearch if available"""
        if not self.es:
            return  # Skip silently if Elasticsearch is not configured
            
        try:
            doc = {
                'timestamp': datetime.utcnow(),
                'level': level,
                'message': message,
                'metadata': kwargs,
            }
            self.es.index(index=f'arkanisbot-logs-{datetime.utcnow().strftime("%Y-%m")}',
                         document=doc)
        except Exception as e:
            # Only log Elasticsearch errors at debug level to avoid noise
            self.logger.debug(f"Failed to log to Elasticsearch: {e}")
    
    def debug(self, message: str, **kwargs):
        """Log debug level message"""
        self.logger.debug(message)
        self._log_to_elasticsearch('DEBUG', message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info level message"""
        self.logger.info(message)
        self._log_to_elasticsearch('INFO', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning level message"""
        self.logger.warning(message)
        self._log_to_elasticsearch('WARNING', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error level message"""
        self.logger.error(message)
        self._log_to_elasticsearch('ERROR', message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical level message"""
        self.logger.critical(message)
        self._log_to_elasticsearch('CRITICAL', message, **kwargs)

# Create a default logger instance
logger = CustomLogger('arkanisbot') 