# Security Architecture

## Authentication & Authorization Overview

CodeWarden uses a **zero-credential** architecture powered by Azure Managed Identity and Azure Key Vault for maximum security.

```
┌─────────────────────────────────────────────────────────────────┐
│                     Security Architecture                        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      Azure Function App                          │
│                    (System-assigned MI)                          │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              No Credentials in Code                     │    │
│  │              No Credentials in Config                   │    │
│  │              DefaultAzureCredential()                   │    │
│  └────────────────────────────────────────────────────────┘    │
└────────────────────┬─────────────────────────────────────────────┘
                     │
                     │ Authenticated via Managed Identity
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌──────────┐
   │   Key   │ │  Table  │ │  Azure   │
   │  Vault  │ │ Storage │ │  DevOps  │
   └─────────┘ └─────────┘ └──────────┘
        │                         │
        │ Stores:                 │ Uses:
        │ • OpenAI Key           │ • Azure AD
        │ • Webhook Secret       │   Tokens
        └────────────────────────┘
```

## Authentication Methods by Service

### ✅ Managed Identity (Credential-Free)

| Service | Method | Access Control |
|---------|--------|----------------|
| **Azure Key Vault** | System MI | Access Policy (Get/List secrets) |
| **Azure Table Storage** | System MI | RBAC (Storage Table Data Contributor) |
| **Azure DevOps API** | System MI | Azure AD + Project Permissions |

**Benefits:**
- ✅ No credentials to manage or rotate
- ✅ Automatic Azure AD token acquisition
- ✅ Scoped permissions via Azure RBAC
- ✅ Audit logs in Azure AD
- ✅ Works locally via Azure CLI

### ⚠️ Secret-Based (Stored in Key Vault)

| Service | Method | Why |
|---------|--------|-----|
| **OpenAI / Azure OpenAI** | API Key | External service |

**Security Measures:**
- 🔒 Stored only in Azure Key Vault
- 🔒 Retrieved via Managed Identity
- 🔒 Cached in memory (not persisted)
- 🔒 Never logged or exposed
- 🔒 Rotation via Key Vault only

### 🔐 Webhook Validation

| Component | Method | Protection |
|-----------|--------|------------|
| **Incoming Webhooks** | Shared Secret | HMAC validation, constant-time comparison |
| **Payload Size** | Size Limits | Max 1MB |
| **JSON Depth** | Depth Validation | Max 10 levels |

## Security Layers

### Layer 1: Network Security

```
Internet
   │
   ▼
Azure Front Door / App Gateway
   │ (Optional: IP restrictions, WAF)
   ▼
Function App
   │ (Required: HTTPS only)
   │ (Optional: VNet integration)
   ▼
Private Endpoints (Optional)
   │
   ▼
Azure Services (Key Vault, Storage)
```

### Layer 2: Identity & Access Management

```
┌─────────────────────────────────────────────────┐
│         Azure Active Directory (Entra ID)        │
│                                                  │
│  ┌────────────────────────────────────────┐    │
│  │   Function App Managed Identity        │    │
│  │   (System-assigned)                    │    │
│  │                                          │    │
│  │   Principal ID: xxxx-xxxx-xxxx          │    │
│  └────────────────────────────────────────┘    │
│                     │                            │
│                     │ Granted Roles:             │
│                     │                            │
│          ┌──────────┼──────────┐                │
│          ▼          ▼          ▼                │
│    Key Vault  Table Storage  (Others)          │
│    Secrets    Data                              │
│    User       Contributor                       │
└─────────────────────────────────────────────────┘
```

**RBAC Assignments:**

1. **Key Vault Access:**
   - Role: Key Vault Secrets User (RBAC) or Access Policy
   - Permissions: Get, List
   - Scope: Key Vault resource

2. **Table Storage Access:**
   - Role: Storage Table Data Contributor
   - Permissions: Read, Write, Delete table data
   - Scope: Storage Account resource

### Layer 3: Secret Management

```
┌──────────────────────────────────────────────────┐
│            Azure Key Vault                        │
│                                                   │
│  ┌──────────────────────────────────────────┐   │
│  │ Secrets (Encrypted at rest)              │   │
│  │                                            │   │
│  │ • AZURE-OPENAI-KEY or OPENAI-API-KEY     │   │
│  │   └─ Rotated: Monthly                     │   │
│  │                                            │   │
│  │ • WEBHOOK-SECRET                          │   │
│  │   └─ Random 32-byte string                │   │
│  └──────────────────────────────────────────┘   │
│                                                   │
│  Access Logs:                                    │
│  • Who accessed what secret                     │
│  • When (timestamp)                             │
│  • Success/Failure                              │
└──────────────────────────────────────────────────┘
```

### Layer 4: Application Security

**Input Validation:**
```python
✅ Webhook payload size: Max 1MB
✅ JSON depth: Max 10 levels
✅ File paths: No traversal (../)
✅ Webhook secret: Constant-time comparison
✅ Request origin: Validated against expected sources
```

**Output Sanitization:**
```python
✅ Error messages: No stack traces in responses
✅ Logging: Sensitive data filtered
✅ API responses: Minimal information disclosure
```

**Secure Defaults:**
```python
✅ All endpoints: Function-level auth (except webhook)
✅ HTTPS: Required (enforced by Azure)
✅ CORS: Restricted to Azure DevOps
✅ Content-Type: JSON only
```

## Threat Model & Mitigations

### Threat 1: Credential Theft

**Risk:** Attacker gains access to credentials and impersonates the application.

**Mitigations:**
- ✅ No credentials in code or environment variables
- ✅ Managed Identity cannot be extracted
- ✅ Secrets stored only in Key Vault
- ✅ Key Vault access requires Azure AD authentication
- ✅ Audit logs track all secret access

### Threat 2: Webhook Injection

**Risk:** Attacker sends malicious webhook to trigger unauthorized reviews.

**Mitigations:**
- ✅ Webhook secret validation (HMAC)
- ✅ Constant-time comparison prevents timing attacks
- ✅ Payload size limits prevent DoS
- ✅ JSON depth validation prevents parser exploits
- ✅ IP restrictions (optional, can be added)

### Threat 3: Path Traversal

**Risk:** Attacker manipulates file paths to access unauthorized files.

**Mitigations:**
- ✅ Path sanitization (`_is_safe_path()`)
- ✅ Reject absolute paths
- ✅ Reject traversal patterns (`../`)
- ✅ Null byte checking
- ✅ Suspicious path filtering

### Threat 4: Secrets in Logs

**Risk:** Sensitive data leaked through application logs.

**Mitigations:**
- ✅ Structured logging with field filtering
- ✅ No raw request/response bodies logged
- ✅ Error IDs instead of stack traces
- ✅ Sanitized log output
- ✅ Log review procedures

### Threat 5: API Abuse

**Risk:** Attacker triggers excessive AI API calls, incurring costs.

**Mitigations:**
- ✅ Webhook authentication required
- ✅ Function-level auth on all endpoints
- ✅ Rate limiting (Azure built-in)
- ✅ Cost monitoring and alerts
- ✅ Per-request timeouts

### Threat 6: Code Injection via AI

**Risk:** Malicious code in PR comments injected into AI prompts.

**Mitigations:**
- ✅ AI responses validated against schema
- ✅ No code execution from AI output
- ✅ JSON-only response format
- ✅ Markdown rendering in DevOps (not HTML)

## Security Best Practices

### Development

1. **Never commit secrets:**
   - Use `.gitignore` for `.env` files
   - Scan commits with git-secrets or similar

2. **Local development:**
   - Always use `az login` for local auth
   - Never use production secrets locally

3. **Code reviews:**
   - Review all changes to authentication logic
   - Validate input handling changes
   - Check for new secret storage

### Deployment

1. **Managed Identity:**
   ```bash
   # Enable system-assigned MI
   az functionapp identity assign \
     --name <app-name> \
     --resource-group <rg-name>
   ```

2. **Least Privilege:**
   - Grant only required permissions
   - Use specific scopes (not subscription-wide)
   - Review role assignments regularly

3. **Secret Rotation:**
   - OpenAI API Key: Every 30 days
   - Webhook Secret: Every 6 months
   - Update in Key Vault only (no code changes)
   - Managed Identity tokens: Automatic rotation by Azure AD

### Monitoring

1. **Azure Monitor Alerts:**
   - Failed authentication attempts
   - Key Vault access failures
   - Unusual API call patterns
   - High cost anomalies

2. **Datadog Integration:**
   - Application metrics
   - Error rates
   - Performance monitoring
   - Custom business metrics

3. **Audit Logs:**
   - Azure AD sign-in logs
   - Key Vault audit logs
   - Storage account logs
   - Function execution logs

## Compliance Considerations

### Data Residency

- All data stored in specified Azure region
- Table Storage: Same region as Function App
- Key Vault: Same region as Function App
- Compliance with regional requirements (GDPR, etc.)

### Data Classification

| Data Type | Classification | Storage | Encryption |
|-----------|---------------|---------|------------|
| PR Code Diffs | Confidential | Transient (memory only) | TLS in transit |
| Review Results | Internal | Table Storage | At rest + in transit |
| API Keys | Restricted | Key Vault only | At rest + in transit |
| Webhook Secrets | Restricted | Key Vault only | At rest + in transit |

### Access Logging

All access to sensitive resources is logged:
- Key Vault: Every secret retrieval
- Table Storage: All data operations
- Function App: All invocations
- Retention: 90 days minimum

## Security Checklist

### Pre-Deployment

- [ ] System-assigned Managed Identity enabled
- [ ] Key Vault access policies/RBAC configured
- [ ] Table Storage RBAC roles assigned
- [ ] Secrets stored in Key Vault
- [ ] No credentials in app settings
- [ ] HTTPS enforced
- [ ] Function-level auth on endpoints

### Post-Deployment

- [ ] Verify Managed Identity authentication
- [ ] Test secret retrieval from Key Vault
- [ ] Validate webhook authentication
- [ ] Check audit logs are flowing
- [ ] Set up monitoring alerts
- [ ] Document secret rotation schedule
- [ ] Review security logs weekly

### Ongoing

- [ ] Rotate API keys regularly (OpenAI: 30 days)
- [ ] Review RBAC assignments monthly
- [ ] Update dependencies quarterly
- [ ] Security audit annually
- [ ] Penetration testing (as needed)

## Incident Response

### Compromised API Key

1. **Immediate:**
   - Revoke key in external service (OpenAI/Azure OpenAI)
   - Generate new API key
   - Update in Key Vault
   - Restart Function App

2. **Investigation:**
   - Review audit logs for unauthorized access
   - Check for unusual API usage patterns
   - Identify source of compromise

3. **Prevention:**
   - Review Key Vault access policies
   - Enhance monitoring and alerts
   - Update security procedures

### Suspicious Webhook Activity

1. **Immediate:**
   - Review webhook request logs
   - Validate source IPs
   - Check for payload anomalies

2. **Response:**
   - Block suspicious IPs (if identified)
   - Rotate webhook secret
   - Update Azure DevOps webhook config

3. **Prevention:**
   - Add rate limiting
   - Implement IP allowlisting
   - Enhanced monitoring

## Resources

- [Azure Managed Identity Best Practices](https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/managed-identity-best-practice-recommendations)
- [Key Vault Security](https://learn.microsoft.com/en-us/azure/key-vault/general/security-features)
- [Azure Functions Security](https://learn.microsoft.com/en-us/azure/azure-functions/security-concepts)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
