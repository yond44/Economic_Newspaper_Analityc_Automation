"""Utility to list all API routes"""
import logging
from typing import List, Dict, Any
from fastapi import FastAPI
from fastapi.routing import APIRoute

logger = logging.getLogger(__name__)


def get_all_routes(app: FastAPI) -> List[Dict[str, Any]]:
    """
    Extract all routes from FastAPI app
    
    Returns:
        List of dicts with path, methods, name, and tags
    """
    routes = []
    
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append({
                "path": route.path,
                "methods": sorted(list(route.methods or ["GET"])),
                "name": route.name,
                "tags": route.tags or [],
                "summary": route.summary or ""
            })
    
    return sorted(routes, key=lambda x: x["path"])


def print_routes_table(app: FastAPI) -> None:
    """
    Print all routes in a formatted table
    """
    routes = get_all_routes(app)
    
    logger.info("\n" + "=" * 120)
    logger.info("📋 API ROUTES REGISTRY")
    logger.info("=" * 120)
    
    # Header
    logger.info(f"{'METHOD':<10} {'ENDPOINT':<60} {'SUMMARY':<50}")
    logger.info("-" * 120)
    
    # Group by method and endpoint
    by_path = {}
    for route in routes:
        path = route["path"]
        if path not in by_path:
            by_path[path] = []
        by_path[path].extend(route["methods"])
    
    # Print sorted
    for path in sorted(by_path.keys()):
        methods = ", ".join(sorted(by_path[path]))
        route_info = next(r for r in routes if r["path"] == path)
        summary = route_info["summary"][:47] if route_info["summary"] else ""
        
        logger.info(f"{methods:<10} {path:<60} {summary:<50}")
    
    logger.info("-" * 120)
    logger.info(f"Total endpoints: {len(by_path)}")
    logger.info("=" * 120 + "\n")


def print_routes_by_tag(app: FastAPI) -> None:
    """
    Print all routes grouped by tag
    """
    routes = get_all_routes(app)
    
    logger.info("\n" + "=" * 120)
    logger.info("📋 API ROUTES BY TAG")
    logger.info("=" * 120)
    
    # Group by tags
    by_tag = {}
    for route in routes:
        tags = route["tags"] or ["default"]
        for tag in tags:
            if tag not in by_tag:
                by_tag[tag] = []
            by_tag[tag].append(route)
    
    # Print by tag
    for tag in sorted(by_tag.keys()):
        logger.info(f"\n🏷️  {tag.upper()}")
        logger.info("-" * 120)
        
        for route in by_tag[tag]:
            methods = ", ".join(route["methods"])
            summary = route["summary"][:60] if route["summary"] else ""
            logger.info(f"  {methods:<15} {route['path']:<70} {summary}")
    
    logger.info("\n" + "=" * 120 + "\n")


def print_routes_detailed(app: FastAPI) -> None:
    """
    Print detailed route information
    """
    routes = get_all_routes(app)
    
    logger.info("\n" + "=" * 120)
    logger.info("📋 DETAILED ROUTES INFORMATION")
    logger.info("=" * 120)
    
    for i, route in enumerate(routes, 1):
        logger.info(f"\n{i}. {route['path']}")
        logger.info(f"   Methods: {', '.join(route['methods'])}")
        if route["summary"]:
            logger.info(f"   Summary: {route['summary']}")
        if route["tags"]:
            logger.info(f"   Tags: {', '.join(route['tags'])}")
        logger.info(f"   Handler: {route['name']}")
    
    logger.info("\n" + "=" * 120 + "\n")