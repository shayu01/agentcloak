"""Tests for core/seq.py — SeqCounter and RingBuffer."""

from browserctl.core.seq import RingBuffer, SeqCounter, SeqEvent


class TestSeqCounter:
    def test_starts_at_zero(self) -> None:
        c = SeqCounter()
        assert c.value == 0

    def test_starts_at_custom_value(self) -> None:
        c = SeqCounter(start=10)
        assert c.value == 10

    def test_increment_returns_new_value(self) -> None:
        c = SeqCounter()
        assert c.increment() == 1
        assert c.increment() == 2
        assert c.increment() == 3

    def test_value_reflects_increments(self) -> None:
        c = SeqCounter()
        c.increment()
        c.increment()
        assert c.value == 2

    def test_read_does_not_increment(self) -> None:
        c = SeqCounter()
        c.increment()
        _ = c.value
        _ = c.value
        assert c.value == 1

    def test_last_action_seq_starts_at_zero(self) -> None:
        c = SeqCounter()
        assert c.last_action_seq == 0

    def test_increment_action_updates_both_value_and_last_action_seq(self) -> None:
        c = SeqCounter()
        result = c.increment_action()
        assert result == 1
        assert c.value == 1
        assert c.last_action_seq == 1

    def test_increment_does_not_update_last_action_seq(self) -> None:
        c = SeqCounter()
        c.increment()
        c.increment()
        assert c.value == 2
        assert c.last_action_seq == 0

    def test_mixed_increment_and_increment_action(self) -> None:
        c = SeqCounter()
        c.increment()           # seq=1, non-action
        c.increment_action()    # seq=2, action
        c.increment()           # seq=3, non-action
        c.increment()           # seq=4, non-action
        c.increment_action()    # seq=5, action
        assert c.value == 5
        assert c.last_action_seq == 5

    def test_last_action_seq_tracks_most_recent_action(self) -> None:
        c = SeqCounter()
        c.increment_action()    # seq=1
        c.increment()           # seq=2
        c.increment()           # seq=3
        assert c.last_action_seq == 1
        c.increment_action()    # seq=4
        assert c.last_action_seq == 4


class TestRingBuffer:
    def test_empty_buffer(self) -> None:
        buf = RingBuffer(capacity=10)
        assert len(buf) == 0
        assert buf.all() == []

    def test_append_and_len(self) -> None:
        buf = RingBuffer(capacity=10)
        buf.append(SeqEvent(seq=1, kind="click"))
        buf.append(SeqEvent(seq=2, kind="fill"))
        assert len(buf) == 2

    def test_capacity_eviction(self) -> None:
        buf = RingBuffer(capacity=3)
        for i in range(1, 6):
            buf.append(SeqEvent(seq=i, kind="action"))
        assert len(buf) == 3
        seqs = [e.seq for e in buf.all()]
        assert seqs == [3, 4, 5]

    def test_since_filters_by_seq(self) -> None:
        buf = RingBuffer(capacity=100)
        for i in range(1, 6):
            buf.append(SeqEvent(seq=i, kind="action"))
        result = buf.since(3)
        assert [e.seq for e in result] == [4, 5]

    def test_since_zero_returns_all(self) -> None:
        buf = RingBuffer(capacity=100)
        buf.append(SeqEvent(seq=1, kind="nav"))
        buf.append(SeqEvent(seq=2, kind="click"))
        assert len(buf.since(0)) == 2

    def test_since_beyond_max_returns_empty(self) -> None:
        buf = RingBuffer(capacity=100)
        buf.append(SeqEvent(seq=1, kind="nav"))
        assert buf.since(999) == []

    def test_event_data_preserved(self) -> None:
        buf = RingBuffer(capacity=10)
        buf.append(SeqEvent(seq=1, kind="click", data={"index": 5}))
        events = buf.all()
        assert events[0].data == {"index": 5}
