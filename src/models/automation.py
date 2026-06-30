# src/models/automation.py

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class AutomationType(str, Enum):
    """Jenis automation yang bisa dikontrol"""
    N8N_AI_GENERATED = "n8n_ai_generated"
    QUEUE_AUTOMATION = "queue_automation"


class AutomationStatus(BaseModel):
    """Status satu automation"""
    type: AutomationType
    enabled: bool = Field(default=False, description="Apakah automation aktif")
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = Field(None, description="success/failed/skipped")
    last_error: Optional[str] = None
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    skipped_runs: int = Field(0, description="Berapa kali di-skip karena paused")
    n8n_workflow_id: Optional[str] = None
    n8n_workflow_active: Optional[bool] = Field(None, description="Status aktual di n8n")
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class AutomationToggleRequest(BaseModel):
    """Request untuk toggle on/off"""
    enabled: bool


class AutomationStatusResponse(BaseModel):
    """Response status satu automation"""
    status: str = "success"
    automation: AutomationStatus


class AutomationListResponse(BaseModel):
    """Response semua automation"""
    status: str = "success"
    count: int
    automations: Dict[str, AutomationStatus]