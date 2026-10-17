"""The league's week results and season standings, live from Squabbit's leaderboards.

Squabbit scores the league: each week's leaderboard has every team's net to par once they've posted.
A week's places come from those nets (ties share a place), and the season's points from the league's
points table (`points_table` in the history file): a tie splits the points of the places it covers, so
two teams tied for 1st each get the average of the 1st and 2nd place points. Checked against the 2025
season's spreadsheet: the same points on 106 of 108 team-weeks (the other two were a tie the
spreadsheet recorded that Squabbit's nets don't show).

A week counts toward the standings once it's final: every team has posted, or its deadline has passed.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any

from .league import League


@dataclass
class Entry:
    team: str            # the league file's team name (Squabbit's when it can't be matched)
    net: int | None      # net to par; None until the team posts


def place(net: int, nets: list[int]) -> tuple[int, bool]:
    """This net's place among `nets` (which include it): 1 + how many are better, and whether it's tied."""
    return 1 + sum(1 for n in nets if n < net), sum(1 for n in nets if n == net) > 1


def place_points(position: int, tied: int, table: list[float]) -> float:
    """Points for a place shared by `tied` teams: the average of the places they cover."""
    covered = [table[i] if i < len(table) else 0.0 for i in range(position - 1, position - 1 + tied)]
    return sum(covered) / len(covered)


def week_of(tournament: dict[str, Any]) -> int | None:
    m = re.search(r"week\s*(\d+)", tournament.get("name") or "", re.I)
    return int(m.group(1)) if m else None


class Board:
    def __init__(self, weeks: dict[int, list[Entry]], league: League, points_table: list[float] | None) -> None:
        self.weeks = weeks
        self.league = league
        self.points_table = points_table or []

    @classmethod
    def from_squabbit(cls, items: list[tuple[dict, dict | None]], league: League,
                      points_table: list[float] | None) -> "Board":
        """`items`: each league tournament with its leaderboard document (or None)."""
        from .handicap import _format

        weeks: dict[int, list[Entry]] = {}
        for t, lb in items:
            week = week_of(t)
            boards = list(((lb or {}).get("leaderboards") or {}).values())
            if week is None or not boards:
                continue
            teams = _format(t).get("teams") or {}
            entries = []
            for e in boards[0].get("teamEntries") or []:
                total = e.get("total")
                entries.append(Entry(team=cls._team(league, teams.get(e.get("entityId")) or {}, e.get("entityName")),
                                     net=None if total is None or e.get("dnf") else int(total)))
            weeks[week] = entries
        return cls(weeks, league, points_table)

    @staticmethod
    def _team(league: League, squabbit_team: dict, name: str | None) -> str:
        """The league team behind a Squabbit team: by its players' Squabbit ids, else by its name."""
        teams = {league.player_team.get(p) for u in squabbit_team.get("userIds") or []
                 if (p := league.squabbit_ids.get(u))}
        if len(teams) == 1 and None not in teams:
            return teams.pop()
        return league.match_team(name) or name or "?"

    def posted(self, week: int, exclude: str | None = None) -> list[Entry]:
        """The week's posted results, best first."""
        return sorted((e for e in self.weeks.get(week, []) if e.net is not None and e.team != exclude),
                      key=lambda e: e.net)

    def team_count(self, week: int) -> int:
        return len(self.weeks.get(week, []))

    def final(self, week: int, today: str) -> bool:
        entries = self.weeks.get(week, [])
        if not any(e.net is not None for e in entries):
            return False
        if all(e.net is not None for e in entries):
            return True
        end = (self.league.week_entry(week) or {}).get("end_date")
        return bool(end) and str(end) < today

    def standings(self, today: str | None = None) -> tuple[list[tuple[str, float, int]], int]:
        """[(team, points, place)] best first over the final weeks, and how many weeks that is."""
        today = today or datetime.date.today().isoformat()
        if not self.points_table:
            return [], 0
        totals: dict[str, float] = {}
        weeks = [w for w in sorted(self.weeks) if self.final(w, today)]
        for w in weeks:
            for e in self.weeks[w]:
                totals.setdefault(e.team, 0.0)
            nets = [e.net for e in self.weeks[w] if e.net is not None]
            for e in self.weeks[w]:
                if e.net is not None:
                    pos, _ = place(e.net, nets)
                    totals[e.team] += place_points(pos, nets.count(e.net), self.points_table)
        if not weeks:
            return [], 0
        order = sorted(totals.items(), key=lambda kv: -kv[1])
        return [(t, p, 1 + sum(1 for _, q in order if q > p)) for t, p in order], len(weeks)
