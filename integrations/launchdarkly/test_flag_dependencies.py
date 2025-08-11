#!/usr/bin/env python3
"""
Test script for LaunchDarkly flag dependencies implementation.
This script tests the flag dependencies API and formatting.
"""

import asyncio
import os
import json
from loguru import logger
from client import LaunchDarklyClient, ObjectKind

async def test_flag_dependencies():
    """Test the flag dependencies implementation."""
    # Get configuration from environment or use defaults
    api_token = os.environ.get("LAUNCHDARKLY_TOKEN", "your-api-token")
    launchdarkly_url = os.environ.get("LAUNCHDARKLY_HOST", "https://app.launchdarkly.com")
    
    # Initialize client
    client = LaunchDarklyClient(
        api_token=api_token,
        launchdarkly_url=launchdarkly_url,
        webhook_secret=None
    )
    
    logger.info("Testing LaunchDarkly flag dependencies implementation")
    
    # Get all projects
    projects = []
    async for project_batch in client.get_paginated_projects():
        projects.extend(project_batch)
    
    if not projects:
        logger.error("No projects found. Check your API token and URL.")
        return
    
    logger.info(f"Found {len(projects)} projects")
    
    # Get first project
    project = projects[0]
    project_key = project["key"]
    logger.info(f"Using project: {project_key}")
    
    # Get feature flags for the project
    feature_flags = []
    async for flags_batch in client.get_paginated_resource(
        ObjectKind.FEATURE_FLAG, resource_path=project_key
    ):
        feature_flags.extend(flags_batch)
    
    if not feature_flags:
        logger.error(f"No feature flags found in project {project_key}")
        return
    
    logger.info(f"Found {len(feature_flags)} feature flags in project {project_key}")
    
    # Test flag dependencies for each flag
    for flag in feature_flags[:5]:  # Test first 5 flags
        flag_key = flag["key"]
        logger.info(f"Testing dependencies for flag: {flag_key}")
        
        # Test direct API call
        try:
            dependencies = await client.get_feature_flag_dependencies(project_key, flag_key)
            logger.info(f"Raw dependencies for {flag_key}: {json.dumps(dependencies, indent=2)}")
        except Exception as e:
            logger.error(f"Error getting dependencies for {flag_key}: {e}")
            continue
        
        # Test formatted dependencies
        try:
            formatted_deps = await client.fetch_flag_dependencies(project_key, flag_key)
            logger.info(f"Formatted dependencies for {flag_key}: {json.dumps(formatted_deps, indent=2)}")
            logger.info(f"Found {len(formatted_deps)} dependency relationships")
        except Exception as e:
            logger.error(f"Error formatting dependencies for {flag_key}: {e}")
            continue
        
        # Test status with dependencies
        try:
            status_with_deps = await client.get_feature_flag_status_with_dependencies(project_key, flag_key)
            logger.info(f"Status with dependencies for {flag_key}:")
            logger.info(f"  Dependency count: {status_with_deps.get('dependencyCount', 0)}")
            logger.info(f"  Dependent count: {status_with_deps.get('dependentCount', 0)}")
        except Exception as e:
            logger.error(f"Error getting status with dependencies for {flag_key}: {e}")
    
    logger.info("Flag dependencies testing completed")

if __name__ == "__main__":
    asyncio.run(test_flag_dependencies())
