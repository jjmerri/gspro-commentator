import asyncio
import logging
import time
from dataclasses import dataclass

from .config import Config
from .models import Line
from .tts import TTS, Audio

log = logging.getLogger(__name__)

WORDS_PER_SECOND = 2.7
# The audio device powers down when idle; the first clip after a gap loses its opening moments
# while it wakes (the opener, minutes into silence, was starting mid-word). Lead silence after a
# gap absorbs the wake-up instead of the speech.
_IDLE_GAP_SECONDS = 5.0
_WAKE_LEAD_SECONDS = 0.6
_last_play_end = 0.0
# Requests per line, all told (hedges and replacements for errored ones): caps a fast-failing error
# (bad key, outage) at a handful of calls.
_MAX_REQUESTS = 5


async def play(audio: Audio) -> None:
    import numpy as np
    import sounddevice as sd

    global _last_play_end
    lead = _WAKE_LEAD_SECONDS if time.monotonic() - _last_play_end > _IDLE_GAP_SECONDS else 0.0
    samples = audio.samples
    if lead:
        pad = np.zeros(int(audio.sample_rate * lead), dtype=samples.dtype)
        samples = np.concatenate([pad, samples])

    def _play() -> None:
        sd.play(samples, audio.sample_rate)
        sd.wait()

    await asyncio.to_thread(_play)
    _last_play_end = time.monotonic()


def _audio_seconds(audio: Audio | None) -> float:
    """Playback length of a synthesized clip, for the cost estimate (TTS is billed by audio time)."""
    if audio is None:
        return 0.0
    try:
        return len(audio.samples) / audio.sample_rate
    except Exception:
        return 0.0


def stop_playback() -> None:
    try:
        import sounddevice as sd

        sd.stop()
    except Exception:
        pass


@dataclass
class _Queued:
    """A live line waiting its turn. On a network voice its synth starts as soon as it's queued, so a
    stalled line doesn't hold up voicing the ones behind it; playback still goes in queue order."""

    gen: int
    line: Line
    deadline: float | None  # time.monotonic() by which it must be playing, or None
    exchange: int  # lines from one say() call: lose one and the replies after it go too
    task: asyncio.Task | None = None


class SpeechQueue:
    """Synthesizes the next line while the current one plays, so the booth doesn't pause between speakers."""

    def __init__(self, cfg: Config, tts: TTS, player=play, stopper=stop_playback) -> None:
        self.cfg = cfg
        self.tts = tts
        # Respells names for the voice (League.spoken); the engine sets it from the league file.
        self.spoken = lambda text: text
        self._play = player
        self._stop = stopper
        # A line past its deadline is dropped, never played late.
        self._text_q: asyncio.Queue[_Queued] = asyncio.Queue()
        self._audio_q: asyncio.Queue[tuple[int, Line, Audio | None, float | None]] = asyncio.Queue(maxsize=1)
        # The synth the loop is waiting on; interrupt() cancels it (queued ones are cancelled as they're
        # drained) so a stalled request can't hold up the line that superseded it.
        self._synth_task: asyncio.Task | None = None
        self._exchange = 0
        self._lost_exchange: int | None = None
        # Commentary off: nothing is voiced or played.
        self.muted = False
        # Lines accepted but not yet finished playing, including the ones mid-synthesis or mid-playback.
        self._pending = 0
        # Bumped by interrupt(); lines from an older generation are skipped wherever they are.
        self._generation = 0
        self._playing: asyncio.Task | None = None
        # The generation of the prepared sequence (wrap/closer) currently feeding the audio queue, or
        # None when none is. The synth loop and the feeder both park on the maxsize-1 audio queue and
        # would otherwise alternate, splicing a concurrent say() (a late reaction) into the middle of
        # the exchange; while a sequence owns this the synth loop drops its output instead of
        # competing. It's the owning generation, not a bool, so a plain interrupt (which bumps the
        # generation but not this) is still cleared by the feeder, and an overlapping sequence keeps
        # ownership until it finishes.
        self._sequencing: int | None = None
        # Per-session audio tally, for the cost estimate. "synth" counts every clip actually run
        # through TTS (including pre-voiced branches that never air); "spoken" counts only the clips
        # that reached the speakers. The gap is the pre-voicing waste. Non-blocking dict increments.
        self.audio_stats = {
            "synth_clips": 0, "synth_chars": 0, "synth_seconds": 0.0,
            "spoken_clips": 0, "spoken_chars": 0, "spoken_seconds": 0.0,
        }

    def _count_synth(self, text: str, audio: Audio | None) -> None:
        if audio is None:  # console/local-silent providers cost nothing to "synthesize"
            return
        self.audio_stats["synth_clips"] += 1
        self.audio_stats["synth_chars"] += len(text)
        self.audio_stats["synth_seconds"] += _audio_seconds(audio)

    def _count_spoken(self, text: str, audio: Audio | None) -> None:
        if audio is None:
            return
        self.audio_stats["spoken_clips"] += 1
        self.audio_stats["spoken_chars"] += len(text)
        self.audio_stats["spoken_seconds"] += _audio_seconds(audio)

    def say(self, lines: list[Line], interrupt: bool = False, deadline: float | None = None) -> None:
        """Queue lines to voice and play. `deadline` (a time.monotonic()) is when they stop being worth
        saying; each line is also dropped if its voice isn't ready within live_deadline_seconds."""
        if self.muted:
            return
        if interrupt:
            self.interrupt()
        else:
            # Commentary on a shot from two shots ago is worse than none.
            backlog = self._text_q.qsize() + self._audio_q.qsize()
            if backlog >= self.cfg.commentary.max_speech_backlog:
                log.info("Speech backlog %s; dropping %s queued lines", backlog, self._text_q.qsize())
                self._drain(self._text_q)
        self._exchange += 1
        eager = getattr(self.tts, "concurrent", False)  # a local CPU voice goes one line at a time
        for line in lines:
            item = _Queued(self._generation, line, deadline, self._exchange)
            if eager:
                self._start_synth(item)
            self._text_q.put_nowait(item)
            self._pending += 1

    def _start_synth(self, item: _Queued) -> None:
        # A live line waits at most live_deadline_seconds for its voice (or until its own deadline).
        until = time.monotonic() + self.cfg.tts.live_deadline_seconds
        if item.deadline is not None:
            until = min(until, item.deadline)
        item.task = asyncio.create_task(self._synthesize(item.line, until))

    def _voice_for(self, line: Line) -> tuple[str, str | None]:
        voices = self.cfg.tts.active_voices
        voice = voices.get(line.speaker) or next(iter(voices.values()))
        return voice, self.cfg.tts.active_instructions.get(line.speaker)

    async def _synthesize(self, line: Line, until: float | None = None) -> tuple[bool, Audio | None]:
        """Voice a line, returning (ok, audio). A cloud voice's requests either answer in a second or
        two or stall for 30 s+, so a request still unanswered after hedge_after_seconds gets a second
        one alongside it (the first isn't killed; a slow one that would have worked still can) and
        whichever answers first wins. It keeps hedging, at most two requests in flight, until `until`
        (a time.monotonic()), which defaults to prepare_deadline_seconds for a line voiced ahead."""
        voice, instructions = self._voice_for(line)
        text = self.spoken(line.text)
        if not getattr(self.tts, "remote", False):
            try:
                audio = await self.tts.synthesize(text, voice, instructions)
            except Exception as e:
                log.warning("TTS failed (%s: %s): %s", type(e).__name__, e, line.text)
                return False, None
            self._count_synth(line.text, audio)
            return True, audio

        cfg = self.cfg.tts
        started = time.monotonic()
        if until is None:
            until = started + cfg.prepare_deadline_seconds
        inflight: list[tuple[asyncio.Task, float]] = []  # (request, when it was sent), oldest first
        sent = 0

        def send() -> None:
            nonlocal sent
            sent += 1
            inflight.append((asyncio.create_task(self.tts.synthesize(text, voice, instructions)), time.monotonic()))

        try:
            while True:
                now = time.monotonic()
                if now >= until - 0.05:
                    break
                if not inflight:
                    if sent >= _MAX_REQUESTS:
                        break
                    send()  # the first request, or a replacement for one that errored
                can_hedge = sent < _MAX_REQUESTS
                tick = min(inflight[-1][1] + cfg.hedge_after_seconds, until) if can_hedge else until
                done, _ = await asyncio.wait([t for t, _ in inflight], timeout=max(tick - time.monotonic(), 0),
                                             return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    inflight = [(t, at) for t, at in inflight if t is not task]
                    if (err := task.exception()) is None:
                        audio = task.result()
                        if sent > 1:
                            log.info("TTS answered in %.1fs after %s requests: %s",
                                     time.monotonic() - started, sent, line.text)
                        self._count_synth(line.text, audio)
                        return True, audio
                    log.warning("TTS request failed (%s: %s): %s", type(err).__name__, err, line.text)
                if done or not can_hedge or time.monotonic() >= until - 0.05:
                    continue
                if len(inflight) >= 2:  # keep two in flight: drop the oldest, long since stalled
                    old, _ = inflight.pop(0)
                    old.cancel()
                log.info("TTS slow (%.1fs); hedging with another request: %s", time.monotonic() - started, line.text)
                send()
        finally:
            for task, _ in inflight:
                task.cancel()
        log.warning("TTS gave up after %.1fs (%s requests): %s", time.monotonic() - started, sent, line.text)
        return False, None

    async def prepare_exchange(self, lines: list[Line]) -> tuple[list[Line], list[Audio | None]]:
        """Voice a multi-line exchange ahead of time (a wrap, the closer): in parallel on a network
        voice, in order on a local one. It's cut at the first line that couldn't be voiced, since a
        reply to a line nobody hears makes no sense; empty when the first line failed."""
        if self.muted:
            return [], []
        if getattr(self.tts, "concurrent", False):
            results = await asyncio.gather(*(self._synthesize(l) for l in lines))
        else:
            results = [await self._synthesize(l) for l in lines]
        kept: list[Audio | None] = []
        for line, (ok, audio) in zip(lines, results):
            if not ok:
                log.info("TTS gave up preparing %r; cut the exchange to %s of %s lines", line.text, len(kept), len(lines))
                break
            kept.append(audio)
        return lines[:len(kept)], kept

    async def prepare(self, line: Line) -> Audio | None:
        """Voices a line now to play later (mid-flight calls are voiced before the swing)."""
        if self.muted:
            return None
        ok, audio = await self._synthesize(line)
        if not ok:
            log.info("TTS gave up preparing: %s", line.text)
        return audio

    def say_prepared(self, line: Line, audio: Audio | None) -> None:
        """Cuts off whatever is playing and plays already-voiced audio straight away."""
        if self.muted:
            return
        self.interrupt()
        self._audio_q.put_nowait((self._generation, line, audio, None))
        self._pending += 1

    def say_prepared_sequence(self, items: list[tuple[Line, Audio | None]]) -> None:
        """Play several already-voiced lines in order. Cuts off whatever's playing once, then feeds
        the clips to the play loop one at a time (the audio queue holds only one, so a background task
        awaits each put, like the synth loop does). A later interrupt supersedes the rest of the
        sequence. Looping say_prepared instead would interrupt between every line and drop all but the
        last, so the whole exchange has to go through here."""
        if not items or self.muted:
            return
        self.interrupt()
        gen = self._generation
        self._sequencing = gen
        self._pending += len(items)

        async def feed() -> None:
            try:
                for i, (line, audio) in enumerate(items):
                    if gen != self._generation:   # a newer interrupt superseded this sequence
                        self._pending -= (len(items) - i)   # the rest never reach the play loop
                        return
                    await self._audio_q.put((gen, line, audio, None))
            finally:
                # Release the synth loop, but only if we still own it (a newer sequence that took over
                # owns the token now and will clear it itself). A plain interrupt bumps the generation
                # without touching the token, so this still clears and the booth doesn't go silent.
                if self._sequencing == gen:
                    self._sequencing = None

        task = asyncio.create_task(feed())
        task.add_done_callback(lambda t: t.cancelled() or t.exception())

    def interrupt(self) -> None:
        """Cut off what's playing and discard everything queued or mid-synthesis."""
        self._generation += 1
        dropped = self._text_q.qsize() + self._audio_q.qsize()
        self._drain(self._text_q)
        self._drain(self._audio_q)
        cut = bool(self._playing and not self._playing.done())
        if dropped or cut:
            log.info("Interrupted: %s cut off, %s queued lines dropped", "a line" if cut else "nothing", dropped)
        if self._playing and not self._playing.done():
            self._stop()
            self._playing.cancel()
        if self._synth_task and not self._synth_task.done():
            self._synth_task.cancel()

    def _drain(self, q: asyncio.Queue) -> None:
        while not q.empty():
            item = q.get_nowait()
            if isinstance(item, _Queued) and item.task:
                item.task.cancel()
            self._pending -= 1

    def is_idle(self) -> bool:
        return self._pending == 0

    async def run(self) -> None:
        await asyncio.gather(self._synth_loop(), self._play_loop())

    async def _synth_loop(self) -> None:
        """Hands voiced lines to the play loop in queue order, waiting on each line's synth in turn."""
        while True:
            item = await self._text_q.get()
            if item.gen != self._generation or item.exchange == self._lost_exchange:
                if item.task:
                    item.task.cancel()
                self._pending -= 1
                continue
            if item.task is None:
                self._start_synth(item)
            self._synth_task = item.task
            try:
                ok, audio = await item.task
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
                ok, audio = False, None  # interrupt() superseded it mid-synthesis
            finally:
                self._synth_task = None
            late = ok and item.deadline is not None and time.monotonic() > item.deadline
            if not ok or late:
                if item.gen == self._generation:
                    if late:
                        log.info("Dropped a line voiced %.1fs past its deadline: %s",
                                 time.monotonic() - item.deadline, item.line.text)
                    else:
                        log.info("Dropped a line its voice wasn't ready for in time: %s", item.line.text)
                    self._lost_exchange = item.exchange  # its replies go too
                self._pending -= 1
                continue
            if item.gen != self._generation or self._sequencing is not None:
                # Interrupted while synthesizing, or a prepared wrap/closer is airing and this ordinary
                # line would splice into the middle of it; drop it rather than compete for the queue.
                self._pending -= 1
                continue
            await self._audio_q.put((item.gen, item.line, audio, item.deadline))

    async def _play_loop(self) -> None:
        while True:
            gen, line, audio, deadline = await self._audio_q.get()
            try:
                if gen != self._generation:
                    continue
                if deadline is not None and time.monotonic() > deadline:
                    log.info("Dropped a line that missed its moment by %.1fs: %s",
                             time.monotonic() - deadline, line.text)
                    continue
                name = self.cfg.personas[line.speaker].name if line.speaker in self.cfg.personas else line.speaker
                print(f"  [{name}] {line.text}", flush=True)
                log.info("Speaking [%s]: %s", name, line.text)
                if audio is not None:
                    self._count_spoken(line.text, audio)
                    self._playing = asyncio.create_task(self._play(audio))
                elif self.cfg.tts.console_simulate_duration:
                    self._playing = asyncio.create_task(asyncio.sleep(len(line.text.split()) / WORDS_PER_SECOND))
                else:
                    continue
                try:
                    await self._playing
                except asyncio.CancelledError:
                    # interrupt() cancelled the line; only a shutdown of this loop should propagate.
                    if asyncio.current_task().cancelling():
                        raise
                except Exception:
                    log.exception("Audio playback failed")
            finally:
                self._pending -= 1
