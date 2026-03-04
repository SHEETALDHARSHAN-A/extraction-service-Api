# grpcio-yanked-version-fix Bugfix Design

## Overview

The post-processing-service Docker build fails because requirements.txt pins grpcio to version 1.78.1, which has been yanked from PyPI due to causing major outages in gcloud serverless environments. The fix involves updating the requirements.txt to specify a non-yanked, stable version of grpcio that maintains compatibility with the service's gRPC server functionality. This is a straightforward dependency version update with minimal risk since the service uses basic gRPC server features that are stable across recent grpcio versions.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when Docker attempts to build post-processing-service with grpcio==1.78.1 specified in requirements.txt
- **Property (P)**: The desired behavior - Docker build completes successfully and installs a non-yanked grpcio version
- **Preservation**: Existing gRPC server functionality (server creation, service registration, request handling) must remain unchanged
- **grpcio**: The Python gRPC runtime library that provides server and client implementations
- **Yanked Package**: A package version removed from PyPI's default installation path due to critical issues, but still visible in the index
- **post-processing-service**: The gRPC service in `services/post-processing-service/` that handles PII redaction, JSON validation, and confidence scoring

## Bug Details

### Fault Condition

The bug manifests when Docker attempts to build the post-processing-service image and pip tries to install the pinned grpcio==1.78.1 version. The package version is yanked from PyPI, causing pip to either timeout searching for the package or fail with a "yanked version" error.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type DockerBuildContext
  OUTPUT: boolean
  
  RETURN input.service == "post-processing-service"
         AND input.requirementsFile.contains("grpcio==1.78.1")
         AND packageIsYanked("grpcio", "1.78.1")
         AND input.buildStep == "pip install -r requirements.txt"
END FUNCTION
```

### Examples

- **Docker build with yanked version**: Building post-processing-service with `grpcio==1.78.1` in requirements.txt results in pip timeout or installation failure
- **Local development**: Running `pip install -r requirements.txt` locally fails with yanked package error
- **CI/CD pipeline**: Automated builds fail at the dependency installation step
- **Edge case - cached version**: If grpcio==1.78.1 is already in Docker layer cache or local pip cache, build may succeed but is not reproducible in clean environments

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- gRPC server creation and startup must continue to work exactly as before
- Service registration and request handling must remain unchanged
- Communication with other services via gRPC must continue without compatibility issues
- All existing gRPC functionality (ThreadPoolExecutor, insecure_port, server lifecycle) must work identically

**Scope:**
All inputs that do NOT involve the Docker build process with the yanked grpcio version should be completely unaffected by this fix. This includes:
- Runtime behavior of the post-processing-service
- gRPC protocol compatibility with clients
- Service functionality (PII redaction, validation, confidence scoring)
- Environment variable handling and configuration

## Hypothesized Root Cause

Based on the bug description and requirements.txt analysis, the root cause is clear:

1. **Pinned Yanked Version**: The requirements.txt file explicitly pins `grpcio==1.78.1`, which was yanked from PyPI on or after its release due to causing major outages in gcloud serverless environments

2. **PyPI Yanked Package Behavior**: When pip attempts to install a yanked package version:
   - The version is not available through normal installation channels
   - pip may timeout searching for the package
   - pip may show a warning that the version is yanked and refuse to install it
   - The build process fails at the `RUN pip install -r requirements.txt` step in the Dockerfile

3. **No Version Flexibility**: The exact pin (==) prevents pip from automatically selecting an alternative non-yanked version

4. **Build Environment Dependency**: The issue manifests in any clean build environment (local, CI/CD, production) where the yanked version is not already cached

## Correctness Properties

Property 1: Fault Condition - Docker Build Success with Non-Yanked grpcio

_For any_ Docker build context where post-processing-service is being built with requirements.txt specifying a non-yanked grpcio version, the Docker build SHALL complete successfully, installing the specified grpcio version without timeouts or yanked package errors.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - gRPC Functionality Unchanged

_For any_ runtime operation of the post-processing-service (server startup, request handling, service registration), the service with the updated grpcio version SHALL produce exactly the same behavior as with the original version, preserving all gRPC server functionality and inter-service communication capabilities.

**Validates: Requirements 3.1, 3.2, 3.3**

## Fix Implementation

### Changes Required

The fix is straightforward and involves updating a single line in the requirements file.

**File**: `services/post-processing-service/requirements.txt`

**Specific Changes**:
1. **Update grpcio version**: Replace `grpcio==1.78.1` with a non-yanked stable version
   - Recommended: `grpcio==1.68.1` (latest stable in 1.68.x series, widely used and tested)
   - Alternative: `grpcio>=1.68.0,<1.69.0` (allows patch updates within 1.68.x)
   - Rationale: Version 1.68.1 is stable, non-yanked, and maintains API compatibility with 1.78.1 for the basic server features used by this service

2. **Version Selection Criteria**:
   - Must be non-yanked on PyPI
   - Must support Python 3.11 (as specified in Dockerfile)
   - Must maintain backward compatibility for gRPC server API (grpc.server, add_insecure_port, ThreadPoolExecutor)
   - Should be a recent stable release to include security fixes

3. **No Code Changes Required**: The service uses only basic gRPC server APIs that are stable across versions:
   - `grpc.server(futures.ThreadPoolExecutor(max_workers=10))`
   - `server.add_insecure_port()`
   - `server.start()` and `server.wait_for_termination()`
   - These APIs have been stable since grpcio 1.x and require no modifications

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, confirm the bug exists with the yanked version, then verify the fix works correctly and preserves all existing functionality.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm that grpcio==1.78.1 is indeed yanked and causes build failures.

**Test Plan**: Attempt to build the Docker image with the current requirements.txt (grpcio==1.78.1) in a clean environment without cache. Observe the failure and document the exact error message.

**Test Cases**:
1. **Clean Docker Build**: Run `docker build` with `--no-cache` flag for post-processing-service (will fail on unfixed code)
2. **Direct pip Install**: Run `pip install grpcio==1.78.1` in a clean Python 3.11 environment (will fail or show yanked warning)
3. **PyPI API Check**: Query PyPI API to confirm version 1.78.1 is marked as yanked
4. **Cached Build Test**: Build with existing cache to confirm it may succeed but is not reproducible (edge case)

**Expected Counterexamples**:
- Docker build fails with timeout or "Could not find a version that satisfies the requirement grpcio==1.78.1"
- pip shows warning: "The candidate selected for download or install is a yanked version"
- Build time exceeds reasonable limits (>5 minutes for a simple pip install)

### Fix Checking

**Goal**: Verify that for all Docker build contexts where the updated grpcio version is specified, the build completes successfully.

**Pseudocode:**
```
FOR ALL buildContext WHERE isBugCondition(buildContext) == FALSE DO
  result := dockerBuild(buildContext)
  ASSERT result.status == "success"
  ASSERT result.installedPackages.contains("grpcio")
  ASSERT NOT result.installedPackages["grpcio"].isYanked
END FOR
```

**Test Cases**:
1. **Clean Build with Fix**: Build Docker image with updated grpcio version using `--no-cache`
2. **Build Time Verification**: Confirm build completes in reasonable time (<2 minutes for pip install step)
3. **Package Verification**: Verify installed grpcio version matches specification and is not yanked
4. **Multi-Environment Build**: Test build in different environments (local Docker, CI/CD, different OS)

### Preservation Checking

**Goal**: Verify that for all runtime operations of the service, the updated grpcio version produces the same behavior as the original version.

**Pseudocode:**
```
FOR ALL serviceOperation WHERE NOT isBuildOperation(serviceOperation) DO
  ASSERT postProcessingService_original(serviceOperation) = postProcessingService_fixed(serviceOperation)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across different gRPC operations
- It catches edge cases in request handling that manual tests might miss
- It provides strong guarantees that gRPC functionality is unchanged across version updates

**Test Plan**: First, verify the service works correctly with a known-good grpcio version (e.g., 1.68.1 installed manually), then write tests capturing that behavior to run after the fix.

**Test Cases**:
1. **Server Startup Preservation**: Verify server starts successfully and listens on port 50052
2. **Request Handling Preservation**: Send test gRPC requests and verify responses match expected format
3. **Concurrent Request Preservation**: Test ThreadPoolExecutor handles multiple concurrent requests correctly
4. **Error Handling Preservation**: Verify error responses and exception handling work identically
5. **Service Lifecycle Preservation**: Test server start, graceful shutdown, and restart behavior

### Unit Tests

- Test Docker build completes successfully with updated grpcio version
- Test pip install succeeds without yanked package warnings
- Test grpcio package is importable and version is correct
- Test gRPC server starts and accepts connections
- Test basic request/response cycle works

### Property-Based Tests

- Generate random valid PostProcessRequest payloads and verify service handles them correctly
- Generate random port configurations and verify server binds correctly
- Test service behavior across many concurrent request scenarios
- Verify PII redaction, validation, and confidence scoring produce consistent results

### Integration Tests

- Test full Docker build and run workflow (build image, start container, send requests)
- Test inter-service communication with other services that may call post-processing-service
- Test service behavior in docker-compose environment with all dependencies
- Test build reproducibility across different environments and cache states
