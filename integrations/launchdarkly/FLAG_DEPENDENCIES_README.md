# LaunchDarkly Flag Dependencies Feature

This document provides an overview of the flag dependencies feature implementation in the Port Ocean LaunchDarkly integration.

## Overview

The flag dependencies feature enhances the LaunchDarkly integration by providing visibility into relationships between feature flags. This allows users to understand which flags depend on other flags and which flags are depended upon, enabling better risk assessment and change management.

## Implementation Details

The implementation includes:

1. **New API Client Methods**:
   - `get_feature_flag_dependencies`: Fetches raw dependency data from LaunchDarkly's beta API
   - `fetch_flag_dependencies`: Formats dependency data for Port
   - `get_paginated_flag_dependencies`: Retrieves dependencies for all flags
   - `get_feature_flag_status_with_dependencies`: Enhances flag status with dependency information

2. **New Object Kind**:
   - Added `FLAG_DEPENDENCIES` to the `ObjectKind` enum

3. **Resync Handler**:
   - Added `on_resync_flag_dependencies` to process flag dependencies during resync

4. **Webhook Processing**:
   - Updated `FeatureFlagWebhookProcessor` to handle dependency information
   - Added support for the new `FLAG_DEPENDENCIES` kind

5. **Port Blueprints**:
   - Added `launchDarklyFlagDependency` blueprint for dependency relationships
   - Updated `launchDarklyFFInEnvironment` blueprint with dependency counts

## Data Model

The flag dependencies feature introduces two main data structures:

1. **Flag Dependency Relationship**:
   - Source flag information (key, project)
   - Dependent flag information (key, name, project)
   - Relationship type (`depends_on` or `is_depended_on_by`)

2. **Enhanced Flag Status**:
   - Added dependency counts
   - Lists of dependent flags and flags depended on

## Testing

A test script (`test_flag_dependencies.py`) is provided to verify the implementation. To run the test:

1. Set environment variables:
   ```
   export LAUNCHDARKLY_TOKEN=your-api-token
   export LAUNCHDARKLY_HOST=https://app.launchdarkly.com
   ```

2. Run the test script:
   ```
   python test_flag_dependencies.py
   ```

## Usage

After deploying this feature, users will be able to:

1. View dependency counts on feature flags
2. See which flags depend on a specific flag
3. See which flags a specific flag depends on
4. Navigate through dependency relationships in Port

## Notes

- The LaunchDarkly flag dependencies API is in beta and may change
- Performance optimizations include batch processing to minimize API calls
- Error handling is implemented to gracefully handle missing dependencies

## Future Enhancements

Potential future enhancements include:

1. Dependency graph visualization
2. Dependency change tracking and alerting
3. Impact analysis for flag changes based on dependencies
