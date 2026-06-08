from typing import Any, ClassVar

class ReasoningEffort:
    minimal: ClassVar[ReasoningEffort]
    low: ClassVar[ReasoningEffort]
    medium: ClassVar[ReasoningEffort]
    high: ClassVar[ReasoningEffort]

class SandboxMode:
    read_only: ClassVar[SandboxMode]

class ReasoningSummary:
    root: Any

    @classmethod
    def model_validate(cls, value: Any) -> ReasoningSummary: ...
