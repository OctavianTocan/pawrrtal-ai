from collections.abc import AsyncIterator
from typing import Any, ClassVar

class TextInput:
    text: str

    def __init__(self, *, text: str) -> None: ...

class ImageInput:
    url: str

    def __init__(self, *, url: str) -> None: ...

class LocalImageInput:
    path: str

    def __init__(self, *, path: str) -> None: ...

type InputItem = TextInput | ImageInput | LocalImageInput
type Input = InputItem | str
type RunInput = str | list[InputItem]

class AppServerConfig:
    codex_bin: object | None
    cwd: str | None
    env: dict[str, str] | None

    def __init__(
        self,
        *,
        codex_bin: object | None = ...,
        cwd: str | None = ...,
        env: dict[str, str] | None = ...,
    ) -> None: ...

class AsyncTurnHandle:
    async def stream(self) -> AsyncIterator[Any]: ...

class AsyncThread:
    id: str

    def __init__(self, codex: Any, thread_id: str) -> None: ...
    async def turn(self, run_input: RunInput, **kwargs: Any) -> AsyncTurnHandle: ...

class AsyncCodex:
    _client: Any

    def __init__(self, *, config: AppServerConfig | None = ...) -> None: ...
    async def _ensure_initialized(self) -> None: ...
    async def close(self) -> None: ...
    async def thread_start(
        self,
        *,
        model: str,
        cwd: str | None = ...,
        base_instructions: str | None = ...,
        developer_instructions: str | None = ...,
        approval_mode: Any = ...,
        sandbox: Any = ...,
    ) -> AsyncThread: ...
    async def thread_resume(self, thread_id: str) -> AsyncThread: ...

class Codex: ...
class Thread: ...
class TurnHandle: ...
class TurnResult: ...
class AppServerError(Exception): ...
class AppServerRpcError(Exception): ...
class TransportClosedError(Exception): ...
class RetryLimitExceededError(Exception): ...

class ApprovalMode:
    deny_all: ClassVar[Any]

class ReasoningSummary:
    root: Any

    @classmethod
    def model_validate(cls, value: Any) -> ReasoningSummary: ...
