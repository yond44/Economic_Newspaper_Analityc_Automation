# src/services/automation_manager.py

import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.models.automation import AutomationType, AutomationStatus

logger = logging.getLogger(__name__)

# Konfigurasi dari env
N8N_API_URL = os.getenv("N8N_API_URL", "http://jojoba-n8n:5678")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")

# Mapping AutomationType → workflow ID dari env
WORKFLOW_IDS = {
    AutomationType.N8N_AI_GENERATED: os.getenv("N8N_WORKFLOW_AI_GENERATED", ""),
    AutomationType.QUEUE_AUTOMATION: os.getenv("N8N_WORKFLOW_QUEUE", ""),
}

COLLECTION_NAME = "automation_settings"


# ============================================
# N8N API CLIENT
# ============================================

async def _n8n_request(
    method: str,
    endpoint: str,
    json_data: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Helper untuk panggil n8n REST API."""
    if not N8N_API_KEY:
        logger.warning("⚠️ N8N_API_KEY belum di-set, skip n8n API call")
        return None
    
    url = f"{N8N_API_URL.rstrip('/')}/api/v1{endpoint}"
    headers = {
        "X-N8N-API-KEY": N8N_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(method, url, headers=headers, json=json_data)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ n8n API {method} {endpoint} failed: {e.response.status_code} {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"❌ n8n API {method} {endpoint} error: {str(e)}")
        return None


async def n8n_get_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
    """Get info workflow dari n8n."""
    if not workflow_id:
        return None
    return await _n8n_request("GET", f"/workflows/{workflow_id}")


async def n8n_set_workflow_active(workflow_id: str, active: bool) -> bool:
    """Activate atau deactivate workflow di n8n."""
    if not workflow_id:
        logger.warning(f"⚠️ Workflow ID kosong, skip activation")
        return False
    
    action = "activate" if active else "deactivate"
    result = await _n8n_request("POST", f"/workflows/{workflow_id}/{action}")
    
    if result is not None:
        logger.info(f"✅ n8n workflow {workflow_id} {action}d")
        return True
    
    logger.error(f"❌ Gagal {action} workflow {workflow_id}")
    return False


# ============================================
# DATABASE: AUTOMATION SETTINGS
# ============================================

async def ensure_default_settings(db: AsyncIOMotorDatabase) -> None:
    """Pastikan semua AutomationType punya entry di DB. Jalankan di startup."""
    collection = db[COLLECTION_NAME]
    
    for auto_type in AutomationType:
        existing = await collection.find_one({"type": auto_type.value})
        if not existing:
            default_doc = {
                "type": auto_type.value,
                "enabled": False,
                "last_run_at": None,
                "last_run_status": None,
                "last_error": None,
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "skipped_runs": 0,
                "n8n_workflow_id": WORKFLOW_IDS.get(auto_type, ""),
                "n8n_workflow_active": None,
                "updated_at": datetime.utcnow(),
                "updated_by": "system",
            }
            await collection.insert_one(default_doc)
            logger.info(f"📝 Created default automation setting: {auto_type.value}")


async def get_automation(
    db: AsyncIOMotorDatabase,
    automation_type: AutomationType,
) -> Optional[Dict[str, Any]]:
    """Get status satu automation."""
    collection = db[COLLECTION_NAME]
    doc = await collection.find_one({"type": automation_type.value})
    
    if doc:
        doc.pop("_id", None)
    return doc


async def get_all_automations(db: AsyncIOMotorDatabase) -> Dict[str, Dict[str, Any]]:
    """Get semua automation status."""
    collection = db[COLLECTION_NAME]
    result: Dict[str, Dict[str, Any]] = {}
    
    async for doc in collection.find({}):
        doc.pop("_id", None)
        auto_type = doc.get("type")
        if auto_type:
            result[auto_type] = doc
    
    # Fill in missing types
    for auto_type in AutomationType:
        if auto_type.value not in result:
            result[auto_type.value] = {
                "type": auto_type.value,
                "enabled": False,
                "n8n_workflow_id": WORKFLOW_IDS.get(auto_type, ""),
                "total_runs": 0, "successful_runs": 0,
                "failed_runs": 0, "skipped_runs": 0,
            }
    
    return result


async def is_automation_enabled(
    db: AsyncIOMotorDatabase,
    automation_type: AutomationType,
) -> bool:
    """Quick check: apakah automation aktif. Default False kalau belum di-set."""
    doc = await get_automation(db, automation_type)
    return bool(doc and doc.get("enabled", False))


async def set_automation_enabled(
    db: AsyncIOMotorDatabase,
    automation_type: AutomationType,
    enabled: bool,
    updated_by: Optional[str] = None,
    sync_to_n8n: bool = True,
) -> Dict[str, Any]:
    """Set automation on/off di DB dan optionally di n8n."""
    collection = db[COLLECTION_NAME]
    
    workflow_id = WORKFLOW_IDS.get(automation_type, "")
    n8n_sync_success = None
    n8n_error = None
    
    # Sync ke n8n dulu (kalau ada workflow id dan diminta)
    if sync_to_n8n and workflow_id:
        try:
            n8n_sync_success = await n8n_set_workflow_active(workflow_id, enabled)
            if not n8n_sync_success:
                n8n_error = "n8n API call failed (cek log)"
        except Exception as e:
            n8n_error = str(e)
            n8n_sync_success = False
    
    # Update DB
    update_doc = {
        "enabled": enabled,
        "n8n_workflow_id": workflow_id,
        "n8n_workflow_active": n8n_sync_success if sync_to_n8n else None,
        "updated_at": datetime.utcnow(),
        "updated_by": updated_by or "unknown",
    }
    if n8n_error:
        update_doc["last_error"] = f"n8n sync: {n8n_error}"
    
    await collection.update_one(
        {"type": automation_type.value},
        {"$set": update_doc, "$setOnInsert": {
            "type": automation_type.value,
            "total_runs": 0, "successful_runs": 0,
            "failed_runs": 0, "skipped_runs": 0,
        }},
        upsert=True,
    )
    
    logger.info(
        f"🔧 Automation {automation_type.value} → enabled={enabled}, "
        f"n8n_sync={n8n_sync_success}, by={updated_by}"
    )
    
    return await get_automation(db, automation_type) or {}


async def record_run(
    db: AsyncIOMotorDatabase,
    automation_type: AutomationType,
    status: str,  # "success" | "failed" | "skipped"
    error: Optional[str] = None,
) -> None:
    """Catat satu run untuk metrik."""
    collection = db[COLLECTION_NAME]
    
    inc = {"total_runs": 1}
    if status == "success":
        inc["successful_runs"] = 1
    elif status == "failed":
        inc["failed_runs"] = 1
    elif status == "skipped":
        inc["skipped_runs"] = 1
    
    set_doc = {
        "last_run_at": datetime.utcnow(),
        "last_run_status": status,
    }
    if error:
        set_doc["last_error"] = error
    elif status == "success":
        set_doc["last_error"] = None
    
    await collection.update_one(
        {"type": automation_type.value},
        {"$inc": inc, "$set": set_doc},
        upsert=True,
    )


async def refresh_n8n_status(
    db: AsyncIOMotorDatabase,
    automation_type: AutomationType,
) -> Optional[bool]:
    """Tarik status aktual dari n8n dan simpan. Berguna untuk health check."""
    workflow_id = WORKFLOW_IDS.get(automation_type, "")
    if not workflow_id:
        return None
    
    workflow = await n8n_get_workflow(workflow_id)
    if workflow is None:
        return None
    
    actual_active = bool(workflow.get("active", False))
    
    await db[COLLECTION_NAME].update_one(
        {"type": automation_type.value},
        {"$set": {
            "n8n_workflow_active": actual_active,
            "updated_at": datetime.utcnow(),
        }},
    )
    
    return actual_active