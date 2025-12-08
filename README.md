<p align="center">
  <img src="https://img.shields.io/badge/CodeWarden-AI%20PR%20Reviewer-blueviolet?style=for-the-badge&logo=azure-devops" alt="CodeWarden">
</p>

<h1 align="center">CodeWarden</h1>

<p align="center">
  <strong>AI-Powered Code Review for Azure DevOps</strong><br>
  Catch bugs, security issues, and code smells before they hit production.
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+"></a>
  <a href="https://github.com/psf/black"><img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="http://mypy-lang.org/"><img src="http://www.mypy-lang.org/static/mypy_badge.svg" alt="Type checked: mypy"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-features">Features</a> •
  <a href="docs/DEPLOYMENT-GUIDE.md">Deploy</a> •
  <a href="docs/ARCHITECTURE.md">Architecture</a> •
  <a href="CONTRIBUTING.md">Contribute</a>
</p>

---

## Why CodeWarden?

<table>
<tr>
<td width="50%">

### The Problem

- Manual code reviews are slow and inconsistent
- Security issues slip through to production
- Junior developers wait hours for feedback
- Existing tools cost $400-800/month

</td>
<td width="50%">

### The Solution

- **Instant AI reviews** on every PR
- **90+ languages** and frameworks supported
- **Self-hosted** in your Azure subscription
- **$10-160/month** total cost

</td>
</tr>
</table>

---

## Key Metrics

<p align="center">

| 🚀 **Performance** | 💰 **Cost Savings** | 🔒 **Security** |
|:------------------:|:-------------------:|:---------------:|
| 5-30 second reviews | 78% cheaper than alternatives | Zero credentials in code |
| 50-88% token savings | ~$10/mo development | Managed Identity auth |
| 90+ file types | ~$160/mo production | Azure Key Vault secrets |

</p>

---

## Features

<table>
<tr>
<td width="33%" valign="top">

### 🎯 Smart Analysis
- Diff-only review (not full files)
- Technology-specific prompts
- Context-aware suggestions
- Severity classification

</td>
<td width="33%" valign="top">

### 🧠 Learns Over Time
- Tracks accepted/rejected suggestions
- Adapts to team preferences
- Detects recurring patterns
- Improves accuracy continuously

</td>
<td width="33%" valign="top">

### 🏢 Enterprise Ready
- Azure Managed Identity
- Key Vault integration
- Structured logging (Datadog)
- Full audit trail

</td>
</tr>
</table>

### Supported Technologies

```
Languages:     Python, TypeScript, JavaScript, Java, C#, Go, Rust, Ruby, PHP, Swift, Kotlin...
Infrastructure: Terraform, Ansible, CloudFormation, Bicep, Pulumi, ARM Templates...
Containers:    Docker, Kubernetes, Helm, Docker Compose...
Config:        YAML, JSON, TOML, XML, .env, nginx, Apache...
And 70+ more file types with specialized review prompts.
```

---

## Architecture

```
┌──────────────┐      ┌─────────────────────────────────────┐      ┌──────────────┐
│ Azure DevOps │─────▶│     Azure Functions (Python)       │─────▶│   OpenAI /   │
│   Webhook    │      │                                     │      │  Azure AI    │
└──────────────┘      │  ┌─────────────────────────────┐    │      └──────────────┘
                      │  │    CodeWarden Reviewer      │    │
                      │  │                             │    │      ┌──────────────┐
                      │  │  • Parse diffs              │    │─────▶│  Key Vault   │
                      │  │  • AI review                │    │      │  (Secrets)   │
                      │  │  • Post comments            │    │      └──────────────┘
                      │  │  • Track feedback           │    │
                      │  └─────────────────────────────┘    │      ┌──────────────┐
                      │                                     │─────▶│Table Storage │
                      └─────────────────────────────────────┘      │ (Feedback)   │
                                                                   └──────────────┘
```

**[View detailed architecture →](docs/ARCHITECTURE.md)**

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/Swaeltjie/codewarden.git
cd codewarden
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
az login
cp .env.example .env
# Edit .env with your Azure DevOps org and Key Vault URL
```

### 3. Run Locally

```bash
func start
# Webhook endpoint: http://localhost:7071/api/pr-webhook
```

### 4. Deploy to Azure

```bash
func azure functionapp publish <your-function-app> --python
```

**[Full deployment guide →](docs/DEPLOYMENT-GUIDE.md)**

---

## Cost Comparison

| Solution | Monthly Cost (20 users) | Self-Hosted | Azure DevOps |
|----------|-------------------------|:-----------:|:------------:|
| **CodeWarden** | **$10-160** | ✅ | ✅ |
| CodeRabbit | $380-780 | ❌ | ✅ |
| GitHub Copilot | $200-780 | ❌ | ❌ |
| Codacy | $300-600 | ❌ | ⚠️ |

**Save 78% or more** compared to commercial alternatives.

---

## Documentation

| Document | Description |
|----------|-------------|
| **[Architecture](docs/ARCHITECTURE.md)** | System design, security, data models |
| **[Deployment Guide](docs/DEPLOYMENT-GUIDE.md)** | Step-by-step Azure setup |
| **[Managed Identity](docs/MANAGED-IDENTITY-SETUP.md)** | Credential-free authentication |
| **[Datadog Integration](docs/DATADOG-INTEGRATION.md)** | Monitoring & observability |

---

## Development

```bash
# Run tests
pytest --cov=src

# Code quality
pre-commit run --all-files

# Type checking
mypy src/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

---

## Security

- ✅ **Zero credentials in code** - Managed Identity for all Azure services
- ✅ **Secrets in Key Vault** - API keys never in config files
- ✅ **Webhook validation** - HMAC signature verification
- ✅ **HTTPS only** - All traffic encrypted
- ✅ **Audit logging** - Full trail in Azure AD & Datadog

---

<p align="center">
  <strong>Ready to improve your code reviews?</strong><br><br>
  <a href="docs/DEPLOYMENT-GUIDE.md"><img src="https://img.shields.io/badge/Deploy%20Now-blue?style=for-the-badge" alt="Deploy Now"></a>
  &nbsp;&nbsp;
  <a href="docs/ARCHITECTURE.md"><img src="https://img.shields.io/badge/Learn%20More-gray?style=for-the-badge" alt="Learn More"></a>
</p>

---

<p align="center">
  <a href="LICENSE">MIT License</a> •
  <a href="CONTRIBUTING.md">Contributing</a> •
  <a href="https://github.com/Swaeltjie/codewarden/issues">Issues</a>
</p>
