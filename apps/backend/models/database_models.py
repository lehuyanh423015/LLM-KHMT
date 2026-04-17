"""
SQLAlchemy ORM models for conversations and messages.

These tables store the chat history in SQLite.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from core.database import Base


class Conversation(Base):
    """A conversation session between the user and the AI."""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), index=True, nullable=True)
    title = Column(String(255), default="New Conversation")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship: one conversation has many messages
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Conversation(id={self.id}, title='{self.title}')>"


class Message(Base):
    """A single message within a conversation."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship back to conversation
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, role='{self.role}')>"

class CustomerProfile(Base):
    """Memory representation for a specific customer/session."""

    __tablename__ = "customer_profiles"

    session_id = Column(String(255), primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    budget = Column(String(255), nullable=True)
    preferred_category = Column(String(255), nullable=True)
    preferred_color = Column(String(255), nullable=True)
    priorities = Column(String(255), nullable=True)
    dislikes = Column(String(255), nullable=True)
    
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<CustomerProfile(session_id='{self.session_id}')>"
