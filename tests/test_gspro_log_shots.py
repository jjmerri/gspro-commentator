import asyncio

from commentator.config import Config
from commentator.sources import build_source
from commentator.sources.gspro_log_shots import GsproLogShotSource, parse_launch, shot_from_launch

DRIVE = "LaunchExt Vars: sp 138.37, el 15.21, az -4.52, ts 1588.58, sa -15.74, cy 237.54, id 1467"
PUTT = "LaunchExt Vars: sp 13.12, el 0, az 4.41, ts 0, sa 45, cy 0, id 1475"


def test_full_shot_ball_data_from_the_log():
    shot = shot_from_launch(parse_launch(DRIVE))
    assert (shot.ball_speed, shot.vla, shot.hla, shot.total_spin, shot.spin_axis, shot.carry) == (
        138.37, 15.21, -4.52, 1588.58, -15.74, 237.54)
    assert shot.shot_number == 1467 and shot.units == "Yards"
    assert shot.club_speed is None and not shot.club_measured and not shot.is_putt


def test_putt_from_the_log():
    shot = shot_from_launch(parse_launch(PUTT))
    assert shot.ball_speed == 13.12 and shot.carry == 0.0 and shot.is_putt


def test_other_lines_are_not_shots():
    assert parse_launch(" * ------- Shot Fired! ------- *") is None
    assert parse_launch("LaunchExt - Regular Mode") is None
    assert parse_launch("LaunchExt Vars: el 12") is None


def test_source_yields_new_shots_only(tmp_path):
    log = tmp_path / "output_log.txt"
    log.write_text("old stuff\n" + DRIVE + "\n", encoding="utf-8")
    src = GsproLogShotSource(str(log), poll_seconds=0.01)

    async def first():
        it = src.events().__aiter__()
        task = asyncio.ensure_future(it.__anext__())
        await asyncio.sleep(0.05)   # primed at the end: the old drive is history
        with log.open("a", encoding="utf-8") as f:
            f.write(" * ------- Shot Fired! ------- *\n" + PUTT + "\nLaunchExt - Putting Mode\n")
        return await asyncio.wait_for(task, 2)

    ev = asyncio.run(first())
    assert ev.shot.shot_number == 1475 and ev.shot.is_putt


def test_connector_log_falls_back_to_the_gspro_log(tmp_path):
    cfg = Config()
    cfg.source.connector_log = str(tmp_path / "GSPC" / "ConnectDebug.txt")
    cfg.source.gspro_log = str(tmp_path / "output_log.txt")
    assert type(build_source(cfg)).__name__ == "GsproLogShotSource"
    (tmp_path / "GSPC").mkdir()
    (tmp_path / "GSPC" / "ConnectDebug.txt").write_text("")
    assert type(build_source(cfg)).__name__ == "ConnectorLogSource"
    cfg.source.type = "gspro_log"
    assert type(build_source(cfg)).__name__ == "GsproLogShotSource"
