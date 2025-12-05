# CodeWarden

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)

AI-powered Pull Request reviewer for Azure DevOps supporting Terraform, Ansible, Azure Pipelines, and JSON configurations.

## ✨ Features

- **Multi-Technology Support:** Terraform, Ansible, Azure Pipelines, JSON
- **Diff-Only Analysis:** 50-85% token savings vs. full-file reviews
- **Feedback Learning:** Adapts to team preferences over time
- **Enterprise Security:** Azure Key Vault, Managed Identity, structured logging
- **Type-Safe:** Pydantic models, mypy checking, comprehensive testing

## 🏗️ Architecture Overview

### High-Level Architecture

```
┌─────────────────┐
│  Azure DevOps   │
│   (Webhook)     │
└────────┬────────┘
         │ PR Event
         ▼
┌────────────────────────────────────────────────────────┐
│              Azure Functions (Python 3.12)             │
│                                                        │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │ HTTP Trigger │    │Timer Trigger │                  │
│  │ pr_webhook   │    │  feedback    │                  │
│  └──────┬───────┘    └──────┬───────┘                  │
│         │                    │                         │
│         ▼                    ▼                         │
│  ┌─────────────────────────────────────┐               │
│  │      PR Review Orchestrator         │               │
│  │  • Fetch changed files              │               │
│  │  • Parse diffs (diff-only)          │               │
│  │  • Determine strategy (3-tier)      │               │
│  │  • Apply learning context           │               │
│  │  • Execute AI review                │               │
│  │  • Post results to DevOps           │               │
│  │  • Log to Datadog (via agent)       │               │
│  └─────────────────────────────────────┘               │
└──────────┬──────────────────────────────┬──────────────┘
           │                              │
    ┌──────▼───────┐              ┌──────▼───────┐
    │  Azure Key   │              │   OpenAI     │
    │    Vault     │              │     API      │
    │  (Secrets)   │              │ (GPT-4, etc) │
    └──────────────┘              └──────────────┘
           │
    ┌──────▼────────────────────────────────┐
    │    Storage Layer                      │
    │                                       │
    │  Azure Table Storage - $0.10/mo       │
    │    - Feedback tracking                │
    │    - Review history                   │
    └───────────────────────────────────────┘

    ┌──────────────────────────────────────┐
    │    Monitoring (Your Choice)          │
    │                                      │
    │  Datadog (Recommended)               │
    │    - Logs via Datadog Agent          │
    │    - Metrics & APM                   │
    │    - Alerts & dashboards             │
    │    - Uses existing infrastructure    │
    └──────────────────────────────────────┘
```

### Review Workflow

```
1. PR Created/Updated → Webhook → Azure Function
2. Fetch PR details & parse diffs (diff-only analysis)
3. Determine review strategy (single-pass, chunked, or hierarchical)
4. Apply learning context from past feedback
5. AI review with technology-specific prompts
6. Post results to Azure DevOps (summary + inline comments)
7. Track feedback for continuous improvement
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Runtime** | Azure Functions (Python 3.12) | Serverless compute |
| **API Gateway** | Azure Functions HTTP Trigger | Webhook endpoint |
| **AI/LLM** | Azure AI Foundry GPT-5 (recommended) or OpenAI | Code review analysis |
| **Storage** | Azure Table Storage | Feedback & history |
| **Secrets** | Azure Key Vault | Secure credential storage |
| **Monitoring** | Datadog (your existing infrastructure) | Logging, metrics & APM |
| **DevOps** | Azure DevOps API | PR integration |

### Data Storage

**Azure Table Storage** stores feedback tracking and review history:
- Cost-effective: $0.10/month vs Cosmos DB $25/month
- Fast key-value access (sub-100ms)
- Tracks feedback (accepted/rejected suggestions) and review metrics

For global distribution or complex queries, consider Cosmos DB.

📖 **[See detailed architecture documentation](docs/ARCHITECTURE.md)** for complete system design and data models.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Azure subscription
- Azure DevOps organization
- OpenAI API key (or Azure AI Foundry endpoint)
- Datadog account (optional, for monitoring)

### Installation

```bash
# Clone repository
git clone <your-repo>
cd ai-pr-reviewer

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Configure environment
cp .env.example .env
# Edit .env with your values

# Run locally
func start
```

### Deploy to Azure

```bash
# See DEPLOYMENT-GUIDE.md for complete instructions
func azure functionapp publish <your-function-app> --python
```

## 📁 Project Structure

```
ai-pr-reviewer/
├── function_app.py              # Azure Functions entry point
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Development dependencies
├── host.json                    # Function runtime configuration
│
├── src/
│   ├── handlers/                # HTTP/Timer trigger handlers
│   │   ├── pr_webhook.py       # Main PR orchestrator
│   │   └── feedback_collector.py
│   │
│   ├── services/                # Business logic
│   │   ├── azure_devops.py     # DevOps API client
│   │   ├── ai_client.py        # OpenAI/Anthropic client
│   │   ├── diff_parser.py      # Git diff parsing
│   │   ├── feedback_tracker.py # Learning system
│   │   └── pattern_detector.py # Historical analysis
│   │
│   ├── models/                  # Pydantic data models
│   ├── prompts/                 # AI prompts per technology
│   └── utils/                   # Configuration, logging, metrics
│
└── tests/                       # Comprehensive test suite
    ├── unit/
    ├── integration/
    └── fixtures/
```

## 🎯 Why Python?

Python provides excellent AI/LLM library support and rapid development. The ~1s cold start overhead is negligible compared to 20s average review times.

## 📊 Performance

**Token Savings (Diff-Only):** 50-88% reduction vs. full-file analysis
**Review Times:** 5-8s (small), 12-18s (medium), 25-40s (large PRs)

## 🛠️ Development

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Specific test
pytest tests/unit/test_diff_parser.py -v
```

### Code Quality

```bash
# Format code
black src/

# Lint
ruff check src/ --fix

# Type checking
mypy src/

# Security scan
bandit -r src/

# All checks
pre-commit run --all-files
```

## 📖 Documentation

### Core Documentation
- **[Architecture Overview](docs/ARCHITECTURE.md)** - System design, data models, and storage decisions
- **[Deployment Guide](docs/DEPLOYMENT-GUIDE.md)** - Complete Azure deployment walkthrough
- **[Security Architecture](docs/ARCHITECTURE-SECURITY.md)** - Zero-credential architecture and threat model

### Setup Guides
- **[Managed Identity Setup](docs/MANAGED-IDENTITY-SETUP.md)** - Credential-free authentication
- **[Azure DevOps MI Guide](docs/AZURE-DEVOPS-MANAGED-IDENTITY.md)** - DevOps-specific MI configuration
- **[Datadog Integration](docs/DATADOG-INTEGRATION.md)** - Monitoring and observability

### Reference
- **[Azure Resources](docs/AZURE-RESOURCES.md)** - Complete resource inventory and costs
- **[Version Control](docs/VERSION-CONTROL.md)** - Changelog and version history

## 🔒 Security

- ✅ Secrets stored in Azure Key Vault
- ✅ Managed Identity (no credentials in code)
- ✅ Function-level authorization keys
- ✅ Webhook secret validation
- ✅ HTTPS only
- ✅ Security scanning with Bandit

## 💰 Cost

**Development:** ~$10/month (Consumption plan + infrastructure)
**Production:** ~$160/month (Premium EP1 + infrastructure)

**vs. Alternatives:**
- CodeRabbit: $380-780/month (20 users)
- GitHub Copilot: $200-780/month (20 users)
- **CodeWarden: $10-160/month** (3-78x cheaper)

## 📝 License

MIT License - see LICENSE file for details

---

**Ready to deploy!** See [DEPLOYMENT-GUIDE.md](docs/DEPLOYMENT-GUIDE.md) for complete instructions.
