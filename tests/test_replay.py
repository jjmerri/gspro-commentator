"""Replay a realistic GSPconnect stream through the real ConnectorLogSource and assert every shot
is detected exactly once and classified right, including through file rotation, the booth's most
failure-prone surface. The harness lives in tools/replay_connector.py; see it for the mechanics."""
import asyncio

import pytest

from tools.replay_connector import expect_putt, ground_truth, replay, synth_stream


@pytest.mark.parametrize("strand", [False, True])
def test_every_shot_survives_rotation(strand):
    # strand=True rotates the log the instant each shot is written: the one timing that can strand a
    # shot in a rotated-away file unread. Both modes must still surface every shot exactly once.
    lines = synth_stream()
    truth = ground_truth(lines)
    detected = asyncio.run(replay(lines, strand_shots=strand))
    nums = [e.shot.shot_number for e in detected]
    assert sorted(set(nums)) == sorted(truth), f"missed {sorted(set(truth) - set(nums))}"
    assert len(nums) == len(set(nums)), "a shot was emitted more than once"


def test_putts_are_classified_as_putts():
    # Real EYE XO2 putts send a sentinel VLA (99999) the parser blanks to None; the stream also has a
    # literal-0.0 putt. All must read as putts, else they run the ball-follow and get full-shot
    # commentary that lands on the next hole. Full shots must stay full shots.
    lines = synth_stream()
    detected = asyncio.run(replay(lines))
    truth = ground_truth(lines)
    for e in detected:
        want = expect_putt(truth[e.shot.shot_number])
        assert e.shot.is_putt == want, f"SN {e.shot.shot_number} is_putt={e.shot.is_putt}, want {want}"
    assert any(e.shot.is_putt for e in detected), "the stream must contain putts to be a real check"
