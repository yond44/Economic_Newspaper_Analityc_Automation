"""Question Models"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class QuestionBase(BaseModel):
    """Base question model"""
    text: str = Field(..., min_length=1, max_length=500)
    source: Optional[str] = Field(default="api", description="Source of the question")
    status: Optional[str] = Field(default="pending", description="pending, processing, completed, archived")


class QuestionCreate(QuestionBase):
    """Create a new question"""
    pass


class QuestionResponse(QuestionBase):
    """Question response model"""
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class QuestionListResponse(BaseModel):
    """List of questions response"""
    status: str = "success"
    count: int
    questions: list[QuestionResponse]


class QuestionSingleResponse(BaseModel):
    """Single question response"""
    status: str = "success"
    question: QuestionResponse


class QuestionStatsResponse(BaseModel):
    """Question statistics response"""
    status: str = "success"
    stats: dict


class QuestionGenerateResponse(BaseModel):
    """Question generation response"""
    status: str = "success"
    question: str
    source: Optional[str] = None


class SuccessMessageResponse(BaseModel):
    """Success message response"""
    status: str = "success"
    message: str