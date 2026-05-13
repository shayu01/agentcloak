"""Tests for core/capture.py — CaptureStore and CaptureEntry."""

from agentcloak.core.capture import CaptureEntry, CaptureStore


def _make_entry(
    *,
    url: str = "https://api.example.com/v1/users",
    method: str = "GET",
    status: int = 200,
    resource_type: str = "xhr",
    content_type: str = "application/json",
    seq: int = 1,
) -> CaptureEntry:
    return CaptureEntry(
        seq=seq,
        timestamp="2026-05-07T12:00:00Z",
        method=method,
        url=url,
        status=status,
        resource_type=resource_type,
        content_type=content_type,
    )


class TestCaptureStore:
    def test_not_recording_by_default(self) -> None:
        store = CaptureStore()
        assert store.recording is False

    def test_add_while_not_recording(self) -> None:
        store = CaptureStore()
        added = store.add(_make_entry())
        assert added is False
        assert len(store) == 0

    def test_add_while_recording(self) -> None:
        store = CaptureStore()
        store.start()
        added = store.add(_make_entry())
        assert added is True
        assert len(store) == 1

    def test_start_stop(self) -> None:
        store = CaptureStore()
        store.start()
        assert store.recording is True
        store.stop()
        assert store.recording is False

    def test_filters_static_resources(self) -> None:
        store = CaptureStore()
        store.start()
        store.add(_make_entry(resource_type="stylesheet"))
        store.add(_make_entry(resource_type="image"))
        store.add(_make_entry(resource_type="font"))
        assert len(store) == 0

    def test_filters_static_extensions(self) -> None:
        store = CaptureStore()
        store.start()
        store.add(_make_entry(url="https://cdn.example.com/style.css"))
        store.add(_make_entry(url="https://cdn.example.com/logo.png"))
        store.add(_make_entry(url="https://cdn.example.com/font.woff2"))
        assert len(store) == 0

    def test_allows_api_requests(self) -> None:
        store = CaptureStore()
        store.start()
        store.add(_make_entry(url="https://api.example.com/v1/users"))
        store.add(_make_entry(url="https://api.example.com/v1/posts"))
        assert len(store) == 2

    def test_capacity_eviction(self) -> None:
        store = CaptureStore(capacity=3)
        store.start()
        for i in range(5):
            store.add(_make_entry(seq=i))
        assert len(store) == 3
        entries = store.entries()
        assert entries[0].seq == 2

    def test_clear(self) -> None:
        store = CaptureStore()
        store.start()
        store.add(_make_entry())
        store.clear()
        assert len(store) == 0

    def test_api_entries_filters_non_json(self) -> None:
        store = CaptureStore()
        store.start()
        store.add(_make_entry(content_type="application/json"))
        store.add(_make_entry(content_type="text/html"))
        store.add(_make_entry(content_type="text/plain"))
        api = store.api_entries()
        assert len(api) == 3

    def test_api_entries_filters_zero_status(self) -> None:
        store = CaptureStore()
        store.start()
        store.add(_make_entry(status=200))
        store.add(_make_entry(status=0))
        api = store.api_entries()
        assert len(api) == 1
