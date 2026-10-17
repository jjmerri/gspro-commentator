from commentator.config import NotifyConfig
from commentator.health import Health
from commentator.notify import Notifier


def _notifier(**kw):
    sent = []
    n = Notifier(NotifyConfig(provider="ntfy", **kw), topic="test-topic",
                 send=lambda *a: sent.append(a))
    n._safe_send = lambda *a: n._send(*a)   # send inline, not on a thread
    return n, sent


def test_issues_raised_together_go_out_as_one_push_and_unchanged_ones_dont_repeat():
    n, sent = _notifier()
    h = Health()
    h.add_listener(n.on_change)
    n.cfg.gather_seconds = 60   # the test flushes by hand
    h.raise_issue("gspro.version", "warn", "GSPro was updated")
    h.raise_issue("round.tiles_absent", "fail", "no carry tile read")
    n.flush()
    assert len(sent) == 1
    title, body, priority, _ = sent[0]
    assert title == "Golf booth: 2 problems" and priority == "high"
    assert "FAIL: no carry tile read" in body and "WARN: GSPro was updated" in body
    # Cleared (a "resolved" push), then back with the same message: a flapping check buzzes once.
    h.clear("round.tiles_absent")
    n.flush()
    h.raise_issue("round.tiles_absent", "fail", "no carry tile read")
    n.flush()
    h.clear("round.tiles_absent")
    n.flush()
    assert [s[0] for s in sent] == ["Golf booth: 2 problems", "Golf booth: resolved"]
    # A changed message is news.
    h.raise_issue("round.tiles_absent", "fail", "no total length tile read")
    n.flush()
    assert sent[-1][0] == "Golf booth: 1 problem"


def test_a_push_says_resolved_only_for_what_was_pushed_and_respects_levels():
    n, sent = _notifier(levels=["fail"])
    n.cfg.gather_seconds = 60
    h = Health()
    h.add_listener(n.on_change)
    h.raise_issue("a", "warn", "just a warning")    # warn isn't in levels: nothing
    h.clear("a")
    n.flush()
    assert sent == []
    h.raise_issue("b", "fail", "broken")
    n.flush()
    h.clear("b")
    n.flush()
    assert [s[0] for s in sent] == ["Golf booth: 1 problem", "Golf booth: resolved"]


def test_no_topic_means_no_pushes():
    n = Notifier(NotifyConfig(provider="ntfy"), topic="")
    h = Health()
    n.attach(h)
    assert not n.enabled and not h._listeners
