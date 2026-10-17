import json
import time
from collections import defaultdict
from pathlib import Path

from .llm import LLMClient, LLMResult

# USD per million tokens: (input, output). Cache reads bill at 0.1x input, writes at 1.25x.
# Check current pricing before relying on these.
PRICES = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}


# Cloud TTS (gpt-4o-mini-tts) is billed by generated audio time; OpenAI's own estimate is about this.
# Check current pricing before relying on it.
TTS_USD_PER_MINUTE = 0.015


def audio_cost(seconds: float) -> float:
    """Estimated USD for `seconds` of synthesized cloud TTS audio."""
    return seconds / 60.0 * TTS_USD_PER_MINUTE


def audio_summary(stats: dict) -> str:
    """One-line session TTS tally: what was synthesized vs what actually aired, and the estimated $.
    The gap is the pre-voicing waste (branches voiced for every outcome, one of which airs)."""
    synth_s, spoken_s = stats.get("synth_seconds", 0.0), stats.get("spoken_seconds", 0.0)
    pct = (1 - spoken_s / synth_s) * 100 if synth_s else 0.0
    return (
        f"Audio this session: synthesized {stats.get('synth_clips', 0)} clips / "
        f"{stats.get('synth_chars', 0):,} chars / {synth_s / 60:.1f} min (est ${audio_cost(synth_s):.2f}); "
        f"spoken {stats.get('spoken_clips', 0)} clips / {spoken_s / 60:.1f} min (est ${audio_cost(spoken_s):.2f}); "
        f"{pct:.0f}% of synthesized audio pre-voiced but never aired"
    )


def estimate_cost(model: str, r: dict) -> float:
    price = next((p for prefix, p in PRICES.items() if model.startswith(prefix)), None)
    if not price:
        return 0.0
    inp, out = price
    return (
        (r.get("input_tokens") or 0) * inp
        + (r.get("cache_read_tokens") or 0) * inp * 0.1
        + (r.get("cache_write_tokens") or 0) * inp * 1.25
        + (r.get("output_tokens") or 0) * out
    ) / 1_000_000


class UsageLog:
    def __init__(self, log_dir: str) -> None:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        self.path = Path(log_dir) / "usage.jsonl"

    def record(self, kind: str, llm: LLMClient, result: LLMResult) -> None:
        row = {
            "ts": time.time(),
            "date": time.strftime("%Y-%m-%d"),
            "kind": kind,
            "provider": llm.provider,
            "model": llm.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cache_read_tokens": result.cache_read_tokens,
            "cache_write_tokens": result.cache_write_tokens,
            "latency_s": round(result.latency_seconds, 2),
        }
        row["est_cost_usd"] = round(estimate_cost(llm.model, row), 6) if llm.provider == "anthropic" else 0.0
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")


def summarize(log_dir: str, weeks: int = 12, as_model: str | None = None) -> str:
    """Per-night totals. `as_model` prices every call at that Claude model's rates,
    which turns a local night's token counts into a rough cloud estimate
    (tokenizers differ, so treat it as ballpark)."""
    path = Path(log_dir) / "usage.jsonl"
    if not path.exists():
        return f"No usage log at {path}"
    by_date: dict[str, dict] = defaultdict(lambda: {"calls": 0, "latency": 0.0, "cost": 0.0, "models": set()})
    for raw in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(raw)
        d = by_date[r["date"]]
        d["calls"] += 1
        d["latency"] += r.get("latency_s") or 0
        d["cost"] += estimate_cost(as_model, r) if as_model else (r.get("est_cost_usd") or 0)
        d["models"].add(f'{r["provider"]}:{r["model"]}')
    out = ["date        calls  avg_latency  est_cost  models"]
    for date, d in sorted(by_date.items()):
        out.append(
            f'{date}  {d["calls"]:>5}  {d["latency"] / d["calls"]:>9.2f}s  ${d["cost"]:>7.2f}  {", ".join(sorted(d["models"]))}'
        )
    last = by_date[max(by_date)]
    priced = f" priced as {as_model}" if as_model else ""
    out.append(f"\nLast night x {weeks} weeks{priced}: ${last['cost'] * weeks:.2f}")
    return "\n".join(out)
