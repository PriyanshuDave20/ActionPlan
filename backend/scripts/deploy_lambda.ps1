# Deploys the AI Workplace Operations Agent backend to AWS Lambda
# as a container image via AWS CodeBuild. No local Docker required.
#
# Requires:
#   - AWS CLI v2 authenticated (aws configure / SSO / instance role)
#   - Git/source code accessible to CodeBuild (e.g., GitHub repository)
#   - CodeBuild project and ECR repository created in advance
#     (see README "AWS Lambda deployment"); this script can also
#     create the ECR repository via -CreateEcrRepository.
#
# Usage (PowerShell):
#   .\scripts\deploy_lambda.ps1 -FunctionName workplace-operations-agent `
#       -LambdaRoleArn arn:aws:iam::<account-id>:role/workplace-operations-lambda-role `
#       -CreateEcrRepository
#
# All secrets remain in the Lambda function's environment variables.
# This script never writes secrets to ECR, Docker, or the image.
# Docker Desktop is NOT required.

param(
    [string]$Region = "us-east-2",
    [string]$EcrRepositoryName = "workplace-operations-agent",
    [string]$ImageTag = "latest",
    [string]$FunctionName = "workplace-operations-agent",
    [string]$LambdaRoleArn = "",
    [string]$CodeBuildProjectName = "workplace-operations-agent-build",
    [string]$GitHubSourceLocation = "",
    [string]$GitHubConnectionArn = "",
    [int]$MemoryMb = 2048,
    [int]$TimeoutSeconds = 60,
    [int]$EphemeralStorageMb = 1024,
    [switch]$CreateEcrRepository = $false,
    [switch]$WaitForLambda = $true
)

$ErrorActionPreference = "Stop"

# ── Validate AWS CLI ──────────────────────────────────────────────
Write-Host "==> Validating AWS CLI"
$awsVersion = aws --version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "AWS CLI is not installed or not accessible. Install AWS CLI v2."
}
Write-Host "    AWS CLI: $awsVersion"

# ── Validate AWS credentials ──────────────────────────────────────
Write-Host "==> Validating AWS credentials"
$identity = aws sts get-caller-identity --region $Region --query "Account" --output text 2>&1
if (-not $identity -or $LASTEXITCODE -ne 0) {
    throw "Could not resolve AWS account. Is the AWS CLI authenticated? Run: aws configure"
}
$AccountId = $identity.Trim()
Write-Host "    Account: $AccountId  Region: $Region"

$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$ImageUri = "$Registry/$EcrRepositoryName`:$ImageTag"
Write-Host "    Target image: $ImageUri"

# ── Ensure ECR repository exists ──────────────────────────────────
if ($CreateEcrRepository) {
    Write-Host "==> Ensuring ECR repository exists"
    $exists = aws ecr describe-repositories --region $Region `
        --repository-names $EcrRepositoryName --query "repositories[0].repositoryUri" `
        --output text 2>$null
    if (-not $exists) {
        aws ecr create-repository --region $Region --repository-name $EcrRepositoryName `
            --image-tag-mutability MUTABLE 2>$null | Out-Null
        Write-Host "    Created repository $EcrRepositoryName"
    } else {
        Write-Host "    Repository already exists"
    }
}

# ── Start CodeBuild build ─────────────────────────────────────────
Write-Host "==> Starting CodeBuild project: $CodeBuildProjectName"
Write-Host "    Source version: $ImageTag"

$startBuildArgs = @(
    "--region", $Region,
    "--project-name", $CodeBuildProjectName,
    "--source-version", $ImageTag,
    "--query", "build.id",
    "--output", "text"
)
if ($GitHubSourceLocation) {
    # Source override is handled via project configuration; GitHubSourceLocation
    # is used at deploy time via parameter overrides
}

$buildOutput = aws codebuild start-build @startBuildArgs 2>&1

if ($LASTEXITCODE -ne 0 -or -not $buildOutput) {
    throw "Failed to start CodeBuild build. Error: $buildOutput"
}
$BuildId = $buildOutput.Trim()
Write-Host "    Build ID: $BuildId"

# ── Wait for CodeBuild to complete ────────────────────────────────
Write-Host "==> Waiting for CodeBuild build to complete (this may take several minutes)..."
$buildFailed = $false
$buildStatus = ""

do {
    Start-Sleep -Seconds 15
    $buildStatus = aws codebuild batch-get-builds `
        --region $Region `
        --ids $BuildId `
        --query "builds[0].buildStatus" `
        --output text 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    Warning: could not query build status"
        continue
    }
    Write-Host "    Current status: $buildStatus"
} while ($buildStatus -eq "IN_PROGRESS" -or $buildStatus -eq "QUEUED")

if ($buildStatus -ne "SUCCEEDED") {
    $buildFailed = $true
    Write-Host ""
    Write-Host "ERROR: CodeBuild build FAILED with status: $buildStatus"
    Write-Host "Build ID: $BuildId"
    # Fetch detailed logs
    $logs = aws codebuild batch-get-builds --region $Region --ids $BuildId --query "builds[0].logs" --output json 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Build logs: $logs"
    }
    throw "CodeBuild build failed. Check CloudWatch logs at /aws/codebuild/$CodeBuildProjectName"
}

Write-Host "    CodeBuild build succeeded"

# ── Retrieve the resulting ECR image URI ──────────────────────────
Write-Host "==> Verifying ECR image"
$ecrImageExists = aws ecr describe-images --region $Region `
    --repository-name $EcrRepositoryName `
    --image-ids imageTag=$ImageTag `
    --query "images[0].imageUri" --output text 2>$null

if ($LASTEXITCODE -ne 0 -or -not $ecrImageExists) {
    throw "Expected image $ImageUri not found in ECR after CodeBuild succeeded."
}
Write-Host "    Verified image in ECR: $ecrImageExists"

# ── Update Lambda function ────────────────────────────────────────
Write-Host "==> Updating Lambda function $FunctionName to image: $ImageUri"

$existing = aws lambda get-function --region $Region --function-name $FunctionName 2>$null
if ($LASTEXITCODE -ne 0 -and $LambdaRoleArn) {
    Write-Host "    Creating Lambda function"
    aws lambda create-function `
        --region $Region `
        --function-name $FunctionName `
        --package-type Image `
        --code "ImageUri=$ImageUri" `
        --role $LambdaRoleArn `
        --memory-size $MemoryMb `
        --timeout $TimeoutSeconds `
        --architectures x86_64 `
        --ephemeral-storage "Size=$EphemeralStorageMb" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create Lambda function"
    }
} elseif ($existing) {
    Write-Host "    Function exists; updating image code"
    aws lambda update-function-code `
        --region $Region `
        --function-name $FunctionName `
        --image-uri $ImageUri | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update Lambda function code"
    }
} else {
    throw "Lambda function $FunctionName does not exist and -LambdaRoleArn was not provided."
}

# ── Wait for Lambda to be ready ───────────────────────────────────
if ($WaitForLambda) {
    Write-Host "==> Waiting for Lambda function to be Active"
    try {
        aws lambda wait function-updated --region $Region --function-name $FunctionName 2>$null
    } catch {
        Write-Host "    Warning: Lambda wait command returned non-zero; checking function status..."
    }
    $funcStatus = aws lambda get-function --region $Region --function-name $FunctionName `
        --query "Configuration.State" --output text 2>&1
    Write-Host "    Lambda state: $funcStatus"
}

# ── Get API Gateway URL (from CloudFormation outputs if available) ──
Write-Host ""
Write-Host "=========================================="
Write-Host "Deployment complete!"
Write-Host "=========================================="
Write-Host "Deployed image: $ImageUri"
Write-Host "Lambda function: $FunctionName"
Write-Host "CodeBuild project: $CodeBuildProjectName"
Write-Host "CodeBuild build ID: $BuildId"
Write-Host "ECR repository: $EcrRepositoryName"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Set Lambda environment variables (LLM_API_KEY, ZILLIZ_TOKEN, etc.)"
Write-Host "  2. Create/attach the API Gateway HTTP API"
Write-Host "  3. Run smoke test: \$env:BACKEND_API_URL='https://<api-id>.execute-api.us-east-2.amazonaws.com'; py -3 scripts\cloud_smoke_test.py"
Write-Host ""
Write-Host "Invoke directly to smoke test:"
Write-Host "  aws lambda invoke --function-name $FunctionName --payload '{}' output.txt && type output.txt"
