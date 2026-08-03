"""Scripted stand-ins for the anthropic client, patched in at
app.modules.ai.client.get_client."""

from types import SimpleNamespace


def text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(block_id: str, name: str, input: dict):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=input)


def fake_response(*, stop_reason="end_turn", content=None, parsed_output=None):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content or [],
        parsed_output=parsed_output,
    )


class FakeStream:
    """Mimics client.messages.stream(...) context manager."""

    def __init__(self, events, final):
        self._events = events
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return self._final


def text_delta_event(text: str):
    return SimpleNamespace(
        type="content_block_delta", delta=SimpleNamespace(type="text_delta", text=text)
    )


def tool_start_event(name: str):
    return SimpleNamespace(
        type="content_block_start",
        content_block=SimpleNamespace(type="tool_use", name=name),
    )


class FakeMessages:
    def __init__(self):
        self.create_responses = []
        self.parse_responses = []
        self.stream_scripts = []  # list of (events, final_message)
        self.create_calls = []
        self.parse_calls = []
        self.stream_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.create_responses.pop(0)

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return self.parse_responses.pop(0)

    def stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        events, final = self.stream_scripts.pop(0)
        return FakeStream(events, final)


class FakeAnthropic:
    def __init__(self):
        self.messages = FakeMessages()
