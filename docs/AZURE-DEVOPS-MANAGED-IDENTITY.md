# Azure DevOps Managed Identity Setup

## Overview

CodeWarden uses **credential-free authentication** to Azure DevOps via Managed Identity - providing superior security with zero credentials to manage.

## Benefits of Managed Identity for Azure DevOps

| Feature | Managed Identity |
|---------|------------------|
| **Credentials** | ✅ Automatic, no credentials |
| **Expiration** | ✅ Never expires |
| **Rotation** | ✅ Automatic (Azure AD handles) |
| **Auditing** | ✅ Full Azure AD audit logs |
| **Permissions** | ✅ Granular project-level access |
| **Security** | ✅ Cannot be extracted or leaked |

## Prerequisites

1. **Azure Function App** with System-assigned Managed Identity enabled
2. **Azure DevOps Organization** (cloud-hosted)
3. **Admin access** to Azure DevOps organization

**Note:** This feature requires:
- Azure DevOps Services (cloud) - **NOT** Azure DevOps Server (on-prem)
- Azure Function App or other Azure resource with Managed Identity

## Setup Steps

### Step 1: Enable Managed Identity on Function App

```bash
# Enable system-assigned managed identity
az functionapp identity assign \
  --name <function-app-name> \
  --resource-group <resource-group>

# Get the Principal ID (Object ID)
PRINCIPAL_ID=$(az functionapp identity show \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --query principalId -o tsv)

echo "Managed Identity Principal ID: $PRINCIPAL_ID"

# Get the display name for Azure DevOps
APP_NAME=$(az functionapp show \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --query name -o tsv)

echo "Add this user to Azure DevOps: $APP_NAME"
```

### Step 2: Add Managed Identity to Azure DevOps

**Method A: Via Azure Portal (Recommended)**

1. Go to your **Azure Function App** in Azure Portal
2. Under **Identity** → **System assigned**, copy the **Object (principal) ID**
3. Go to **Azure DevOps** → Your Organization → **Organization Settings**
4. Click **Users**
5. Click **Add users**
6. In the search box, paste the **Object ID** you copied
7. Select the identity (it will show as the Function App name)
8. Assign access level: **Basic** (minimum required)
9. Click **Add**

**Method B: Via Azure DevOps CLI**

```bash
# Install Azure DevOps CLI extension
az extension add --name azure-devops

# Login to Azure DevOps
az devops login

# Set your organization
az devops configure --defaults organization=https://dev.azure.com/<your-org>

# Add the managed identity as a user
# Note: Use the Principal ID from Step 1
az devops user add \
  --email-id "$PRINCIPAL_ID@azuredevops.microsoft.com" \
  --license-type basic \
  --send-email-invite false

# Verify the user was added
az devops user list --output table
```

### Step 3: Grant Project Permissions

The Managed Identity needs specific permissions:

**Minimum Required Permissions:**

| Resource | Permission | Why |
|----------|------------|-----|
| **Code** | Read | To fetch PR details and diffs |
| **Pull Request Threads** | Read & Write | To post review comments |
| **Project** | View project-level information | To access project metadata |

**Grant permissions:**

1. Go to **Azure DevOps** → Your Project → **Project Settings**
2. Under **Permissions**, find your Managed Identity user
3. Grant these permissions:
   - Code: **Reader**
   - Pull Request Threads: **Contributor**
   - Project: **Reader**

**Or via security groups:**

1. Add the Managed Identity to the **Contributors** group for the project
2. This provides appropriate read/write access for PR reviews

### Step 4: Verify Configuration

No additional configuration needed! The code uses Managed Identity automatically.

**Verification:**

```bash
# Check authentication method in logs
az functionapp log tail \
  --name <function-app-name> \
  --resource-group <resource-group>

# Look for: "devops_auth_success" with method="managed_identity"
```

### Step 5: Test the Integration

```bash
# Restart the function app to ensure fresh authentication
az functionapp restart \
  --name <function-app-name> \
  --resource-group <resource-group>

# Monitor logs
az functionapp log tail \
  --name <function-app-name> \
  --resource-group <resource-group>

# Create a test PR in Azure DevOps
# The webhook should trigger and you should see:
# - "devops_auth_success" with method="managed_identity"
# - "devops_session_created" with auth_method="managed_identity"
# - PR review comments posted successfully
```

## Authentication Flow

```
┌──────────────────────────────────────────────────┐
│            Azure Function App                     │
│         (System-assigned MI enabled)              │
└────────────────────┬─────────────────────────────┘
                     │
                     │ 1. Request Azure AD token
                     ▼
┌──────────────────────────────────────────────────┐
│           Azure Active Directory                 │
│                                                  │
│  Resource: https://app.vssps.visualstudio.com   │
│  Scope: .default                                 │
└────────────────────┬─────────────────────────────┘
                     │
                     │ 2. Returns JWT access token
                     ▼
┌──────────────────────────────────────────────────┐
│          Azure Function App (CodeWarden)         │
│                                                  │
│  Authorization: Bearer <jwt-token>               │
└────────────────────┬─────────────────────────────┘
                     │
                     │ 3. API calls with Bearer token
                     ▼
┌──────────────────────────────────────────────────┐
│          Azure DevOps REST API                   │
│                                                  │
│  • Validates Azure AD token                     │
│  • Checks user permissions                      │
│  • Returns PR data / Posts comments             │
└──────────────────────────────────────────────────┘
```

## Authentication Method

CodeWarden uses **Managed Identity only** for Azure DevOps authentication:

```python
# Authentication flow:
1. Get Azure AD token for Managed Identity
2. Use Bearer token with Azure DevOps API
3. If authentication fails, error is raised with setup instructions
```

**Requirements:**
- Managed Identity enabled on Function App
- MI added to Azure DevOps organization
- MI has proper project permissions
- For local dev: Azure CLI login required

## Local Development

### Azure CLI Authentication

```bash
# Login to Azure
az login

# The DefaultAzureCredential will use your Azure CLI identity
# You need to be added to the Azure DevOps organization as well
```

**Requirements for local development:**
- Azure CLI installed and logged in (`az login`)
- Your Azure account added to Azure DevOps organization
- Your account has appropriate project permissions

## Troubleshooting

### Error: "Authentication failed"

**Symptoms:**
```
devops_managed_identity_failed: Failed to acquire token
devops_auth_failed: Failed to authenticate
```

**Solutions:**

1. **Verify MI is added to Azure DevOps:**
   ```bash
   # Check if your MI is in the organization
   az devops user list --output table

   # Look for your Function App name or Principal ID
   ```

2. **Check MI permissions:**
   - Ensure "Basic" license assigned
   - Verify project permissions (Code: Read, PR Threads: Read/Write)

3. **Verify MI is enabled:**
   ```bash
   az functionapp identity show \
     --name <function-app-name> \
     --resource-group <resource-group>

   # Should return principalId and tenantId
   ```

### Error: "User not found" when adding to Azure DevOps

**Symptoms:**
Can't find the Managed Identity when searching in Azure DevOps Users.

**Solution:**
- **Use the Object ID**, not the Function App name
- The Object ID is a GUID like: `12345678-1234-1234-1234-123456789abc`
- You can find it in Azure Portal → Function App → Identity → System assigned → Object (principal) ID

### Error: "Forbidden" when accessing PR

**Symptoms:**
```
HTTP 403 Forbidden when fetching PR details
```

**Solution:**
The Managed Identity doesn't have proper project permissions:

1. Go to Azure DevOps → Project → Project Settings → Permissions
2. Find your Managed Identity user
3. Ensure it has at least:
   - View project-level information
   - Read code
   - Contribute to pull request threads

### MI works in Azure but not locally

**Symptoms:**
Managed Identity works in Azure Function App but fails locally.

**Solution:**
```bash
# Ensure you're logged into Azure CLI
az login

# Verify your account
az account show

# Add YOUR user account to Azure DevOps organization
# (Same steps as adding MI, but use your email)
```

## Verification Checklist

After setup, verify these items:

- [ ] System-assigned Managed Identity enabled on Function App
- [ ] Managed Identity added to Azure DevOps organization
- [ ] Basic license assigned to Managed Identity
- [ ] Project permissions granted (Code: Read, PR Threads: Contribute)
- [ ] Function App restarted
- [ ] Logs show `devops_auth_success` with `method="managed_identity"`
- [ ] Test webhook successfully posts review comment
- [ ] No "authentication failed" errors in logs

## Deployment Checklist

Complete these steps to enable Managed Identity authentication:

1. ✅ **Enable Managed Identity** on Function App
2. ✅ **Add MI to Azure DevOps** organization (with Basic license)
3. ✅ **Grant project permissions** (Code: Read, PR Threads: Contribute)
4. ✅ **Deploy Function App**
5. ✅ **Verify** logs show "managed_identity" authentication
6. ✅ **Test** with a sample PR to confirm it works

## Security Benefits

### Managed Identity Advantages
```
✅ Never expires (automatic rotation by Azure AD)
✅ Cannot be extracted or leaked
✅ Granular project-level permissions
✅ Full Azure AD audit logs
✅ Centralized permission management via Azure RBAC
✅ Integrates with Conditional Access policies
```

## Best Practices

1. **Least Privilege**
   - Grant only required project permissions
   - Use project-specific permissions, not org-wide

3. **Monitor Authentication**
   - Set up alerts for authentication failures
   - Review audit logs regularly
   - Track auth method usage

4. **Regular Reviews**
   - Quarterly review of MI permissions
   - Remove unused MI users
   - Audit project access

## Resources

- [Microsoft Docs: Service Principal & Managed Identity](https://learn.microsoft.com/en-us/azure/devops/integrate/get-started/authentication/service-principal-managed-identity)
- [Azure DevOps REST API Reference v7.1](https://learn.microsoft.com/en-us/rest/api/azure/devops/?view=azure-devops-rest-7.1)
- [Azure Identity Library](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme)
- [Blog: Authenticate as Managed Identity](https://blog.xmi.fr/posts/azure-devops-authenticate-as-managed-identity/)

## FAQ

**Q: Does this work with Azure DevOps Server (on-premises)?**
A: No, Managed Identity requires Azure DevOps Services (cloud). On-premises Azure DevOps Server doesn't support Azure AD authentication.

**Q: Can I use User-assigned Managed Identity?**
A: Yes, but you'll need to modify the code to specify the client ID. System-assigned is simpler.

**Q: What happens if MI authentication fails?**
A: The function will return an error with detailed setup instructions. Ensure MI is properly configured in Azure DevOps.

**Q: How do I verify Managed Identity is working?**
A: Check application logs for `devops_auth_success` with `method="managed_identity"`. You should see Bearer token authentication in the logs.

**Q: Does this cost extra?**
A: No! Managed Identity is free. You only pay for Azure AD token acquisitions (fractions of a penny per request).

**Q: How often does the token refresh?**
A: Azure AD tokens typically expire after 1 hour. The code automatically refreshes tokens as needed.
