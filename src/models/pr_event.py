# src/models/pr_event.py
"""
Pydantic Models for Pull Request Events

Data models for Azure DevOps webhook payloads and file changes.

Version: 2.5.14 - Enhanced branch validation
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum
import re


class FileType(str, Enum):
    """Type of Infrastructure as Code file."""
    TERRAFORM = "terraform"
    ANSIBLE = "ansible"
    PIPELINE = "pipeline"
    JSON = "json"
    UNKNOWN = "unknown"


class PREvent(BaseModel):
    """
    Pull Request event from Azure DevOps webhook.

    Maps Azure DevOps webhook payload to internal representation.
    """

    pr_id: int = Field(..., gt=0, lt=2147483647, description="Pull request ID")
    repository_id: str = Field(..., max_length=100, description="Repository UUID")
    repository_name: str = Field(..., max_length=500, description="Repository name")
    project_id: str = Field(..., max_length=100, description="Project UUID or name")
    project_name: str = Field(..., max_length=500, description="Project name")
    source_branch: str = Field(..., max_length=500, description="Source branch ref (e.g., refs/heads/feature)")
    target_branch: str = Field(..., max_length=500, description="Target branch ref (e.g., refs/heads/main)")
    source_commit_id: Optional[str] = Field(None, max_length=100, description="Latest source commit SHA")
    event_type: str = Field(..., max_length=100, description="Webhook event type (e.g., git.pullrequest.updated)")
    title: str = Field(..., max_length=1000, description="PR title")
    description: Optional[str] = Field(None, max_length=10000, description="PR description")
    author_email: str = Field(..., max_length=500, description="Author email address")
    author_name: Optional[str] = Field(None, max_length=500, description="Author display name")

    @field_validator('source_branch', 'target_branch')
    @classmethod
    def validate_branch_ref(cls, v: str) -> str:
        """
        Validate branch reference format.

        Ensures branch names don't contain command injection characters
        or path traversal patterns.
        """
        if not v:
            raise ValueError("Branch reference cannot be empty")

        # Check for null bytes
        if '\x00' in v:
            raise ValueError("Branch reference contains null bytes")

        # Check for newlines (log injection)
        if '\n' in v or '\r' in v:
            raise ValueError("Branch reference contains newlines")

        # Check for path traversal patterns BEFORE regex
        if '..' in v:
            raise ValueError("Branch reference contains path traversal pattern")

        # Check for double slashes (malformed paths)
        if '//' in v:
            raise ValueError("Branch reference contains invalid double slashes")

        # Check for trailing slash
        if v.endswith('/'):
            raise ValueError("Branch reference cannot end with slash")

        # Valid Azure DevOps branch format: refs/heads/branch-name
        # More restrictive pattern: alphanumeric, dash, underscore, forward slash
        # Dots allowed but not consecutive (..) - checked above
        if not re.match(r'^refs/(heads|tags)/[a-zA-Z0-9][a-zA-Z0-9\-_./]*[a-zA-Z0-9]$|^refs/(heads|tags)/[a-zA-Z0-9]$', v):
            raise ValueError(f"Invalid branch reference format: {v}")

        return v

    @field_validator('title')
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate PR title is not just whitespace."""
        if not v or not v.strip():
            raise ValueError("PR title cannot be empty or whitespace")
        return v.strip()

    @field_validator('author_email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Basic email validation."""
        if not v or '@' not in v:
            raise ValueError("Invalid email address")
        if len(v.split('@')) != 2:
            raise ValueError("Invalid email address format")
        return v.lower().strip()
    
    @classmethod
    def from_azure_devops_webhook(cls, webhook_payload: dict) -> "PREvent":
        """
        Parse Azure DevOps webhook payload into PREvent.
        
        Azure DevOps sends webhooks with this structure:
        {
            "resource": {
                "pullRequestId": 123,
                "repository": {
                    "id": "abc123",
                    "name": "my-repo",
                    "project": {"id": "proj123", "name": "MyProject"}
                },
                "sourceRefName": "refs/heads/feature",
                "targetRefName": "refs/heads/main",
                "title": "My PR",
                "description": "Description",
                "createdBy": {
                    "uniqueName": "user@example.com",
                    "displayName": "User Name"
                }
            }
        }
        
        Args:
            webhook_payload: Full webhook payload from Azure DevOps
            
        Returns:
            Parsed PREvent
            
        Raises:
            ValueError: If payload structure is invalid
        """
        resource = webhook_payload.get('resource')
        if not resource:
            raise ValueError("Webhook payload missing 'resource' field")

        repository = resource.get('repository')
        if not repository:
            raise ValueError("Webhook resource missing 'repository' field")

        project = repository.get('project')
        if not project:
            raise ValueError("Webhook repository missing 'project' field")

        created_by = resource.get('createdBy', {})

        # Validate required resource fields
        required_fields = {
            'pullRequestId': 'PR ID',
            'sourceRefName': 'source branch',
            'targetRefName': 'target branch'
        }

        for field, description in required_fields.items():
            if field not in resource:
                raise ValueError(
                    f"Webhook resource missing required field '{field}' ({description})"
                )

        # Get event type from webhook root
        event_type = webhook_payload.get('eventType', 'git.pullrequest.updated')

        # Get latest commit ID from source branch (last merge source commit)
        source_commit_id = None
        if 'lastMergeSourceCommit' in resource:
            source_commit_id = resource['lastMergeSourceCommit'].get('commitId')

        # Validate required fields have values (not just exist)
        if not resource.get('title'):
            raise ValueError("PR title is required")
        if not created_by.get('uniqueName'):
            raise ValueError("Author email is required")

        return cls(
            pr_id=resource['pullRequestId'],
            repository_id=repository['id'],
            repository_name=repository['name'],
            project_id=project.get('id') or project.get('name'),
            project_name=project.get('name', 'Unknown'),
            source_branch=resource['sourceRefName'],
            target_branch=resource['targetRefName'],
            source_commit_id=source_commit_id,
            event_type=event_type,
            title=resource['title'],
            description=resource.get('description'),
            author_email=created_by['uniqueName'],
            author_name=created_by.get('displayName')
        )
    
    class Config:
        use_enum_values = True


class FileChange(BaseModel):
    """
    Represents a changed file in the PR with diff analysis.
    """
    
    path: str = Field(..., max_length=2000, description="File path relative to repo root")
    file_type: FileType = Field(..., description="Type of IaC file")
    diff_content: str = Field(..., max_length=1000000, description="Unified diff content")
    lines_added: int = Field(ge=0, lt=1000000, description="Number of lines added")
    lines_deleted: int = Field(ge=0, lt=1000000, description="Number of lines deleted")
    changed_sections: List = Field(
        default_factory=list,
        max_length=10000,
        description="Parsed changed sections from diff parser"
    )

    @field_validator('path')
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """
        Validate file path to prevent path traversal.

        Similar to review_result.py validation.
        """
        if not v:
            raise ValueError("file path cannot be empty")

        # Check for null bytes
        if '\x00' in v:
            raise ValueError("file path contains null bytes")

        # Check for path traversal
        import os
        normalized = os.path.normpath(v)
        if '..' in normalized.split(os.sep):
            raise ValueError("file path contains path traversal")

        return v
    
    @property
    def total_changes(self) -> int:
        """Total number of changed lines."""
        return self.lines_added + self.lines_deleted
    
    @property
    def is_new_file(self) -> bool:
        """Check if this is a newly added file."""
        return self.lines_deleted == 0 and self.lines_added > 0
    
    @property
    def is_deleted_file(self) -> bool:
        """Check if this file was deleted."""
        return self.lines_added == 0 and self.lines_deleted > 0
    
    class Config:
        arbitrary_types_allowed = True  # Allow ChangedSection objects
        use_enum_values = True
