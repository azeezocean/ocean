from port_ocean.utils import http_async_client
import httpx
from typing import Any, AsyncGenerator, Optional, Union
from loguru import logger
from enum import StrEnum
import asyncio
from port_ocean.utils.cache import cache_iterator_result
from port_ocean.utils.async_iterators import stream_async_iterators_tasks
from port_ocean.context.ocean import ocean


PAGE_SIZE = 100


class ObjectKind(StrEnum):
    PROJECT = "project"
    AUDITLOG = "auditlog"
    FEATURE_FLAG = "flag"
    ENVIRONMENT = "environment"
    FEATURE_FLAG_STATUS = "flag-status"
    FLAG_DEPENDENCIES = "flag-dependencies"


class LaunchDarklyClient:
    def __init__(
        self, api_token: str, launchdarkly_url: str, webhook_secret: str | None = None
    ):
        self.api_url = f"{launchdarkly_url}/api/v2"
        self.api_token = api_token
        self.http_client = http_async_client
        self.http_client.headers.update(self.api_auth_header)
        self.webhook_secret = webhook_secret

    @property
    def api_auth_header(self) -> dict[str, Any]:
        return {
            "Authorization": f"{self.api_token}",
            "Content-Type": "application/json",
        }

    @classmethod
    def create_from_ocean_configuration(cls) -> "LaunchDarklyClient":
        logger.info(f"Initializing LaunchDarklyClient {ocean.integration_config}")
        return LaunchDarklyClient(
            launchdarkly_url=ocean.integration_config["launchdarkly_host"],
            api_token=ocean.integration_config["launchdarkly_token"],
            webhook_secret=ocean.integration_config["webhook_secret"],
        )

    async def get_paginated_resource(
        self, kind: str, resource_path: str | None = None, page_size: int = PAGE_SIZE
    ) -> AsyncGenerator[list[dict[str, Any]], None]:

        kind = kind + "s" if not kind.endswith("s") else kind + "es"

        url = kind if not resource_path else f"{kind}/{resource_path}"
        url = url.replace("auditlogs", ObjectKind.AUDITLOG)
        params = {"limit": page_size}

        while url:
            try:
                response = await self.send_api_request(
                    endpoint=url, query_params=params
                )
                items = response.get("items", [])
                logger.info(f"Received batch with {len(items)} items")
                yield items

                if "_links" in response and "next" in response["_links"]:
                    url = response["_links"]["next"]["href"]
                else:
                    total_count = response.get("totalCount")
                    logger.info(f"Fetched {total_count} {kind} from Launchdarkly")
                    break

            except httpx.HTTPStatusError as e:
                logger.error(
                    f"HTTP error with status code: {e.response.status_code} and response text: {e.response.text}"
                )
                raise
            except httpx.HTTPError as e:
                logger.error(
                    f"HTTP error occurred while fetching {kind} from LaunchDarkly: {e}"
                )
                raise

    async def send_api_request(
        self,
        endpoint: str,
        method: str = "GET",
        query_params: Optional[dict[str, Any]] = None,
        json_data: Optional[Union[dict[str, Any], list[Any]]] = None,
    ) -> dict[str, Any]:
        try:
            endpoint = endpoint.replace("/api/v2/", "")
            url = f"{self.api_url}/{endpoint}"
            logger.debug(
                f"URL: {url}, Method: {method}, Params: {query_params}, Body: {json_data}"
            )
            response = await self.http_client.request(
                method=method,
                url=url,
                params=query_params,
                json=json_data,
            )
            response.raise_for_status()

            logger.debug(f"Successfully retrieved data for endpoint: {endpoint}")

            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error on {endpoint}: {e.response.status_code} - {e.response.text}"
            )
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error on {endpoint}: {str(e)}")
            raise

    @cache_iterator_result()
    async def get_paginated_projects(
        self,
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        async for projects in self.get_paginated_resource(ObjectKind.PROJECT):
            logger.info(f"Retrieved {len(projects)} projects from launchdarkly")
            yield projects

    @cache_iterator_result()
    async def get_paginated_environments(
        self,
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        async for projects in self.get_paginated_projects():
            tasks = [
                self.fetch_environments_for_project(project) for project in projects
            ]
            environments = await asyncio.gather(*tasks)
            for environment_batch in environments:
                yield environment_batch

    async def fetch_environments_for_project(
        self, project: dict[str, Any]
    ) -> list[dict[str, Any]]:
        environments = []
        async for environment_batch in self.get_paginated_resource(
            ObjectKind.PROJECT,
            resource_path=f'{project["key"]}/{ObjectKind.ENVIRONMENT}s',
        ):
            updated_batch = [
                {**environment, "__projectKey": project["key"]}
                for environment in environment_batch
            ]
            environments.extend(updated_batch)
        return environments

    async def get_feature_flag_status(
        self, projectKey: str, featureFlagKey: str
    ) -> dict[str, Any]:
        endpoint = f"flag-status/{projectKey}/{featureFlagKey}"
        feature_flag_status = await self.send_api_request(endpoint)
        return feature_flag_status

    async def get_paginated_feature_flag_statuses(
        self,
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        async for environments in self.get_paginated_environments():
            tasks = [
                self.fetch_statuses_from_environment(environment)
                for environment in environments
            ]
            async for resource_groups_batch in stream_async_iterators_tasks(*tasks):
                yield resource_groups_batch

    async def fetch_statuses_from_environment(
        self, environment: dict[str, Any]
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        resource = f"{environment['__projectKey']}/{environment['key']}"
        async for statuses in self.get_paginated_resource(
            kind=ObjectKind.FEATURE_FLAG_STATUS, resource_path=resource
        ):
            updated_batch = [
                {
                    **status,
                    "__environmentKey": environment["key"],
                    "__projectKey": environment["__projectKey"],
                }
                for status in statuses
            ]
            yield updated_batch

    async def get_paginated_feature_flags(
        self,
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        async for projects in self.get_paginated_projects():
            tasks = [
                self.fetch_feature_flags_for_project(project) for project in projects
            ]

            feature_flags_batches = await asyncio.gather(*tasks)
            for feature_flags in feature_flags_batches:
                yield feature_flags

    async def fetch_feature_flags_for_project(
        self, project: dict[str, Any]
    ) -> list[dict[str, Any]]:
        feature_flags = []
        async for flags_batch in self.get_paginated_resource(
            ObjectKind.FEATURE_FLAG, resource_path=project["key"]
        ):
            updated_batch = [
                {**flag, "__projectKey": project["key"]} for flag in flags_batch
            ]
            feature_flags.extend(updated_batch)
        return feature_flags

    async def patch_webhook(self, webhook_id: str, webhook_secret: str) -> None:
        """Patch a webhook to add a secret."""

        patch_data = [{"op": "replace", "path": "/secret", "value": webhook_secret}]

        logger.info(f"Patching webhook {webhook_id} to add secret")
        await self.send_api_request(
            endpoint=f"webhooks/{webhook_id}", method="PATCH", json_data=patch_data
        )
        logger.info(f"Successfully patched webhook {webhook_id} with secret")

    async def get_feature_flag_dependencies(
        self, projectKey: str, featureFlagKey: str
    ) -> dict[str, Any]:
        """Get dependencies for a specific feature flag.
        
        This uses the beta API endpoint for flag dependencies.
        
        Returns:
            A dictionary containing:
            - dependencies: List of flags this flag depends on
            - dependentFlagConfigs: List of flags that depend on this flag
        """
        endpoint = f"flag-dependencies/{projectKey}/{featureFlagKey}"
        try:
            return await self.send_api_request(endpoint=endpoint)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"No dependencies found for {projectKey}/{featureFlagKey}")
                return {"dependencies": [], "dependentFlagConfigs": []}
            raise

    async def get_paginated_flag_dependencies(
        self,
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        """Get dependencies for all feature flags across all projects."""
        async for projects in self.get_paginated_projects():
            for project in projects:
                project_key = project["key"]
                feature_flags = []
                async for flags_batch in self.get_paginated_resource(
                    ObjectKind.FEATURE_FLAG, resource_path=project_key
                ):
                    feature_flags.extend(flags_batch)
                
                # Process in batches to avoid too many concurrent requests
                batch_size = 10
                for i in range(0, len(feature_flags), batch_size):
                    batch = feature_flags[i:i+batch_size]
                    tasks = [
                        self.fetch_flag_dependencies(project_key, flag["key"])
                        for flag in batch
                    ]
                    
                    dependencies_batches = await asyncio.gather(*tasks)
                    # Flatten the list of lists and filter out empty lists
                    dependencies = []
                    for deps in dependencies_batches:
                        dependencies.extend(deps)
                    
                    if dependencies:  # Only yield non-empty dependency lists
                        yield dependencies

    async def fetch_flag_dependencies(
        self, projectKey: str, featureFlagKey: str
    ) -> list[dict[str, Any]]:
        """Fetch dependencies for a specific flag and format them for Port."""
        try:
            dependencies = await self.get_feature_flag_dependencies(projectKey, featureFlagKey)
            
            # Format the dependencies data
            formatted_dependencies = []
            
            # Process flags that depend on this flag
            for dependent in dependencies.get("dependentFlagConfigs", []):
                formatted_dependencies.append({
                    "flagKey": featureFlagKey,
                    "dependentFlagKey": dependent["key"],
                    "dependentFlagName": dependent.get("name", dependent["key"]),
                    "projectKey": projectKey,
                    "dependentProjectKey": dependent["projectKey"],
                    "relationshipType": "is_depended_on_by",
                    "__projectKey": projectKey,
                })
                
            # Process flags that this flag depends on
            for dependency in dependencies.get("dependencies", []):
                formatted_dependencies.append({
                    "flagKey": featureFlagKey,
                    "dependentFlagKey": dependency["key"],
                    "dependentFlagName": dependency.get("name", dependency["key"]),
                    "projectKey": projectKey,
                    "dependentProjectKey": dependency["projectKey"],
                    "relationshipType": "depends_on",
                    "__projectKey": projectKey,
                })
                
            return formatted_dependencies
        except Exception as e:
            logger.error(f"Error fetching dependencies for {projectKey}/{featureFlagKey}: {e}")
            return []

    async def get_feature_flag_status_with_dependencies(
        self, projectKey: str, featureFlagKey: str
    ) -> dict[str, Any]:
        """Get feature flag status with dependency information."""
        status = await self.get_feature_flag_status(projectKey, featureFlagKey)
        try:
            dependencies = await self.get_feature_flag_dependencies(projectKey, featureFlagKey)
            status["dependencies"] = dependencies.get("dependencies", [])
            status["dependentFlags"] = dependencies.get("dependentFlagConfigs", [])
            status["dependencyCount"] = len(dependencies.get("dependencies", []))
            status["dependentCount"] = len(dependencies.get("dependentFlagConfigs", []))
        except Exception as e:
            logger.error(f"Error fetching dependencies for {projectKey}/{featureFlagKey}: {e}")
            status["dependencies"] = []
            status["dependentFlags"] = []
            status["dependencyCount"] = 0
            status["dependentCount"] = 0
        return status

    async def create_launchdarkly_webhook(self, base_url: str) -> None:
        """Create or update a webxhook in LaunchDarkly."""
        webhook_target_url = f"{base_url}/integration/webhook"
        logger.info(f"Checking for existing webhook at {webhook_target_url}")

        notifications_response = await self.send_api_request(endpoint="webhooks")
        existing_configs = notifications_response.get("items", [])

        existing_webhook = next(
            (
                config
                for config in existing_configs
                if config["url"] == webhook_target_url
            ),
            None,
        )

        if not existing_webhook:
            logger.info("Creating new webhook")
            webhook_body = {
                "url": webhook_target_url,
                "description": "Port Integration Webhook",
                "sign": bool(self.webhook_secret),
                "secret": self.webhook_secret,
            }
            await self.send_api_request(
                endpoint="webhooks", method="POST", json_data=webhook_body
            )
            logger.info("Successfully created new webhook")
            return

        logger.info(f"Found existing webhook with ID: {existing_webhook['_id']}")

        if self.webhook_secret and not existing_webhook.get("secret"):
            logger.info("Existing webhook has no secret, adding one")
            await self.patch_webhook(existing_webhook["_id"], self.webhook_secret)
            return

        logger.info("Webhook already exists with appropriate configuration")
