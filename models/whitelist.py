from sqlalchemy import Column, Integer, String, Boolean, DateTime, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from utils.database import Base

class WhitelistedUser(Base):
    """SQLAlchemy model for whitelisted users"""
    __tablename__ = "whitelisted_users"

    user_id = Column(BigInteger, primary_key=True)
    api_id = Column(BigInteger, nullable=False)
    api_hash = Column(String, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    registered = Column(Boolean, default=False)
    session_string = Column(String, nullable=True)
    registration_step = Column(String, nullable=True)
    registration_phone = Column(String, nullable=True)
    phone_code_hash = Column(String, nullable=True)
    temp_session = Column(String, nullable=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    user_metadata = Column(JSONB, nullable=True)  # For any additional data

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'user_id': self.user_id,
            'api_id': self.api_id,
            'api_hash': self.api_hash,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'registered': self.registered,
            'session_string': self.session_string,
            'registration_step': self.registration_step,
            'registration_phone': self.registration_phone,
            'phone_code_hash': self.phone_code_hash,
            'temp_session': self.temp_session,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'metadata': self.user_metadata or {}  # Keep the dict key as metadata for compatibility
        }

    @classmethod
    def from_dict(cls, data: dict):
        """Create model from dictionary"""
        # Convert metadata to user_metadata for the model
        if 'metadata' in data:
            data['user_metadata'] = data.pop('metadata')
            
        if 'added_at' in data and isinstance(data['added_at'], str):
            data['added_at'] = datetime.fromisoformat(data['added_at'])
        if 'last_updated' in data and isinstance(data['last_updated'], str):
            data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        return cls(**data) 