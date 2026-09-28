class AgentVideoNoteError(Exception):
    """Base error for Agent-VideoNote."""


class ConfigurationError(AgentVideoNoteError):
    """Invalid or incomplete runtime configuration."""


class CapabilityError(AgentVideoNoteError):
    """A configured provider cannot satisfy a required capability."""


class TaskNotFoundError(AgentVideoNoteError):
    """Requested task does not exist."""


class InvalidTransitionError(AgentVideoNoteError):
    """Workflow state transition is not allowed."""


class ExternalToolError(AgentVideoNoteError):
    """An external executable failed or returned invalid output."""
