# src/services/file_type_registry.py
"""
File Type Registry

Comprehensive registry of file types with intelligent detection and best practices.
Transforms CodeWarden from IaC-specific to universal code review.

Version: 2.6.1 - Bug fixes and .NET support
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import re
import threading
from functools import lru_cache

from src.utils.logging import get_logger

logger = get_logger(__name__)


class FileCategory(str, Enum):
    """
    Comprehensive file categories for universal code review.

    Categories are organized by domain for easier maintenance.
    Each category has associated best practices and detection rules.
    """
    # ==========================================================================
    # PROGRAMMING LANGUAGES
    # ==========================================================================
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CSHARP = "csharp"
    VBNET = "vbnet"
    GO = "go"
    CPP = "cpp"
    C = "c"
    RUBY = "ruby"
    PHP = "php"
    SWIFT = "swift"
    LUA = "lua"
    PERL = "perl"
    R = "r"
    DART = "dart"
    ELIXIR = "elixir"
    HASKELL = "haskell"
    CLOJURE = "clojure"
    FSHARP = "fsharp"
    OCAML = "ocaml"
    ERLANG = "erlang"
    JULIA = "julia"
    ZIG = "zig"
    NIM = "nim"
    CRYSTAL = "crystal"
    V = "v"
    OBJECTIVE_C = "objective_c"

    # ==========================================================================
    # INFRASTRUCTURE AS CODE
    # ==========================================================================
    TERRAFORM = "terraform"
    ANSIBLE = "ansible"
    CLOUDFORMATION = "cloudformation"
    KUBERNETES = "kubernetes"
    DOCKER = "docker"
    HELM = "helm"
    ARM_TEMPLATE = "arm_template"
    SERVERLESS = "serverless"
    CDK = "cdk"
    CROSSPLANE = "crossplane"
    KUSTOMIZE = "kustomize"

    # ==========================================================================
    # CI/CD PIPELINES
    # ==========================================================================
    AZURE_PIPELINE = "azure_pipeline"
    GITLAB_CI = "gitlab_ci"
    CIRCLECI = "circleci"
    TRAVIS_CI = "travis_ci"
    BITBUCKET_PIPELINE = "bitbucket_pipeline"
    DRONE_CI = "drone_ci"
    TEKTON = "tekton"
    ARGO_WORKFLOW = "argo_workflow"

    # ==========================================================================
    # CONFIGURATION FILES
    # ==========================================================================
    JSON = "json"
    YAML = "yaml"
    TOML = "toml"
    XML = "xml"
    INI = "ini"
    ENV = "env"
    PROPERTIES = "properties"
    HCL = "hcl"
    HOCON = "hocon"
    CONF = "conf"
    EDITORCONFIG = "editorconfig"

    # ==========================================================================
    # WEB DEVELOPMENT
    # ==========================================================================
    HTML = "html"
    CSS = "css"
    SCSS = "scss"
    SASS = "sass"
    LESS = "less"
    VUE = "vue"
    SVELTE = "svelte"
    JSX = "jsx"
    TSX = "tsx"
    ASTRO = "astro"
    MDX = "mdx"

    # ==========================================================================
    # DATA & QUERY LANGUAGES
    # ==========================================================================
    SQL = "sql"
    GRAPHQL = "graphql"
    PRISMA = "prisma"
    PROTOBUF = "protobuf"
    THRIFT = "thrift"
    AVRO = "avro"

    # ==========================================================================
    # SHELL & SCRIPTS
    # ==========================================================================
    BASH = "bash"
    POWERSHELL = "powershell"
    BATCH = "batch"
    ZSH = "zsh"
    FISH = "fish"

    # ==========================================================================
    # DOCUMENTATION
    # ==========================================================================
    MARKDOWN = "markdown"
    RST = "rst"
    ASCIIDOC = "asciidoc"
    LATEX = "latex"
    ORGMODE = "orgmode"

    # ==========================================================================
    # BUILD SYSTEMS
    # ==========================================================================
    MAKEFILE = "makefile"
    CMAKE = "cmake"
    GRADLE = "gradle"
    MAVEN = "maven"
    BAZEL = "bazel"
    MESON = "meson"
    NINJA = "ninja"
    SCONS = "scons"
    PREMAKE = "premake"

    # ==========================================================================
    # PACKAGE MANAGEMENT
    # ==========================================================================
    NPM_PACKAGE = "npm_package"
    REQUIREMENTS = "requirements"
    GEMFILE = "gemfile"
    COMPOSER = "composer"
    PUBSPEC = "pubspec"
    PODFILE = "podfile"
    NUGET = "nuget"
    GO_MOD = "go_mod"
    POETRY = "poetry"
    PIPFILE = "pipfile"
    CONDA = "conda"
    CONAN = "conan"
    VCPKG = "vcpkg"
    SWIFT_PACKAGE = "swift_package"

    # ==========================================================================
    # TESTING
    # ==========================================================================
    JEST = "jest"
    PYTEST = "pytest"
    JUNIT = "junit"
    PLAYWRIGHT = "playwright"
    CYPRESS = "cypress"
    ROBOT = "robot"

    # ==========================================================================
    # SECURITY & COMPLIANCE
    # ==========================================================================
    SECURITY_POLICY = "security_policy"
    CODEOWNERS = "codeowners"
    GITIGNORE = "gitignore"
    DOCKERIGNORE = "dockerignore"
    ESLINT = "eslint"
    PRETTIER = "prettier"
    RENOVATE = "renovate"

    # ==========================================================================
    # GENERIC (Fallback - still reviewed!)
    # ==========================================================================
    GENERIC = "generic"

    # Backward compatibility aliases
    PIPELINE = "azure_pipeline"  # Legacy alias
    UNKNOWN = "generic"  # Legacy alias - now reviewed instead of filtered!


@dataclass
class BestPractices:
    """
    Best practices configuration for a file category.

    Contains security checks, common issues, and performance tips
    that will be included in AI prompts for targeted review guidance.
    """
    focus_areas: List[str] = field(default_factory=list)
    security_checks: List[str] = field(default_factory=list)
    common_issues: List[str] = field(default_factory=list)
    style_guidelines: List[str] = field(default_factory=list)
    performance_tips: List[str] = field(default_factory=list)

    def to_prompt_section(self, category_name: str) -> str:
        """
        Convert best practices to a formatted prompt section.

        Args:
            category_name: Display name of the category

        Returns:
            Formatted string for AI prompt inclusion
        """
        sections = []
        sections.append(f"**{category_name}-specific:**")

        if self.security_checks:
            sections.append("*Security:*")
            for check in self.security_checks[:5]:  # Limit to top 5
                sections.append(f"- {check}")

        if self.common_issues:
            sections.append("*Common Issues:*")
            for issue in self.common_issues[:5]:
                sections.append(f"- {issue}")

        if self.performance_tips:
            sections.append("*Performance:*")
            for tip in self.performance_tips[:3]:  # Limit to top 3
                sections.append(f"- {tip}")

        sections.append("")
        return "\n".join(sections)


@dataclass
class FileTypeConfig:
    """
    Configuration for a file type category.

    Defines detection rules, display settings, and associated best practices.
    """
    category: FileCategory
    extensions: List[str]  # File extensions (e.g., [".py", ".pyw"])
    path_patterns: List[str] = field(default_factory=list)  # Regex patterns for path-based detection
    display_name: str = ""
    token_estimate: int = 350  # Average tokens per file for this category
    priority: int = 0  # Higher = check first (for overlapping extensions like .yml)
    best_practices: BestPractices = field(default_factory=BestPractices)

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.category.value.replace("_", " ").title()


class FileTypeRegistry:
    """
    Comprehensive registry of file types with intelligent detection.

    Features:
    - Extension-based detection with priority ordering
    - Path pattern matching for context-aware classification
    - Best practices lookup for each category
    - Token estimation for cost calculation
    - Caching for performance
    - Thread-safe initialization (v2.6.1)

    Usage:
        category = FileTypeRegistry.classify("src/main.py")
        practices = FileTypeRegistry.get_best_practices(category)
        tokens = FileTypeRegistry.get_token_estimate(category)
    """

    _configs: Dict[FileCategory, FileTypeConfig] = {}
    _extension_map: Dict[str, List[Tuple[FileTypeConfig, int]]] = {}  # ext -> [(config, priority)]
    _initialized: bool = False
    _init_lock: threading.Lock = threading.Lock()  # Thread-safe initialization (v2.6.1)

    @classmethod
    def _initialize(cls) -> None:
        """
        Initialize the registry with all file type configurations.

        Thread-safe using double-check locking pattern (v2.6.1).
        """
        # Fast path - already initialized
        if cls._initialized:
            return

        # Thread-safe initialization with double-check locking
        with cls._init_lock:
            # Check again inside lock (another thread may have initialized)
            if cls._initialized:
                return

            cls._register_programming_languages()
            cls._register_infrastructure_as_code()
            cls._register_cicd_pipelines()
            cls._register_configuration_files()
            cls._register_web_development()
            cls._register_data_and_query()
            cls._register_shell_and_scripts()
            cls._register_documentation()
            cls._register_build_systems()
            cls._register_package_management()
            cls._register_testing()
            cls._register_security_and_compliance()
            cls._register_generic()

            # Build extension map with priorities
            cls._build_extension_map()
            cls._initialized = True

            logger.info(
                "file_type_registry_initialized",
                categories=len(cls._configs),
                extensions=len(cls._extension_map)
            )

    @classmethod
    def _register(cls, config: FileTypeConfig) -> None:
        """Register a file type configuration."""
        cls._configs[config.category] = config

    @classmethod
    def _build_extension_map(cls) -> None:
        """Build extension to config mapping with priorities."""
        for config in cls._configs.values():
            for ext in config.extensions:
                ext_lower = ext.lower()
                if ext_lower not in cls._extension_map:
                    cls._extension_map[ext_lower] = []
                cls._extension_map[ext_lower].append((config, config.priority))

        # Sort by priority (descending) for each extension
        for ext in cls._extension_map:
            cls._extension_map[ext].sort(key=lambda x: x[1], reverse=True)

    # ==========================================================================
    # REGISTRATION METHODS
    # ==========================================================================

    @classmethod
    def _register_programming_languages(cls) -> None:
        """Register programming language configurations."""

        # Python
        cls._register(FileTypeConfig(
            category=FileCategory.PYTHON,
            extensions=[".py", ".pyw", ".pyi", ".pyx", ".pxd"],
            path_patterns=[r".*\.py$"],
            token_estimate=400,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Type hints and documentation",
                    "Error handling patterns",
                    "Resource management (context managers)",
                    "Import organization and circular imports"
                ],
                security_checks=[
                    "SQL injection (raw queries, f-strings in SQL)",
                    "Command injection (os.system, subprocess with shell=True)",
                    "Pickle deserialization vulnerabilities",
                    "Hardcoded credentials and secrets",
                    "Insecure random (random vs secrets module)",
                    "Path traversal in file operations",
                    "SSRF vulnerabilities in HTTP requests",
                    "Eval/exec with untrusted input"
                ],
                common_issues=[
                    "Mutable default arguments in functions",
                    "Bare except clauses catching all exceptions",
                    "Not using context managers for files/connections",
                    "Global variable mutation",
                    "Missing __init__.py in packages",
                    "Circular import dependencies"
                ],
                style_guidelines=[
                    "PEP 8 compliance",
                    "Docstrings for public functions/classes",
                    "Type hints for function signatures",
                    "Consistent naming conventions"
                ],
                performance_tips=[
                    "List comprehensions vs explicit loops",
                    "Generator expressions for large datasets",
                    "@lru_cache for expensive computations",
                    "Avoiding repeated dictionary lookups"
                ]
            )
        ))

        # JavaScript
        cls._register(FileTypeConfig(
            category=FileCategory.JAVASCRIPT,
            extensions=[".js", ".mjs", ".cjs"],
            token_estimate=350,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Async/await patterns",
                    "Error handling in promises",
                    "Module organization",
                    "Null/undefined handling"
                ],
                security_checks=[
                    "XSS vulnerabilities (innerHTML, document.write)",
                    "Prototype pollution attacks",
                    "eval() and Function() with untrusted input",
                    "Insecure dependencies (npm audit)",
                    "CORS misconfigurations",
                    "Command injection in child_process",
                    "SQL injection in template literals",
                    "Sensitive data in localStorage"
                ],
                common_issues=[
                    "Unhandled promise rejections",
                    "Memory leaks (event listeners, intervals)",
                    "Callback hell / promise chaining issues",
                    "Type coercion bugs (== vs ===)",
                    "'this' binding issues",
                    "Missing null/undefined checks"
                ],
                style_guidelines=[
                    "Consistent semicolon usage",
                    "Arrow functions for callbacks",
                    "Destructuring for cleaner code",
                    "Modern ES6+ features"
                ],
                performance_tips=[
                    "Debouncing/throttling expensive operations",
                    "Lazy loading modules",
                    "Avoiding synchronous operations",
                    "Efficient DOM manipulation"
                ]
            )
        ))

        # TypeScript
        cls._register(FileTypeConfig(
            category=FileCategory.TYPESCRIPT,
            extensions=[".ts", ".mts", ".cts"],
            token_estimate=400,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Type safety and strict mode",
                    "Interface vs type alias usage",
                    "Generics and type constraints",
                    "Module organization"
                ],
                security_checks=[
                    "Type assertions bypassing type safety (as any)",
                    "Non-null assertions on potentially null values",
                    "XSS vulnerabilities in template strings",
                    "Prototype pollution",
                    "eval() and Function() usage",
                    "Unsafe type coercion"
                ],
                common_issues=[
                    "Excessive use of 'any' type",
                    "Missing strict null checks",
                    "Implicit any in function parameters",
                    "Type assertion abuse",
                    "Missing return types",
                    "Incorrect generic constraints"
                ],
                style_guidelines=[
                    "Enable strict mode in tsconfig",
                    "Prefer interfaces for object types",
                    "Use readonly where applicable",
                    "Explicit return types for functions"
                ],
                performance_tips=[
                    "Avoid unnecessary type assertions",
                    "Use const assertions for literals",
                    "Proper module resolution",
                    "Tree-shaking friendly exports"
                ]
            )
        ))

        # Java
        cls._register(FileTypeConfig(
            category=FileCategory.JAVA,
            extensions=[".java"],
            token_estimate=450,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Exception handling patterns",
                    "Resource management (try-with-resources)",
                    "Thread safety",
                    "Memory management"
                ],
                security_checks=[
                    "SQL injection (PreparedStatement vs Statement)",
                    "XML External Entity (XXE) attacks",
                    "Deserialization vulnerabilities",
                    "Path traversal in file operations",
                    "Hardcoded credentials",
                    "Insecure cryptography",
                    "LDAP injection",
                    "Log injection"
                ],
                common_issues=[
                    "Catching generic Exception",
                    "Not closing resources properly",
                    "NullPointerException risks",
                    "Mutable objects in collections",
                    "Improper equals/hashCode",
                    "Static mutable state"
                ],
                style_guidelines=[
                    "Consistent naming conventions",
                    "Javadoc for public APIs",
                    "Proper access modifiers",
                    "Final for immutability"
                ],
                performance_tips=[
                    "StringBuilder for string concatenation",
                    "Appropriate collection types",
                    "Lazy initialization",
                    "Efficient stream operations"
                ]
            )
        ))

        # C#
        cls._register(FileTypeConfig(
            category=FileCategory.CSHARP,
            extensions=[".cs", ".csx"],
            token_estimate=450,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Async/await patterns",
                    "Nullable reference types",
                    "LINQ usage",
                    "Dependency injection"
                ],
                security_checks=[
                    "SQL injection (parameterized queries)",
                    "XSS in ASP.NET applications",
                    "Deserialization vulnerabilities",
                    "Path traversal",
                    "Hardcoded secrets",
                    "Insecure cryptography",
                    "CSRF protection"
                ],
                common_issues=[
                    "Async void methods",
                    "Not awaiting async calls",
                    "Null reference exceptions",
                    "IDisposable not disposed",
                    "Thread safety issues",
                    "Boxing/unboxing overhead"
                ],
                style_guidelines=[
                    "Microsoft naming conventions",
                    "XML documentation comments",
                    "Nullable annotations",
                    "Consistent file-scoped namespaces"
                ],
                performance_tips=[
                    "Span<T> for high-performance code",
                    "ValueTask for hot paths",
                    "Pooling for frequent allocations",
                    "ConfigureAwait(false) in libraries"
                ]
            )
        ))

        # VB.NET
        cls._register(FileTypeConfig(
            category=FileCategory.VBNET,
            extensions=[".vb", ".vbs"],
            token_estimate=400,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Async/await patterns",
                    "Option Strict/Explicit",
                    "LINQ usage",
                    "Modern VB syntax"
                ],
                security_checks=[
                    "SQL injection (parameterized queries)",
                    "XSS in ASP.NET applications",
                    "Deserialization vulnerabilities",
                    "Path traversal",
                    "Hardcoded secrets",
                    "Insecure cryptography"
                ],
                common_issues=[
                    "Late binding issues",
                    "Missing Option Strict",
                    "Null reference exceptions",
                    "IDisposable not disposed",
                    "Legacy VB6 patterns",
                    "On Error Resume Next abuse"
                ],
                style_guidelines=[
                    "Microsoft naming conventions",
                    "XML documentation comments",
                    "Option Strict On",
                    "Consistent casing"
                ],
                performance_tips=[
                    "Avoid late binding",
                    "Use StringBuilder for concatenation",
                    "Proper exception handling",
                    "ConfigureAwait(false) in libraries"
                ]
            )
        ))

        # Go
        cls._register(FileTypeConfig(
            category=FileCategory.GO,
            extensions=[".go"],
            token_estimate=350,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Error handling patterns",
                    "Goroutine lifecycle management",
                    "Interface design",
                    "Package organization"
                ],
                security_checks=[
                    "SQL injection (database/sql)",
                    "Command injection (os/exec)",
                    "Path traversal",
                    "Race conditions (go test -race)",
                    "Unvalidated input",
                    "TLS configuration issues",
                    "Unsafe package usage",
                    "Integer overflow"
                ],
                common_issues=[
                    "Ignoring errors (missing error checks)",
                    "Goroutine leaks",
                    "Nil pointer dereference",
                    "Error shadowing",
                    "Missing mutex for shared state",
                    "Ignoring context cancellation",
                    "Deferred function errors ignored"
                ],
                style_guidelines=[
                    "Effective Go guidelines",
                    "Proper error wrapping",
                    "Consistent naming",
                    "Package documentation"
                ],
                performance_tips=[
                    "sync.Pool for frequent allocations",
                    "Avoid string concatenation in loops",
                    "Pre-allocate slice capacity",
                    "Buffered channels where appropriate"
                ]
            )
        ))

        # C++
        cls._register(FileTypeConfig(
            category=FileCategory.CPP,
            extensions=[".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh", ".h++"],
            token_estimate=400,
            priority=8,  # Lower priority for .h files (could be C)
            best_practices=BestPractices(
                focus_areas=[
                    "Memory management (RAII)",
                    "Modern C++ features",
                    "Exception safety",
                    "Template metaprogramming"
                ],
                security_checks=[
                    "Buffer overflow vulnerabilities",
                    "Use-after-free bugs",
                    "Memory leaks",
                    "Integer overflow",
                    "Format string vulnerabilities",
                    "Null pointer dereference",
                    "Uninitialized variables",
                    "Race conditions"
                ],
                common_issues=[
                    "Raw pointer misuse",
                    "Missing virtual destructors",
                    "Object slicing",
                    "Resource leaks",
                    "Undefined behavior",
                    "Copy vs move semantics"
                ],
                style_guidelines=[
                    "Modern C++ (C++17/20/23)",
                    "Smart pointers over raw",
                    "const correctness",
                    "RAII for resources"
                ],
                performance_tips=[
                    "Move semantics for large objects",
                    "Reserve for vectors",
                    "Avoid unnecessary copies",
                    "Cache-friendly data structures"
                ]
            )
        ))

        # C
        cls._register(FileTypeConfig(
            category=FileCategory.C,
            extensions=[".c", ".h"],
            token_estimate=350,
            priority=5,  # Lower priority - .h could be C++
            best_practices=BestPractices(
                focus_areas=[
                    "Memory management",
                    "Pointer safety",
                    "Error handling",
                    "Portability"
                ],
                security_checks=[
                    "Buffer overflow (strcpy, sprintf)",
                    "Format string vulnerabilities",
                    "Integer overflow",
                    "Use-after-free",
                    "Double-free",
                    "Null pointer dereference",
                    "Uninitialized memory",
                    "Race conditions"
                ],
                common_issues=[
                    "Missing NULL checks",
                    "Memory leaks",
                    "Off-by-one errors",
                    "Unsafe string functions",
                    "Missing error handling",
                    "Undefined behavior"
                ],
                style_guidelines=[
                    "Consistent coding style",
                    "Proper header guards",
                    "Function documentation",
                    "Meaningful names"
                ],
                performance_tips=[
                    "Minimize allocations",
                    "Cache-friendly access patterns",
                    "Inline small functions",
                    "Avoid unnecessary copies"
                ]
            )
        ))

        # Ruby
        cls._register(FileTypeConfig(
            category=FileCategory.RUBY,
            extensions=[".rb", ".rake", ".gemspec"],
            token_estimate=350,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Object-oriented design",
                    "Metaprogramming safety",
                    "Block and proc usage",
                    "Rails conventions (if applicable)"
                ],
                security_checks=[
                    "SQL injection (ActiveRecord)",
                    "Mass assignment vulnerabilities",
                    "XSS in views",
                    "Command injection (system, backticks)",
                    "YAML deserialization attacks",
                    "Path traversal",
                    "Unsafe regex (ReDoS)",
                    "Hardcoded secrets"
                ],
                common_issues=[
                    "Excessive metaprogramming",
                    "Missing nil checks",
                    "N+1 query problems",
                    "Thread safety issues",
                    "Memory bloat",
                    "Monkey patching risks"
                ],
                style_guidelines=[
                    "Ruby style guide compliance",
                    "RuboCop lint rules",
                    "YARD documentation",
                    "Consistent naming"
                ],
                performance_tips=[
                    "Eager loading associations",
                    "Avoid method_missing abuse",
                    "Use symbols for hash keys",
                    "Freeze string literals"
                ]
            )
        ))

        # PHP
        cls._register(FileTypeConfig(
            category=FileCategory.PHP,
            extensions=[".php", ".phtml", ".php3", ".php4", ".php5", ".phps"],
            token_estimate=350,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Modern PHP (7.4+/8.x)",
                    "Type declarations",
                    "Error handling",
                    "Dependency injection"
                ],
                security_checks=[
                    "SQL injection (PDO/MySQLi)",
                    "XSS vulnerabilities",
                    "Command injection (exec, system)",
                    "File inclusion vulnerabilities",
                    "Session hijacking",
                    "CSRF protection",
                    "Path traversal",
                    "Deserialization attacks"
                ],
                common_issues=[
                    "Global state abuse",
                    "Missing type hints",
                    "Inconsistent return types",
                    "Error suppression (@)",
                    "Deprecated functions",
                    "Memory issues"
                ],
                style_guidelines=[
                    "PSR-12 coding standard",
                    "PHPDoc comments",
                    "Strict types declaration",
                    "Consistent naming"
                ],
                performance_tips=[
                    "OpCache configuration",
                    "Avoid unnecessary queries",
                    "Use generators for large datasets",
                    "Cache expensive operations"
                ]
            )
        ))

        # Swift
        cls._register(FileTypeConfig(
            category=FileCategory.SWIFT,
            extensions=[".swift"],
            token_estimate=400,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Swift concurrency (async/await)",
                    "Memory management (ARC)",
                    "Protocol-oriented design",
                    "Error handling"
                ],
                security_checks=[
                    "Insecure data storage (Keychain)",
                    "Hardcoded credentials",
                    "Insecure network configuration",
                    "Certificate pinning",
                    "Biometric authentication bypass",
                    "URL scheme vulnerabilities"
                ],
                common_issues=[
                    "Force unwrapping (!)",
                    "Retain cycles",
                    "Main thread blocking",
                    "Incorrect Sendable conformance",
                    "Missing error handling",
                    "Improper optionals"
                ],
                style_guidelines=[
                    "Swift API guidelines",
                    "SwiftLint rules",
                    "Documentation comments",
                    "Consistent naming"
                ],
                performance_tips=[
                    "Value types vs reference types",
                    "Lazy initialization",
                    "Avoid unnecessary copies",
                    "Efficient collection usage"
                ]
            )
        ))

    @classmethod
    def _register_infrastructure_as_code(cls) -> None:
        """Register Infrastructure as Code configurations."""

        # Terraform
        cls._register(FileTypeConfig(
            category=FileCategory.TERRAFORM,
            extensions=[".tf", ".tfvars", ".tfstate"],
            token_estimate=300,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "State management",
                    "Module organization",
                    "Variable validation",
                    "Resource naming conventions"
                ],
                security_checks=[
                    "Public endpoints without firewall rules",
                    "Missing encryption at rest/transit",
                    "Overly permissive IAM policies",
                    "Hardcoded secrets in variables",
                    "Missing logging/monitoring",
                    "Unrestricted security groups (0.0.0.0/0)",
                    "Unencrypted S3 buckets",
                    "Missing MFA delete on S3"
                ],
                common_issues=[
                    "Missing required tags",
                    "Hardcoded values instead of variables",
                    "Missing lifecycle rules",
                    "Deprecated resource types",
                    "Missing depends_on where needed",
                    "Count vs for_each misuse"
                ],
                style_guidelines=[
                    "Consistent naming conventions",
                    "Module structure best practices",
                    "Variable descriptions",
                    "Output documentation"
                ],
                performance_tips=[
                    "Parallelism tuning",
                    "Data source caching",
                    "Module versioning",
                    "State file management"
                ]
            )
        ))

        # Kubernetes YAML (detected by path patterns)
        cls._register(FileTypeConfig(
            category=FileCategory.KUBERNETES,
            extensions=[],  # Detected by path patterns
            path_patterns=[
                r".*k8s.*\.ya?ml$",
                r".*kubernetes.*\.ya?ml$",
                r".*/manifests/.*\.ya?ml$",
                r".*/deploy(ment)?s?/.*\.ya?ml$",
                r".*/kube/.*\.ya?ml$",
                r".*deployment\.ya?ml$",
                r".*service\.ya?ml$",
                r".*ingress\.ya?ml$",
                r".*configmap\.ya?ml$",
                r".*secret\.ya?ml$",
                r".*statefulset\.ya?ml$",
                r".*daemonset\.ya?ml$",
                r".*cronjob\.ya?ml$",
                r".*job\.ya?ml$",
                r".*namespace\.ya?ml$",
                r".*pvc?\.ya?ml$",
                r".*rbac.*\.ya?ml$",
                r".*networkpolicy\.ya?ml$",
                r".*hpa\.ya?ml$",
            ],
            token_estimate=350,
            priority=100,  # High priority for path-based detection
            best_practices=BestPractices(
                focus_areas=[
                    "Resource limits and requests",
                    "Pod security context",
                    "Service mesh integration",
                    "Namespace organization"
                ],
                security_checks=[
                    "Running as root user",
                    "Privileged containers",
                    "Missing network policies",
                    "Secrets in plain text",
                    "Missing RBAC restrictions",
                    "Host path mounts",
                    "Capability escalation",
                    "Missing pod security standards"
                ],
                common_issues=[
                    "Missing resource limits",
                    "Missing health checks (liveness/readiness)",
                    "Incorrect image pull policy",
                    "Missing pod disruption budgets",
                    "Improper label selectors",
                    "Missing anti-affinity rules"
                ],
                style_guidelines=[
                    "Consistent label usage",
                    "Proper annotations",
                    "Resource naming conventions",
                    "Namespace organization"
                ],
                performance_tips=[
                    "Horizontal pod autoscaling",
                    "Vertical pod autoscaling",
                    "Resource right-sizing",
                    "Node affinity for specialized workloads"
                ]
            )
        ))

        # Docker
        cls._register(FileTypeConfig(
            category=FileCategory.DOCKER,
            extensions=["Dockerfile", ".dockerfile"],
            path_patterns=[
                r".*[Dd]ockerfile.*",
                r".*\.dockerfile$",
                r".*docker-compose.*\.ya?ml$",
                r".*compose\.ya?ml$",
            ],
            token_estimate=250,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Multi-stage builds",
                    "Layer optimization",
                    "Security hardening",
                    "Base image selection"
                ],
                security_checks=[
                    "Running as root user",
                    "Secrets in build args",
                    "Using :latest tag",
                    "Untrusted base images",
                    "Missing USER directive",
                    "Sensitive files in image",
                    "Package manager cache in image"
                ],
                common_issues=[
                    "Missing .dockerignore",
                    "Inefficient layer caching",
                    "Large image size",
                    "Missing HEALTHCHECK",
                    "ADD instead of COPY",
                    "Shell form vs exec form"
                ],
                style_guidelines=[
                    "Consistent instruction format",
                    "Proper ARG/ENV usage",
                    "Label metadata",
                    "Sorted package lists"
                ],
                performance_tips=[
                    "Multi-stage builds",
                    "Order layers by change frequency",
                    "Use alpine/distroless base images",
                    "BuildKit caching"
                ]
            )
        ))

        # Ansible
        cls._register(FileTypeConfig(
            category=FileCategory.ANSIBLE,
            extensions=[],
            path_patterns=[
                r".*ansible.*\.ya?ml$",
                r".*/playbooks?/.*\.ya?ml$",
                r".*/roles/.*\.ya?ml$",
                r".*playbook.*\.ya?ml$",
                r".*/tasks/.*\.ya?ml$",
                r".*/handlers/.*\.ya?ml$",
                r".*/vars/.*\.ya?ml$",
                r".*/defaults/.*\.ya?ml$",
                r".*/group_vars/.*\.ya?ml$",
                r".*/host_vars/.*\.ya?ml$",
                r".*inventory.*\.ya?ml$",
                r".*site\.ya?ml$",
            ],
            token_estimate=400,
            priority=90,
            best_practices=BestPractices(
                focus_areas=[
                    "Idempotency",
                    "Role organization",
                    "Variable management",
                    "Task error handling"
                ],
                security_checks=[
                    "Hardcoded passwords/secrets",
                    "Plaintext credentials in vars",
                    "Missing become_method",
                    "Insecure file permissions",
                    "Shell command injection",
                    "Vault encryption for secrets"
                ],
                common_issues=[
                    "Missing idempotency",
                    "No error handling",
                    "Hardcoded values",
                    "Missing tags",
                    "Shell instead of modules",
                    "Missing changed_when/failed_when"
                ],
                style_guidelines=[
                    "YAML formatting",
                    "Task naming",
                    "Role structure",
                    "Variable naming"
                ],
                performance_tips=[
                    "Async tasks for long operations",
                    "Limit/serial for large inventories",
                    "Fact caching",
                    "SSH pipelining"
                ]
            )
        ))

        # Helm
        cls._register(FileTypeConfig(
            category=FileCategory.HELM,
            extensions=[],
            path_patterns=[
                r".*/charts?/.*\.ya?ml$",
                r".*/templates/.*\.ya?ml$",
                r".*Chart\.ya?ml$",
                r".*values.*\.ya?ml$",
                r".*helmfile.*\.ya?ml$",
            ],
            token_estimate=350,
            priority=95,
            best_practices=BestPractices(
                focus_areas=[
                    "Template best practices",
                    "Values schema",
                    "Chart versioning",
                    "Dependencies management"
                ],
                security_checks=[
                    "Secrets in values.yaml",
                    "Missing resource limits",
                    "Privileged containers",
                    "Missing security context",
                    "Exposed services"
                ],
                common_issues=[
                    "Missing NOTES.txt",
                    "Improper template functions",
                    "Missing required values",
                    "Version drift",
                    "Missing labels"
                ],
                style_guidelines=[
                    "Consistent indentation",
                    "Helper templates",
                    "Value documentation",
                    "Chart naming"
                ],
                performance_tips=[
                    "Efficient hooks",
                    "Resource optimization",
                    "Template caching"
                ]
            )
        ))

        # CloudFormation
        cls._register(FileTypeConfig(
            category=FileCategory.CLOUDFORMATION,
            extensions=[],
            path_patterns=[
                r".*cloudformation.*\.ya?ml$",
                r".*cfn.*\.ya?ml$",
                r".*\.template\.ya?ml$",
                r".*sam.*\.ya?ml$",
            ],
            token_estimate=400,
            priority=85,
            best_practices=BestPractices(
                focus_areas=[
                    "Stack organization",
                    "Parameter validation",
                    "Nested stacks",
                    "Drift detection"
                ],
                security_checks=[
                    "Public S3 buckets",
                    "Overly permissive IAM",
                    "Missing encryption",
                    "Hardcoded credentials",
                    "Security group rules",
                    "VPC configuration"
                ],
                common_issues=[
                    "Missing DeletionPolicy",
                    "Hardcoded values",
                    "Circular dependencies",
                    "Missing Outputs",
                    "Version constraints"
                ],
                style_guidelines=[
                    "Template organization",
                    "Metadata usage",
                    "Description fields",
                    "Consistent naming"
                ],
                performance_tips=[
                    "Nested stacks for large templates",
                    "Change sets for updates",
                    "Stack policies"
                ]
            )
        ))

    @classmethod
    def _register_cicd_pipelines(cls) -> None:
        """Register CI/CD pipeline configurations."""

        # GitLab CI
        cls._register(FileTypeConfig(
            category=FileCategory.GITLAB_CI,
            extensions=[".gitlab-ci.yml"],
            path_patterns=[
                r".*\.gitlab-ci\.yml$",
                r".*\.gitlab/ci/.*\.ya?ml$",
            ],
            token_estimate=350,
            priority=110,
            best_practices=BestPractices(
                focus_areas=[
                    "Pipeline structure",
                    "Variable management",
                    "Rules and conditions",
                    "Includes and extends"
                ],
                security_checks=[
                    "Exposed secrets",
                    "Protected environments",
                    "Masked variables",
                    "Script injection",
                    "Runner security"
                ],
                common_issues=[
                    "Missing timeout",
                    "Cache configuration",
                    "Artifact management",
                    "Job dependencies",
                    "Rules complexity"
                ],
                style_guidelines=[
                    "Job naming",
                    "Stage organization",
                    "Template usage",
                    "Documentation"
                ],
                performance_tips=[
                    "DAG mode",
                    "Parallel jobs",
                    "Cache efficiency",
                    "Needs keyword"
                ]
            )
        ))

        # Azure Pipelines
        cls._register(FileTypeConfig(
            category=FileCategory.AZURE_PIPELINE,
            extensions=[],
            path_patterns=[
                r".*azure-pipelines?\.ya?ml$",
                r".*\.azure-pipelines/.*\.ya?ml$",
                r".*\.azuredevops/.*\.ya?ml$",
                r".*/pipelines?/.*\.ya?ml$",
            ],
            token_estimate=350,
            priority=105,
            best_practices=BestPractices(
                focus_areas=[
                    "Template usage",
                    "Variable groups",
                    "Service connections",
                    "Stage dependencies"
                ],
                security_checks=[
                    "Secrets in logs",
                    "Missing approval gates for production",
                    "Insecure service connections",
                    "Missing branch policies",
                    "Unprotected variable groups",
                    "Script injection vulnerabilities"
                ],
                common_issues=[
                    "Missing condition checks",
                    "Hardcoded pool names",
                    "Missing artifact publishing",
                    "Improper dependency handling",
                    "Missing timeout settings"
                ],
                style_guidelines=[
                    "Template organization",
                    "Parameter documentation",
                    "Stage naming",
                    "Job naming"
                ],
                performance_tips=[
                    "Pipeline caching",
                    "Parallel jobs",
                    "Incremental builds",
                    "Container jobs"
                ]
            )
        ))

    @classmethod
    def _register_configuration_files(cls) -> None:
        """Register configuration file types."""

        # JSON
        cls._register(FileTypeConfig(
            category=FileCategory.JSON,
            extensions=[".json", ".jsonc", ".json5"],
            token_estimate=400,
            priority=5,  # Low priority - often detected by path patterns first
            best_practices=BestPractices(
                focus_areas=[
                    "Schema compliance",
                    "Structure consistency",
                    "Data validation"
                ],
                security_checks=[
                    "Hardcoded secrets",
                    "Excessive data exposure",
                    "Missing validation",
                    "Sensitive PII data"
                ],
                common_issues=[
                    "Trailing commas",
                    "Duplicate keys",
                    "Invalid escape sequences",
                    "Deep nesting",
                    "Missing required fields"
                ],
                style_guidelines=[
                    "Consistent indentation",
                    "Sorted keys where appropriate",
                    "Meaningful key names"
                ],
                performance_tips=[
                    "Minimize file size",
                    "Avoid deep nesting",
                    "Split large files"
                ]
            )
        ))

        # YAML
        cls._register(FileTypeConfig(
            category=FileCategory.YAML,
            extensions=[".yaml", ".yml"],
            token_estimate=400,
            priority=1,  # Lowest priority - specific YAML types detected first
            best_practices=BestPractices(
                focus_areas=[
                    "Structure consistency",
                    "Schema validation",
                    "Environment separation"
                ],
                security_checks=[
                    "Hardcoded secrets",
                    "Exposed credentials",
                    "Insecure defaults",
                    "Missing encryption references"
                ],
                common_issues=[
                    "Inconsistent indentation",
                    "Missing anchors/aliases for repetition",
                    "Type coercion issues (yes/no, on/off)",
                    "Missing required fields"
                ],
                style_guidelines=[
                    "Consistent indentation (2 spaces)",
                    "Use explicit types",
                    "Document with comments",
                    "Validate against schemas"
                ],
                performance_tips=[
                    "Use anchors for repetition",
                    "Minimize file size"
                ]
            )
        ))

        # TOML
        cls._register(FileTypeConfig(
            category=FileCategory.TOML,
            extensions=[".toml"],
            token_estimate=300,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Section organization",
                    "Type correctness",
                    "Key naming"
                ],
                security_checks=[
                    "Hardcoded secrets",
                    "Sensitive data exposure"
                ],
                common_issues=[
                    "Incorrect table nesting",
                    "Array vs inline array confusion",
                    "String quoting issues"
                ],
                style_guidelines=[
                    "Consistent formatting",
                    "Logical section grouping",
                    "Comments for complex values"
                ],
                performance_tips=[]
            )
        ))

        # XML
        cls._register(FileTypeConfig(
            category=FileCategory.XML,
            extensions=[".xml", ".xsl", ".xslt", ".xsd", ".wsdl"],
            token_estimate=400,
            priority=5,
            best_practices=BestPractices(
                focus_areas=[
                    "Schema validation",
                    "Namespace management",
                    "Structure consistency"
                ],
                security_checks=[
                    "XXE (XML External Entity) attacks",
                    "Billion laughs attack (DoS)",
                    "XPath injection",
                    "Hardcoded credentials"
                ],
                common_issues=[
                    "Missing XML declaration",
                    "Encoding issues",
                    "Invalid characters",
                    "Schema violations",
                    "Namespace conflicts"
                ],
                style_guidelines=[
                    "Consistent indentation",
                    "Meaningful element names",
                    "Proper namespace usage"
                ],
                performance_tips=[
                    "Minimize file size",
                    "Avoid excessive nesting"
                ]
            )
        ))

        # Environment files
        cls._register(FileTypeConfig(
            category=FileCategory.ENV,
            extensions=[".env", ".env.local", ".env.development", ".env.production",
                       ".env.test", ".env.example", ".env.sample"],
            path_patterns=[r".*\.env(\..+)?$"],
            token_estimate=150,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Variable organization",
                    "Documentation",
                    "Environment separation"
                ],
                security_checks=[
                    "Actual secrets in committed files",
                    "Missing .gitignore entry",
                    "Hardcoded production values",
                    "API keys and passwords",
                    "Database connection strings"
                ],
                common_issues=[
                    "Missing example file",
                    "Inconsistent naming",
                    "Missing required variables",
                    "Whitespace in values"
                ],
                style_guidelines=[
                    "UPPER_CASE variable names",
                    "Group related variables",
                    "Comment documentation"
                ],
                performance_tips=[]
            )
        ))

    @classmethod
    def _register_web_development(cls) -> None:
        """Register web development file types."""

        # HTML
        cls._register(FileTypeConfig(
            category=FileCategory.HTML,
            extensions=[".html", ".htm", ".xhtml"],
            token_estimate=350,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Semantic HTML",
                    "Accessibility (a11y)",
                    "SEO considerations",
                    "Performance"
                ],
                security_checks=[
                    "XSS vulnerabilities",
                    "Inline JavaScript risks",
                    "Clickjacking (missing X-Frame-Options)",
                    "Mixed content issues",
                    "Insecure form actions"
                ],
                common_issues=[
                    "Missing alt attributes",
                    "Missing lang attribute",
                    "Improper heading hierarchy",
                    "Missing viewport meta",
                    "Invalid nesting"
                ],
                style_guidelines=[
                    "Semantic elements",
                    "Consistent indentation",
                    "Lowercase tags",
                    "Quoted attributes"
                ],
                performance_tips=[
                    "Defer/async scripts",
                    "Lazy loading images",
                    "Critical CSS inlining",
                    "Minimize DOM depth"
                ]
            )
        ))

        # CSS
        cls._register(FileTypeConfig(
            category=FileCategory.CSS,
            extensions=[".css"],
            token_estimate=300,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Selector efficiency",
                    "Maintainability",
                    "Browser compatibility",
                    "Responsive design"
                ],
                security_checks=[
                    "CSS injection vulnerabilities",
                    "Data exfiltration via CSS",
                    "External resource loading"
                ],
                common_issues=[
                    "Overly specific selectors",
                    "!important overuse",
                    "Unused CSS",
                    "Vendor prefix issues",
                    "Magic numbers"
                ],
                style_guidelines=[
                    "Consistent naming (BEM, etc.)",
                    "Logical property order",
                    "CSS variables for theming",
                    "Mobile-first approach"
                ],
                performance_tips=[
                    "Minimize specificity",
                    "Avoid expensive selectors",
                    "Use CSS containment",
                    "Reduce reflows/repaints"
                ]
            )
        ))

        # SCSS/SASS
        cls._register(FileTypeConfig(
            category=FileCategory.SCSS,
            extensions=[".scss", ".sass"],
            token_estimate=350,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Variable organization",
                    "Mixin usage",
                    "Nesting depth",
                    "Module system"
                ],
                security_checks=[
                    "External resource URLs",
                    "Interpolation safety"
                ],
                common_issues=[
                    "Deep nesting (>3 levels)",
                    "Mixin overuse",
                    "Extend misuse",
                    "Missing variables",
                    "Circular imports"
                ],
                style_guidelines=[
                    "7-1 architecture",
                    "Variable naming",
                    "Partial organization",
                    "Comment documentation"
                ],
                performance_tips=[
                    "Minimize nesting",
                    "Use @use over @import",
                    "Placeholder selectors"
                ]
            )
        ))

        # Vue
        cls._register(FileTypeConfig(
            category=FileCategory.VUE,
            extensions=[".vue"],
            token_estimate=400,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Composition API patterns",
                    "Component organization",
                    "State management",
                    "TypeScript integration"
                ],
                security_checks=[
                    "XSS via v-html",
                    "Prop validation",
                    "URL sanitization",
                    "Event handler injection"
                ],
                common_issues=[
                    "Mutating props",
                    "Missing v-key",
                    "Watchers for computed",
                    "Reactive gotchas",
                    "Memory leaks"
                ],
                style_guidelines=[
                    "Vue style guide",
                    "Component naming",
                    "SFC structure",
                    "Script setup"
                ],
                performance_tips=[
                    "Lazy loading routes",
                    "v-once for static content",
                    "Computed caching",
                    "Virtual scrolling"
                ]
            )
        ))

        # JSX
        cls._register(FileTypeConfig(
            category=FileCategory.JSX,
            extensions=[".jsx"],
            token_estimate=350,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Component patterns",
                    "Props management",
                    "State handling",
                    "Hooks usage"
                ],
                security_checks=[
                    "XSS via dangerouslySetInnerHTML",
                    "Unescaped user input",
                    "URL sanitization",
                    "Event handler security"
                ],
                common_issues=[
                    "Missing keys in lists",
                    "Direct state mutation",
                    "Unnecessary renders",
                    "Memory leaks in effects",
                    "Prop drilling"
                ],
                style_guidelines=[
                    "Component naming",
                    "File organization",
                    "Props destructuring",
                    "Hook rules"
                ],
                performance_tips=[
                    "useMemo/useCallback",
                    "React.memo",
                    "Code splitting",
                    "Virtualization"
                ]
            )
        ))

        # TSX
        cls._register(FileTypeConfig(
            category=FileCategory.TSX,
            extensions=[".tsx"],
            token_estimate=400,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "TypeScript with React",
                    "Type-safe props",
                    "Generic components",
                    "Type inference"
                ],
                security_checks=[
                    "XSS via dangerouslySetInnerHTML",
                    "Type assertion abuse",
                    "Any type usage",
                    "URL sanitization"
                ],
                common_issues=[
                    "Type assertion overuse",
                    "Any type leakage",
                    "Missing prop types",
                    "Event handler typing",
                    "Generic constraints"
                ],
                style_guidelines=[
                    "Interface vs type",
                    "FC vs function syntax",
                    "Props interface naming",
                    "Strict mode"
                ],
                performance_tips=[
                    "Proper memoization",
                    "Type-safe context",
                    "Generic optimization"
                ]
            )
        ))

    @classmethod
    def _register_data_and_query(cls) -> None:
        """Register data and query language types."""

        # SQL
        cls._register(FileTypeConfig(
            category=FileCategory.SQL,
            extensions=[".sql", ".mysql", ".pgsql", ".plsql"],
            token_estimate=350,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Query optimization",
                    "Index usage",
                    "Transaction management",
                    "Migration safety"
                ],
                security_checks=[
                    "SQL injection patterns",
                    "Excessive privileges",
                    "Missing parameterization",
                    "Sensitive data exposure",
                    "Missing row-level security"
                ],
                common_issues=[
                    "SELECT * usage",
                    "N+1 query patterns",
                    "Missing indexes",
                    "Cartesian products",
                    "Implicit type conversions",
                    "Non-sargable queries"
                ],
                style_guidelines=[
                    "Uppercase keywords",
                    "Consistent aliasing",
                    "Join clarity",
                    "Comment documentation"
                ],
                performance_tips=[
                    "Proper indexing strategy",
                    "Query plan analysis",
                    "Batch operations",
                    "Connection pooling"
                ]
            )
        ))

        # GraphQL
        cls._register(FileTypeConfig(
            category=FileCategory.GRAPHQL,
            extensions=[".graphql", ".gql"],
            token_estimate=300,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Schema design",
                    "Query complexity",
                    "Type safety",
                    "Federation patterns"
                ],
                security_checks=[
                    "Query depth limits",
                    "Introspection exposure",
                    "Rate limiting",
                    "Authorization bypass",
                    "Field-level security"
                ],
                common_issues=[
                    "Over-fetching",
                    "N+1 queries",
                    "Circular references",
                    "Missing nullability",
                    "Enum misuse"
                ],
                style_guidelines=[
                    "Naming conventions",
                    "Description fields",
                    "Input types",
                    "Schema organization"
                ],
                performance_tips=[
                    "DataLoader for batching",
                    "Pagination patterns",
                    "Caching strategies"
                ]
            )
        ))

        # Prisma
        cls._register(FileTypeConfig(
            category=FileCategory.PRISMA,
            extensions=[".prisma"],
            token_estimate=300,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Schema modeling",
                    "Relations",
                    "Migration management",
                    "Type generation"
                ],
                security_checks=[
                    "Sensitive field exposure",
                    "Missing indexes",
                    "Cascade delete risks"
                ],
                common_issues=[
                    "N+1 queries",
                    "Missing indexes",
                    "Inefficient relations",
                    "Migration conflicts"
                ],
                style_guidelines=[
                    "Model naming",
                    "Field ordering",
                    "Relation naming"
                ],
                performance_tips=[
                    "Index usage",
                    "Relation loading",
                    "Batch operations"
                ]
            )
        ))

    @classmethod
    def _register_shell_and_scripts(cls) -> None:
        """Register shell and script types."""

        # Bash
        cls._register(FileTypeConfig(
            category=FileCategory.BASH,
            extensions=[".sh", ".bash", ".bashrc", ".bash_profile"],
            path_patterns=[r".*\.sh$", r".*bash.*"],
            token_estimate=300,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Error handling",
                    "Portability",
                    "Variable quoting",
                    "Exit codes"
                ],
                security_checks=[
                    "Command injection",
                    "Unquoted variables",
                    "Unsafe eval usage",
                    "World-writable scripts",
                    "Missing input validation",
                    "Insecure temp files (/tmp races)",
                    "Privilege escalation"
                ],
                common_issues=[
                    "Missing set -euo pipefail",
                    "Unquoted variables",
                    "Missing shellcheck directives",
                    "Hardcoded paths",
                    "Missing error handling",
                    "POSIX compatibility"
                ],
                style_guidelines=[
                    "ShellCheck compliance",
                    "Consistent quoting",
                    "Function usage",
                    "Comment documentation"
                ],
                performance_tips=[
                    "Avoid subshells where possible",
                    "Use built-ins over external commands",
                    "Proper use of arrays",
                    "Here-docs for multi-line"
                ]
            )
        ))

        # PowerShell
        cls._register(FileTypeConfig(
            category=FileCategory.POWERSHELL,
            extensions=[".ps1", ".psm1", ".psd1"],
            token_estimate=350,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Error handling",
                    "Module structure",
                    "Pipeline usage",
                    "Parameter validation"
                ],
                security_checks=[
                    "Command injection",
                    "Invoke-Expression with user input",
                    "Credential handling",
                    "Execution policy bypass",
                    "Unsigned scripts"
                ],
                common_issues=[
                    "Missing error handling",
                    "Ignoring $ErrorActionPreference",
                    "Write-Host misuse",
                    "Pipeline inefficiency",
                    "Missing parameter validation"
                ],
                style_guidelines=[
                    "Verb-Noun naming",
                    "Comment-based help",
                    "PascalCase conventions",
                    "Module manifest"
                ],
                performance_tips=[
                    "Pipeline streaming",
                    "Avoid Format-* in pipelines",
                    ".NET methods for performance",
                    "Background jobs"
                ]
            )
        ))

    @classmethod
    def _register_documentation(cls) -> None:
        """Register documentation file types."""

        # Markdown
        cls._register(FileTypeConfig(
            category=FileCategory.MARKDOWN,
            extensions=[".md", ".markdown", ".mdown", ".mkd"],
            token_estimate=300,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Structure clarity",
                    "Link validity",
                    "Image alt text",
                    "Code block formatting"
                ],
                security_checks=[
                    "Embedded JavaScript (XSS)",
                    "Malicious links",
                    "Sensitive data exposure",
                    "Data URIs"
                ],
                common_issues=[
                    "Broken links",
                    "Inconsistent heading levels",
                    "Missing alt text",
                    "Trailing whitespace",
                    "Inconsistent formatting"
                ],
                style_guidelines=[
                    "ATX-style headings",
                    "Consistent list markers",
                    "Fenced code blocks with language",
                    "One sentence per line"
                ],
                performance_tips=[]
            )
        ))

    @classmethod
    def _register_build_systems(cls) -> None:
        """Register build system file types."""

        # Makefile
        cls._register(FileTypeConfig(
            category=FileCategory.MAKEFILE,
            extensions=["Makefile", ".mk", "makefile", "GNUmakefile"],
            path_patterns=[r".*[Mm]akefile.*", r".*\.mk$"],
            token_estimate=250,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Target organization",
                    "Variable usage",
                    "Dependency tracking",
                    "Portability"
                ],
                security_checks=[
                    "Command injection in recipes",
                    "Untrusted variable expansion",
                    "Shell escaping issues"
                ],
                common_issues=[
                    "Missing .PHONY declarations",
                    "Hardcoded paths",
                    "Missing dependencies",
                    "Tab vs space issues",
                    "Silent failures"
                ],
                style_guidelines=[
                    "Consistent variable naming",
                    "Comment documentation",
                    "Logical target grouping"
                ],
                performance_tips=[
                    "Parallel execution (-j)",
                    "Proper dependencies",
                    "Pattern rules"
                ]
            )
        ))

        # CMake
        cls._register(FileTypeConfig(
            category=FileCategory.CMAKE,
            extensions=[".cmake"],
            path_patterns=[r".*CMakeLists\.txt$"],
            token_estimate=300,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Modern CMake practices",
                    "Target-based approach",
                    "Find modules",
                    "Generator expressions"
                ],
                security_checks=[
                    "Command injection",
                    "Untrusted input in commands"
                ],
                common_issues=[
                    "Global vs target properties",
                    "Deprecated commands",
                    "Generator expression errors",
                    "Missing dependencies",
                    "Hardcoded paths"
                ],
                style_guidelines=[
                    "lowercase commands",
                    "Target-centric approach",
                    "Comment documentation"
                ],
                performance_tips=[
                    "Precompiled headers",
                    "Unity builds",
                    "Proper dependencies"
                ]
            )
        ))

        # Gradle
        cls._register(FileTypeConfig(
            category=FileCategory.GRADLE,
            extensions=[".gradle", ".gradle.kts"],
            token_estimate=350,
            priority=10,
            best_practices=BestPractices(
                focus_areas=[
                    "Build configuration",
                    "Dependency management",
                    "Task organization",
                    "Plugin usage"
                ],
                security_checks=[
                    "Insecure repositories",
                    "Vulnerable dependencies",
                    "Credential exposure"
                ],
                common_issues=[
                    "Dynamic versions",
                    "Configuration vs implementation",
                    "Task ordering issues",
                    "Build cache misses"
                ],
                style_guidelines=[
                    "Kotlin DSL preference",
                    "Consistent formatting",
                    "Plugin version management"
                ],
                performance_tips=[
                    "Build cache",
                    "Parallel execution",
                    "Incremental builds",
                    "Configuration cache"
                ]
            )
        ))

        # Maven
        cls._register(FileTypeConfig(
            category=FileCategory.MAVEN,
            extensions=[],
            path_patterns=[r".*pom\.xml$"],
            token_estimate=400,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "POM structure",
                    "Dependency management",
                    "Plugin configuration",
                    "Multi-module projects"
                ],
                security_checks=[
                    "Vulnerable dependencies",
                    "Insecure repositories",
                    "Credential exposure in settings"
                ],
                common_issues=[
                    "Missing dependency versions",
                    "Plugin version drift",
                    "Scope misuse",
                    "Circular dependencies"
                ],
                style_guidelines=[
                    "Element ordering",
                    "Property usage",
                    "Parent POM organization"
                ],
                performance_tips=[
                    "Dependency convergence",
                    "Parallel builds",
                    "Incremental builds"
                ]
            )
        ))

    @classmethod
    def _register_package_management(cls) -> None:
        """Register package management file types."""

        # NPM package.json
        cls._register(FileTypeConfig(
            category=FileCategory.NPM_PACKAGE,
            extensions=[],
            path_patterns=[r".*package\.json$"],
            token_estimate=300,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Dependency management",
                    "Scripts organization",
                    "Version constraints",
                    "Package metadata"
                ],
                security_checks=[
                    "Known vulnerable dependencies",
                    "Overly permissive version ranges",
                    "Malicious postinstall scripts",
                    "Typosquatting packages"
                ],
                common_issues=[
                    "Floating versions (^, ~)",
                    "Missing peer dependencies",
                    "Dev vs production dependencies",
                    "Missing lockfile"
                ],
                style_guidelines=[
                    "Sorted keys",
                    "Consistent versioning",
                    "Complete metadata"
                ],
                performance_tips=[
                    "Production dependencies only",
                    "Optional dependencies",
                    "Workspaces for monorepos"
                ]
            )
        ))

        # Python requirements.txt
        cls._register(FileTypeConfig(
            category=FileCategory.REQUIREMENTS,
            extensions=[".txt"],
            path_patterns=[
                r".*requirements.*\.txt$",
                r".*constraints.*\.txt$",
            ],
            token_estimate=150,
            priority=90,
            best_practices=BestPractices(
                focus_areas=[
                    "Version pinning",
                    "Dependency organization",
                    "Environment separation"
                ],
                security_checks=[
                    "Known vulnerable packages",
                    "Unpinned versions",
                    "Insecure package sources",
                    "Typosquatting packages"
                ],
                common_issues=[
                    "Missing version pins",
                    "Incompatible versions",
                    "Missing hashes",
                    "Outdated packages"
                ],
                style_guidelines=[
                    "Alphabetical sorting",
                    "Comment organization",
                    "Version specifiers"
                ],
                performance_tips=[
                    "Minimal dependencies",
                    "Hash checking"
                ]
            )
        ))

        # Go modules
        cls._register(FileTypeConfig(
            category=FileCategory.GO_MOD,
            extensions=[],
            path_patterns=[r".*go\.mod$", r".*go\.sum$"],
            token_estimate=200,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Module versioning",
                    "Dependency management",
                    "Replace directives"
                ],
                security_checks=[
                    "Vulnerable dependencies",
                    "Checksum mismatches",
                    "Replaced with insecure sources"
                ],
                common_issues=[
                    "Pseudo-version usage",
                    "Missing go.sum entries",
                    "Version conflicts",
                    "Indirect dependency issues"
                ],
                style_guidelines=[
                    "Minimal go directive",
                    "Clean replace directives"
                ],
                performance_tips=[
                    "Vendoring for CI",
                    "Module proxy"
                ]
            )
        ))

        # NuGet / .NET Project Files
        cls._register(FileTypeConfig(
            category=FileCategory.NUGET,
            extensions=[".csproj", ".vbproj", ".fsproj", ".sln", ".props", ".targets"],
            path_patterns=[
                r".*\.csproj$",
                r".*\.vbproj$",
                r".*\.fsproj$",
                r".*\.sln$",
                r".*nuget\.config$",
                r".*packages\.config$",
                r".*Directory\.Build\.props$",
                r".*Directory\.Build\.targets$",
            ],
            token_estimate=300,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Package versioning",
                    "Project SDK usage",
                    "Central package management",
                    "Build configuration"
                ],
                security_checks=[
                    "Vulnerable NuGet packages",
                    "Untrusted package sources",
                    "Package signature verification",
                    "Hardcoded credentials in nuget.config"
                ],
                common_issues=[
                    "Floating package versions",
                    "Deprecated packages",
                    "Package version conflicts",
                    "Missing package restore",
                    "Inconsistent target frameworks"
                ],
                style_guidelines=[
                    "SDK-style project format",
                    "Central package management",
                    "Consistent property groups",
                    "Explicit package versions"
                ],
                performance_tips=[
                    "Enable package caching",
                    "Use package lock files",
                    "Optimize restore performance"
                ]
            )
        ))

        # Poetry (Python)
        cls._register(FileTypeConfig(
            category=FileCategory.POETRY,
            extensions=[],
            path_patterns=[r".*pyproject\.toml$", r".*poetry\.lock$"],
            token_estimate=300,
            priority=95,
            best_practices=BestPractices(
                focus_areas=[
                    "Dependency groups",
                    "Version constraints",
                    "Build system"
                ],
                security_checks=[
                    "Vulnerable dependencies",
                    "Missing lockfile",
                    "Insecure sources"
                ],
                common_issues=[
                    "Dependency conflicts",
                    "Missing optional deps",
                    "Script definitions"
                ],
                style_guidelines=[
                    "Group organization",
                    "Consistent formatting"
                ],
                performance_tips=[
                    "Parallel installation",
                    "Cache optimization"
                ]
            )
        ))

    @classmethod
    def _register_testing(cls) -> None:
        """Register testing file types."""

        # Jest config
        cls._register(FileTypeConfig(
            category=FileCategory.JEST,
            extensions=[],
            path_patterns=[r".*jest\.config\.(js|ts|json)$"],
            token_estimate=200,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Test configuration",
                    "Coverage settings",
                    "Mock setup"
                ],
                security_checks=[
                    "Test credential exposure",
                    "Unsafe mocking"
                ],
                common_issues=[
                    "Coverage thresholds",
                    "Transform configuration",
                    "Module mapping"
                ],
                style_guidelines=[
                    "TypeScript for type safety",
                    "Organized presets"
                ],
                performance_tips=[
                    "Parallel execution",
                    "Selective testing"
                ]
            )
        ))

    @classmethod
    def _register_security_and_compliance(cls) -> None:
        """Register security and compliance file types."""

        # Gitignore
        cls._register(FileTypeConfig(
            category=FileCategory.GITIGNORE,
            extensions=[".gitignore"],
            token_estimate=100,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Pattern organization",
                    "Completeness",
                    "Repository hygiene"
                ],
                security_checks=[
                    "Missing sensitive file patterns",
                    "Secret files not ignored",
                    "Environment files not ignored"
                ],
                common_issues=[
                    "Over-ignoring",
                    "Under-ignoring",
                    "Platform-specific issues",
                    "Negation pattern errors"
                ],
                style_guidelines=[
                    "Section organization",
                    "Comments for clarity"
                ],
                performance_tips=[]
            )
        ))

        # Dockerignore
        cls._register(FileTypeConfig(
            category=FileCategory.DOCKERIGNORE,
            extensions=[".dockerignore"],
            token_estimate=100,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Build context optimization",
                    "Security files exclusion"
                ],
                security_checks=[
                    "Secrets not ignored",
                    "Git directory not ignored",
                    "Environment files included"
                ],
                common_issues=[
                    "Missing common patterns",
                    "Over-inclusive patterns",
                    "Large file inclusion"
                ],
                style_guidelines=[
                    "Organized sections",
                    "Comments for clarity"
                ],
                performance_tips=[
                    "Minimize build context",
                    "Exclude test files"
                ]
            )
        ))

        # CODEOWNERS
        cls._register(FileTypeConfig(
            category=FileCategory.CODEOWNERS,
            extensions=["CODEOWNERS"],
            path_patterns=[r".*CODEOWNERS$"],
            token_estimate=100,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Ownership clarity",
                    "Pattern accuracy",
                    "Team coverage"
                ],
                security_checks=[
                    "Sensitive paths unowned",
                    "Security-critical file coverage"
                ],
                common_issues=[
                    "Pattern conflicts",
                    "Missing teams",
                    "Stale owners"
                ],
                style_guidelines=[
                    "Alphabetical organization",
                    "Comment sections"
                ],
                performance_tips=[]
            )
        ))

        # ESLint config
        cls._register(FileTypeConfig(
            category=FileCategory.ESLINT,
            extensions=[".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml"],
            path_patterns=[r".*\.eslintrc.*", r".*eslint\.config\..*"],
            token_estimate=200,
            priority=100,
            best_practices=BestPractices(
                focus_areas=[
                    "Rule configuration",
                    "Plugin management",
                    "Override patterns"
                ],
                security_checks=[
                    "Disabled security rules",
                    "Unsafe rule configurations"
                ],
                common_issues=[
                    "Conflicting rules",
                    "Missing plugins",
                    "Over-configuration"
                ],
                style_guidelines=[
                    "Extends vs rules",
                    "Organized overrides"
                ],
                performance_tips=[
                    "Cache usage",
                    "Ignore patterns"
                ]
            )
        ))

    @classmethod
    def _register_generic(cls) -> None:
        """Register generic fallback configuration."""
        cls._register(FileTypeConfig(
            category=FileCategory.GENERIC,
            extensions=[],  # Matches everything not matched elsewhere
            token_estimate=350,
            priority=-1,  # Lowest priority
            best_practices=BestPractices(
                focus_areas=[
                    "Code clarity",
                    "Error handling",
                    "Documentation"
                ],
                security_checks=[
                    "Hardcoded secrets or credentials",
                    "Sensitive data exposure",
                    "Input validation",
                    "Error message information leakage"
                ],
                common_issues=[
                    "Missing error handling",
                    "Code duplication",
                    "Unclear naming",
                    "Missing documentation",
                    "Dead code"
                ],
                style_guidelines=[
                    "Consistent formatting",
                    "Clear naming conventions",
                    "Appropriate comments"
                ],
                performance_tips=[
                    "Efficient algorithms",
                    "Resource management"
                ]
            )
        ))

    # ==========================================================================
    # PUBLIC API
    # ==========================================================================

    # Maximum path length to prevent ReDoS attacks (v2.6.1)
    MAX_PATH_LENGTH: int = 2000

    @classmethod
    @lru_cache(maxsize=1000)
    def classify(cls, file_path: str) -> FileCategory:
        """
        Classify a file path into a category.

        Uses priority-based matching:
        1. Path patterns (highest priority, context-aware)
        2. Extension mapping (with priority ordering)
        3. Generic fallback

        Args:
            file_path: Path to the file (relative or absolute)

        Returns:
            FileCategory for the file

        Note:
            v2.6.1: Added path length validation to prevent ReDoS attacks.
        """
        cls._initialize()

        # Defensive validation (v2.6.1)
        if not file_path or not isinstance(file_path, str):
            return FileCategory.GENERIC

        # Prevent ReDoS attacks with excessively long paths (v2.6.1)
        if len(file_path) > cls.MAX_PATH_LENGTH:
            logger.warning(
                "path_too_long_for_classification",
                path_length=len(file_path),
                max_length=cls.MAX_PATH_LENGTH
            )
            return FileCategory.GENERIC

        # Check for null bytes (security) (v2.6.1)
        if '\x00' in file_path:
            logger.warning("null_byte_in_path", path=file_path[:50])
            return FileCategory.GENERIC

        path_lower = file_path.lower()

        # First, try path pattern matching (highest priority for context)
        for config in sorted(cls._configs.values(), key=lambda c: c.priority, reverse=True):
            for pattern in config.path_patterns:
                try:
                    if re.match(pattern, path_lower):
                        logger.debug(
                            "file_classified_by_pattern",
                            path=file_path[:100],
                            category=config.category.value,
                            pattern=pattern[:50]
                        )
                        return config.category
                except re.error as e:
                    # Log and skip invalid patterns (v2.6.1)
                    logger.warning(
                        "invalid_regex_pattern",
                        pattern=pattern[:50],
                        error=str(e)
                    )
                    continue

        # Second, try extension mapping
        # Get file extension (handle files like "Dockerfile", "Makefile")
        if "." in file_path:
            ext = "." + file_path.rsplit(".", 1)[-1].lower()
        else:
            # For files without extension, use the filename
            ext = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path

        if ext in cls._extension_map:
            # Return the highest priority match
            config, _ = cls._extension_map[ext][0]
            logger.debug(
                "file_classified_by_extension",
                path=file_path[:100],
                category=config.category.value,
                extension=ext
            )
            return config.category

        # Fallback to generic
        logger.debug(
            "file_classified_as_generic",
            path=file_path[:100]
        )
        return FileCategory.GENERIC

    @classmethod
    def get_best_practices(cls, category: FileCategory) -> BestPractices:
        """
        Get best practices for a file category.

        Args:
            category: FileCategory to get practices for

        Returns:
            BestPractices object
        """
        cls._initialize()

        if category in cls._configs:
            return cls._configs[category].best_practices

        # Return generic practices
        return cls._configs.get(FileCategory.GENERIC, FileTypeConfig(
            category=FileCategory.GENERIC,
            extensions=[]
        )).best_practices

    @classmethod
    def get_token_estimate(cls, category: FileCategory) -> int:
        """
        Get token estimate for a file category.

        Args:
            category: FileCategory to get estimate for

        Returns:
            Estimated tokens per file
        """
        cls._initialize()

        if category in cls._configs:
            return cls._configs[category].token_estimate

        return 350  # Default estimate

    @classmethod
    def get_display_name(cls, category: FileCategory) -> str:
        """
        Get display name for a file category.

        Args:
            category: FileCategory to get name for

        Returns:
            Human-readable name
        """
        cls._initialize()

        if category in cls._configs:
            return cls._configs[category].display_name

        return category.value.replace("_", " ").title()

    @classmethod
    def get_all_categories(cls) -> List[FileCategory]:
        """
        Get list of all registered categories.

        Returns:
            List of FileCategory values
        """
        cls._initialize()
        return list(cls._configs.keys())

    @classmethod
    def format_best_practices_for_prompt(
        cls,
        categories: List[FileCategory],
        max_practices: int = 20
    ) -> str:
        """
        Format best practices for multiple categories into a prompt section.

        Args:
            categories: List of categories in the review
            max_practices: Maximum number of practice items to include

        Returns:
            Formatted prompt section
        """
        cls._initialize()

        sections = []
        total_items = 0

        for category in categories:
            if total_items >= max_practices:
                break

            practices = cls.get_best_practices(category)
            display_name = cls.get_display_name(category)

            section = practices.to_prompt_section(display_name)
            if section:
                # Count items in this section (rough estimate)
                item_count = section.count("\n- ")
                if total_items + item_count <= max_practices:
                    sections.append(section)
                    total_items += item_count

        return "\n".join(sections)


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

# Alias for backward compatibility with existing code
FileType = FileCategory
