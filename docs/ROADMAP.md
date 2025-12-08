# Roadmap

Future features and improvements planned for CodeWarden.

> **Legend:** 🔴 Not Started | 🟡 In Progress | 🟢 Complete

---

## High Impact

### 1. Multi-Agent Review Architecture 🔴

Split reviews into specialized agents that run in parallel for better accuracy:

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Security Agent │  │  Performance    │  │  Style/Quality  │
│  • Secrets      │  │  • N+1 queries  │  │  • Naming       │
│  • Injection    │  │  • Memory leaks │  │  • Complexity   │
│  • Auth issues  │  │  • Inefficiency │  │  • Best practice│
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         └───────────────┬────────────────────────┘
                   Aggregator + Deduplication
```

**Benefits:**
- Focused prompts per domain = better accuracy
- Parallel execution = faster reviews
- `agent_type` field already exists in ReviewIssue model

---

### 2. Repository Configuration File 🔴

Allow per-repo customization via `.codewarden.yml`:

```yaml
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
```

---

## Medium Impact

### 3. Cross-File Context Analysis 🔴

Currently each file is reviewed in isolation. Improvements:

- Import/dependency graph awareness
- "This function is called from 5 places" context
- Related file snippets in prompts

---

### 4. Secret Detection Pre-Filter 🔴

Fast regex-based scan before AI review:

- API keys, tokens, passwords
- High-entropy strings
- Known secret patterns (AWS, Azure, GitHub, etc.)
- Flags as CRITICAL immediately (no AI cost)

---

### 5. PR Analytics Dashboard 🔴

Azure Function + Static Web App for insights:

- Issues over time trend
- Most common issue types
- Cost per repository
- Review coverage metrics

---

### 6. Incremental Review 🔴

For updated PRs:

- Only re-review changed files since last review
- Keep previous results for unchanged files
- Track iteration history

---

## Quick Wins

### 7. Configurable Comment Format 🔴

- Emoji severity indicators: 🔴 🟠 🟡 🔵
- Collapsible details for long explanations
- Code suggestion blocks with copy button

---

### 8. Review Summary Comment 🔴

Single top-level PR comment with overview:

```markdown
## CodeWarden Review Summary

| Severity | Count |
|----------|-------|
| 🔴 Critical | 2 |
| 🟠 High | 5 |
| 🟡 Medium | 8 |

**Top Issues:**
1. SQL injection in `api/users.py:45`
2. Missing authentication on `/admin` endpoint
```

---

### 9. Dry Run Mode 🔴

- Review without posting comments
- Returns results via API response
- Useful for testing and CI integration

---

## Contributing

Have an idea? Open an issue or submit a PR. See [CONTRIBUTING.md](../CONTRIBUTING.md).
