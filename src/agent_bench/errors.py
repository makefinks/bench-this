"""Expected failure categories surfaced without raw tracebacks by the CLI."""


class BenchmarkError(Exception):
    """Base class for expected benchmark failures."""


class ConfigurationError(BenchmarkError):
    """A benchmark file is invalid or unsafe."""


class InfrastructureError(BenchmarkError):
    """Docker, setup, credentials, or another runner dependency failed."""


class IdentityMismatch(InfrastructureError):
    """A harness resolved a provider or model other than the pinned identity."""


class CommandTimeout(InfrastructureError):
    """A container exceeded its wall-clock limit."""
