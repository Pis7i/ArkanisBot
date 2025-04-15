import os
import base64
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from datetime import datetime, timedelta
import jwt
from .logger import logger

class SecurityManager:
    def __init__(self):
        self.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')
        self.encryption_key = self._get_or_create_encryption_key()
        self.fernet = Fernet(self.encryption_key)
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key from environment"""
        key = os.getenv('ENCRYPTION_KEY')
        if not key:
            # Generate a new key if none exists
            key = Fernet.generate_key()
            logger.warning(f"No encryption key found. Generated new key: {key.decode()}")
            logger.warning("Please add this key to your .env file as ENCRYPTION_KEY")
            return key
        
        try:
            # Try to decode the key if it's a string
            if isinstance(key, str):
                key = key.encode()
            
            # Validate the key format
            Fernet(key)
            return key
        except Exception as e:
            # If the key is invalid, generate a new one
            logger.error(f"Invalid encryption key: {str(e)}")
            new_key = Fernet.generate_key()
            logger.warning(f"Generated new encryption key: {new_key.decode()}")
            logger.warning("Please add this key to your .env file as ENCRYPTION_KEY")
            return new_key
    
    def encrypt_message(self, message: str) -> str:
        """Encrypt a message"""
        try:
            return self.fernet.encrypt(message.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise
    
    def decrypt_message(self, encrypted_message: str) -> Optional[str]:
        """Decrypt a message"""
        try:
            return self.fernet.decrypt(encrypted_message.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret_key, algorithm="HS256")
    
    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.JWTError as e:
            logger.error(f"Token verification failed: {e}")
            return None
    
    def generate_session_id(self) -> str:
        """Generate a unique session ID"""
        return base64.urlsafe_b64encode(os.urandom(32)).decode()
    
    def hash_password(self, password: str) -> str:
        """Hash a password using PBKDF2"""
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return f"{base64.urlsafe_b64encode(salt).decode()}:{key.decode()}"
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        try:
            salt_str, key_str = hashed_password.split(":")
            salt = base64.urlsafe_b64decode(salt_str.encode())
            stored_key = base64.urlsafe_b64decode(key_str.encode())
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = kdf.derive(password.encode())
            return key == stored_key
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False

# Create a default security manager instance
security_manager = SecurityManager() 