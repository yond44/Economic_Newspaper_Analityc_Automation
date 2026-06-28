# src/services/history_manager.py

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from bson import ObjectId

from src.models.history import (
    SentHistoryCreate,
    SentHistoryUpdate,
    SentHistoryResponse,
    DeliveryStatus,
    ChannelType
)

logger = logging.getLogger(__name__)


def convert_history_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MongoDB document to API response format"""
    if not doc:
        return None
    
    result = dict(doc)
    if '_id' in result:
        result['_id'] = str(result['_id'])
    return result


async def create_history_entry(
    db,
    history_data: SentHistoryCreate,
    user_id: Optional[str] = None,
    username: Optional[str] = None
) -> Optional[str]:
    """Create a new sent history entry"""
    try:
        collection = db["sent_history"]
        
        history_doc = history_data.dict()
        
        # Add timestamps
        now = datetime.utcnow()
        history_doc["created_at"] = now
        history_doc["sent_at"] = now
        history_doc["updated_at"] = now
        
        # Add user info if provided
        if user_id:
            history_doc["user_id"] = user_id
        if username:
            history_doc["username"] = username
        
        # Set default status if not set
        if "status" not in history_doc:
            history_doc["status"] = DeliveryStatus.SENT
        
        # Set recipient count
        if history_doc.get("recipients"):
            history_doc["recipient_count"] = len(history_doc["recipients"])
        
        # Ensure metadata is a dict
        if "metadata" not in history_doc or not history_doc["metadata"]:
            history_doc["metadata"] = {}
        
        result = await collection.insert_one(history_doc)
        logger.info(f"📝 History entry created: {result.inserted_id}")
        return str(result.inserted_id)
        
    except Exception as e:
        logger.error(f"Error creating history entry: {str(e)}")
        return None


async def get_history_entries(
    db,
    limit: int = 50,
    skip: int = 0,
    status: Optional[str] = None,
    channel: Optional[str] = None,
    user_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """Get sent history entries with filters"""
    try:
        collection = db["sent_history"]
        
        # Build filter
        filter_query = {}
        
        if status:
            filter_query["status"] = status
        
        if channel:
            filter_query["channel"] = channel
        
        if user_id:
            filter_query["user_id"] = user_id
        
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            filter_query["sent_at"] = date_filter
        
        # Query with sorting (newest first)
        cursor = collection.find(filter_query).sort("sent_at", -1).skip(skip).limit(limit)
        
        histories = []
        async for doc in cursor:
            histories.append(convert_history_doc(doc))
        
        return histories
        
    except Exception as e:
        logger.error(f"Error getting history entries: {str(e)}")
        return []


async def get_history_entry(db, history_id: str) -> Optional[Dict[str, Any]]:
    """Get a single history entry by ID"""
    try:
        collection = db["sent_history"]
        
        if not ObjectId.is_valid(history_id):
            return None
        
        doc = await collection.find_one({"_id": ObjectId(history_id)})
        return convert_history_doc(doc) if doc else None
        
    except Exception as e:
        logger.error(f"Error getting history entry: {str(e)}")
        return None


async def update_history_entry(
    db,
    history_id: str,
    update_data: SentHistoryUpdate
) -> bool:
    """Update a history entry"""
    try:
        collection = db["sent_history"]
        
        if not ObjectId.is_valid(history_id):
            return False
        
        update_dict = update_data.dict(exclude_unset=True)
        update_dict["updated_at"] = datetime.utcnow()
        
        # Handle specific status updates
        if update_dict.get("status") == DeliveryStatus.DELIVERED:
            update_dict["delivered_at"] = datetime.utcnow()
        elif update_dict.get("status") == DeliveryStatus.OPENED:
            update_dict["opened_at"] = datetime.utcnow()
        elif update_dict.get("status") == DeliveryStatus.CLICKED:
            update_dict["clicked_at"] = datetime.utcnow()
        
        result = await collection.update_one(
            {"_id": ObjectId(history_id)},
            {"$set": update_dict}
        )
        
        return result.modified_count > 0
        
    except Exception as e:
        logger.error(f"Error updating history entry: {str(e)}")
        return False


async def get_history_stats(
    db,
    days: int = 7,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get statistics for sent history"""
    try:
        collection = db["sent_history"]
        
        # Date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Build filter
        filter_query = {
            "sent_at": {"$gte": start_date, "$lte": end_date}
        }
        if user_id:
            filter_query["user_id"] = user_id
        
        # Get total counts
        pipeline = [
            {"$match": filter_query},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }}
        ]
        
        status_counts = {}
        async for doc in collection.aggregate(pipeline):
            status = doc.get("_id") or "unknown"
            status_counts[status] = doc.get("count", 0)
        
        # Get channel counts
        pipeline = [
            {"$match": filter_query},
            {"$group": {
                "_id": "$channel",
                "count": {"$sum": 1}
            }}
        ]
        
        channel_counts = {}
        async for doc in collection.aggregate(pipeline):
            channel = doc.get("_id") or "unknown"
            channel_counts[channel] = doc.get("count", 0)
        
        # Get daily counts for last 7 days
        daily_counts = {}
        for i in range(days):
            day = start_date + timedelta(days=i)
            next_day = day + timedelta(days=1)
            
            count = await collection.count_documents({
                "sent_at": {"$gte": day, "$lt": next_day},
                **({"user_id": user_id} if user_id else {})
            })
            
            daily_counts[day.strftime("%Y-%m-%d")] = count
        
        # Total counts
        total = await collection.count_documents(filter_query)
        
        return {
            "total_sent": total,
            "delivered": status_counts.get(DeliveryStatus.DELIVERED, 0),
            "failed": status_counts.get(DeliveryStatus.FAILED, 0),
            "bounced": status_counts.get(DeliveryStatus.BOUNCED, 0),
            "opened": status_counts.get(DeliveryStatus.OPENED, 0),
            "clicked": status_counts.get(DeliveryStatus.CLICKED, 0),
            "by_channel": channel_counts,
            "by_status": status_counts,
            "last_7_days": daily_counts
        }
        
    except Exception as e:
        logger.error(f"Error getting history stats: {str(e)}")
        return {}


async def delete_history_entry(db, history_id: str) -> bool:
    """Delete a history entry"""
    try:
        collection = db["sent_history"]
        
        if not ObjectId.is_valid(history_id):
            return False
        
        result = await collection.delete_one({"_id": ObjectId(history_id)})
        return result.deleted_count > 0
        
    except Exception as e:
        logger.error(f"Error deleting history entry: {str(e)}")
        return False


async def clear_history(db, user_id: Optional[str] = None) -> int:
    """Clear all history entries (or for a specific user)"""
    try:
        collection = db["sent_history"]
        
        filter_query = {}
        if user_id:
            filter_query["user_id"] = user_id
        
        result = await collection.delete_many(filter_query)
        logger.warning(f"🗑️ Cleared {result.deleted_count} history entries")
        return result.deleted_count
        
    except Exception as e:
        logger.error(f"Error clearing history: {str(e)}")
        return 0