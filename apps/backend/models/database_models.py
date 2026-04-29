"""
SQLAlchemy ORM models for conversations and messages.

These tables store the chat history in SQLite.
"""

from datetime import datetime, timezone
import json

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean, Float
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


class DialogueState(Base):
    """Structured conversation state for orchestrator."""
    
    __tablename__ = "dialogue_states"
    
    session_id = Column(String(255), primary_key=True, index=True)
    
    # Primary intent tracking
    intent = Column(String(100), nullable=True)  # gift_recommendation, budget_advice, product_comparison, price_lookup
    sub_intent = Column(String(100), nullable=True)
    
    # Shopping context
    recipient = Column(String(255), nullable=True)
    occasion = Column(String(255), nullable=True)
    
    # Budget constraints
    budget_min = Column(Float, nullable=True)
    budget_max = Column(Float, nullable=True)
    budget_currency = Column(String(10), default="VND")
    budget_flexible = Column(Boolean, default=False)
    
    # Product preferences
    product_category = Column(String(255), nullable=True)
    excluded_categories = Column(JSON, default=list)  # JSON array of excluded categories
    preferences = Column(JSON, default=list)  # JSON array of preferred attributes
    constraints = Column(JSON, default=list)  # JSON array of constraints
    
    # Location and search
    location = Column(String(255), nullable=True)
    need_real_time_data = Column(Boolean, default=False)
    
    # User behavior
    price_sensitivity = Column(String(50), nullable=True)  # high, medium, low
    style_preference = Column(String(255), nullable=True)
    
    # Conversation management
    latest_user_goal = Column(Text, nullable=True)
    last_invalid_direction = Column(JSON, default=list)  # JSON array of failed suggestion types
    
    # Confidence and flags
    confidence = Column(Float, default=0.0)  # 0.0 to 1.0
    last_feedback_was_negative = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    def to_dict(self):
        """Convert state to dictionary for serialization."""
        return {
            "intent": self.intent,
            "sub_intent": self.sub_intent,
            "recipient": self.recipient,
            "occasion": self.occasion,
            "budget": {
                "min": self.budget_min,
                "max": self.budget_max,
                "currency": self.budget_currency,
                "flexible": self.budget_flexible
            },
            "product_category": self.product_category,
            "excluded_categories": self.excluded_categories or [],
            "preferences": self.preferences or [],
            "constraints": self.constraints or [],
            "location": self.location,
            "need_real_time_data": self.need_real_time_data,
            "price_sensitivity": self.price_sensitivity,
            "style_preference": self.style_preference,
            "latest_user_goal": self.latest_user_goal,
            "last_invalid_direction": self.last_invalid_direction or [],
            "confidence": self.confidence
        }
    
    def __repr__(self):
        return f"<DialogueState(session_id='{self.session_id}', intent='{self.intent}')>"

