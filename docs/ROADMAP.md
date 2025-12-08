  1. Multi-Agent Review Architecture

  Split reviews into specialized agents that run in parallel:
  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
  │  Security Agent │  │ Performance     │  │  Style/Quality  │
  │  - Secrets      │  │ - N+1 queries   │  │  - Naming       │
  │  - Injection    │  │ - Memory leaks  │  │  - Complexity   │
  │  - Auth issues  │  │ - Inefficiency  │  │  - Best practice│
  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
           └──────────────┬─────────────────────────┘
                     Aggregator + Deduplication
  - Each agent has focused prompts → better accuracy
  - agent_type field already exists in ReviewIssue model

  2. Repository Configuration File

  .codewarden.yml in repo root:
  version: 1
  severity_threshold: medium  # Only report medium+ issues
  ignore_paths:
    - "**/*.test.ts"
    - "vendor/**"
  custom_rules:
    - pattern: "TODO|FIXME"
      severity: low
      message: "Unresolved TODO found"
  reviewers:
    security: strict
    performance: normal

  ---
  Medium Impact Features

  4. Cross-File Context Analysis

  Currently each file is reviewed in isolation. Add:
  - Import/dependency graph awareness
  - "This function is called from 5 places" context
  - Related file snippets in prompts

  5. Secret Detection Pre-Filter

  Fast regex-based scan before AI review:
  - API keys, tokens, passwords
  - High-entropy strings
  - Known secret patterns
  - Flags as CRITICAL immediately (no AI cost)

  6. PR Analytics Dashboard

  Azure Function + Static Web App:
  - Issues over time trend
  - Most common issue types
  - Cost per repository
  - Review coverage metrics

  7. Incremental Review

  For updated PRs:
  - Only re-review changed files
  - Keep previous results for unchanged files
  - Track iteration history

  ---
  Lower Effort Wins

  8. Configurable Comment Format

  - Emoji severity indicators: 🔴🟠🟡🔵
  - Collapsible details
  - Code suggestion blocks with copy button

  9. Review Summary PR Comment

  Single top-level comment with:
  ## CodeWarden Review Summary
  | Severity | Count |
  |----------|-------|
  | 🔴 Critical | 2 |
  | 🟠 High | 5 |
  | 🟡 Medium | 8 |

  **Top Issues:**
  1. SQL injection in `api/users.py:45`
  2. Missing authentication on `/admin` endpoint

  10. Dry Run Mode

  - Review without posting comments
  - Returns results via API response
  - Useful for testing/integration
