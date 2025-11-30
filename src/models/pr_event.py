# src/models/pr_event.py
"""
Pydantic Models for Pull Request Events

Data models for Azure DevOps webhook payloads and file changes.

Version: 1.0.0
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


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

    pr_id: int = Field(..., description="Pull request ID")
    repository_id: str = Field(..., description="Repository UUID")
    repository_name: str = Field(..., description="Repository name")
    project_id: str = Field(..., description="Project UUID or name")
    project_name: str = Field(..., description="Project name")
    source_branch: str = Field(..., description="Source branch ref (e.g., refs/heads/feature)")
    target_branch: str = Field(..., description="Target branch ref (e.g., refs/heads/main)")
    source_commit_id: Optional[str] = Field(None, description="Latest source commit SHA")
    event_type: str = Field(..., description="Webhook event type (e.g., git.pullrequest.updated)")
    title: str = Field(..., description="PR title")
    description: Optional[str] = Field(None, description="PR description")
    author_email: str = Field(..., description="Author email address")
    author_name: Optional[str] = Field(None, description="Author display name")
    
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
            title=resource.get('title', 'No title'),
            description=resource.get('description'),
            author_email=created_by.get('uniqueName', 'unknown@example.com'),
            author_name=created_by.get('displayName')
        )
    
    class Config:
        use_enum_values = True


class FileChange(BaseModel):
    """
    Represents a changed file in the PR with diff analysis.
    """
    
    path: str = Field(..., description="File path relative to repo root")
    file_type: FileType = Field(..., description="Type of IaC file")
    diff_content: str = Field(..., description="Unified diff content")
    lines_added: int = Field(ge=0, description="Number of lines added")
    lines_deleted: int = Field(ge=0, description="Number of lines deleted")
    changed_sections: List = Field(
        default_factory=list,
        description="Parsed changed sections from diff parser"
    )
    
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
