# src/routes/automation_routes.py

from fastapi import APIRouter, Depends, HTTPException, status
import logging

from src.config.database import get_db
from src.middleware.auth import get_current_user
from src.models.user import UserInDB
from src.models.automation import (
    AutomationType,
    AutomationToggleRequest,
    AutomationStatusResponse,
    AutomationListResponse,
)
from src.services import automation_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("", response_model=AutomationListResponse)
async def get_all_automations(
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db),
):
    """Get status semua automation"""
    try:
        automations = await automation_manager.get_all_automations(db)
        return {
            "status": "success",
            "count": len(automations),
            "automations": automations,
        }
    except Exception as e:
        logger.error(f"Error get automations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{automation_type}", response_model=AutomationStatusResponse)
async def get_automation_status(
    automation_type: AutomationType,
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db),
):
    """Get status satu automation"""
    try:
        doc = await automation_manager.get_automation(db, automation_type)
        if not doc:
            raise HTTPException(status_code=404, detail="Automation tidak ditemukan")
        return {"status": "success", "automation": doc}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error get automation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{automation_type}/toggle", response_model=AutomationStatusResponse)
async def toggle_automation(
    automation_type: AutomationType,
    body: AutomationToggleRequest,
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db),
):
    """Aktifkan / non-aktifkan automation. Akan sync ke n8n juga."""
    try:
        result = await automation_manager.set_automation_enabled(
            db=db,
            automation_type=automation_type,
            enabled=body.enabled,
            updated_by=current_user.username,
            sync_to_n8n=True,
        )
        
        action = "diaktifkan" if body.enabled else "dijeda"
        logger.info(f"🔧 {current_user.username} {action} automation: {automation_type.value}")
        
        return {"status": "success", "automation": result}
    except Exception as e:
        logger.error(f"Error toggle automation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{automation_type}/refresh-n8n", response_model=AutomationStatusResponse)
async def refresh_n8n_status(
    automation_type: AutomationType,
    current_user: UserInDB = Depends(get_current_user),
    db = Depends(get_db),
):
    """Tarik ulang status workflow dari n8n (untuk health check)"""
    try:
        actual = await automation_manager.refresh_n8n_status(db, automation_type)
        if actual is None:
            raise HTTPException(
                status_code=503,
                detail="n8n tidak bisa dihubungi atau workflow_id belum di-set",
            )
        
        doc = await automation_manager.get_automation(db, automation_type)
        return {"status": "success", "automation": doc}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refresh n8n: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))