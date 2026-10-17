"""Reads this league's own data (handicaps, scores) from Squabbit at round start.

The booth signs in as the league organiser with SQUABBIT_EMAIL / SQUABBIT_PASSWORD from
the booth's .env, then reads the league, its tournaments and scorecards. Read-only: it
never writes to Squabbit. A handful of requests per round, cached for the night.

Squabbit is a Firebase app, so this talks to Firebase directly: Identity Toolkit to sign
in, then the Firestore REST API to read documents. The web API key is the one the public
web app ships with (js/ideasAuth.js); Firestore's own rules still decide what the signed-in
account may read, so this sees only what the app would show the same account.
"""

import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Public Firebase web API key shipped in Squabbit's web app, not a secret: it only identifies
# the project. Access is enforced by Firestore rules and the signed-in account.
API_KEY = "AIzaSyDGVjvgrebAuRyRHOrztVLhRaUCP0N6TVM"
PROJECT = "squabbit-2019"
_SIGNIN = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
_DOCS = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"


class SquabbitError(RuntimeError):
    pass


def _value(v: dict[str, Any]) -> Any:
    """Unwraps one Firestore typed value into a plain Python value."""
    for kind, raw in v.items():
        if kind == "integerValue":
            return int(raw)
        if kind == "doubleValue":
            return float(raw)
        if kind == "booleanValue":
            return bool(raw)
        if kind == "nullValue":
            return None
        if kind == "mapValue":
            return {k: _value(x) for k, x in raw.get("fields", {}).items()}
        if kind == "arrayValue":
            return [_value(x) for x in raw.get("values", [])]
        return raw  # stringValue, timestampValue, referenceValue, etc.
    return None


def _fields(doc: dict[str, Any]) -> dict[str, Any]:
    out = {k: _value(v) for k, v in doc.get("fields", {}).items()}
    out["_id"] = doc.get("name", "").rsplit("/", 1)[-1]
    return out


class SquabbitClient:
    def __init__(self, email: str | None = None, password: str | None = None) -> None:
        self.email = email or os.environ.get("SQUABBIT_EMAIL")
        self.password = password or os.environ.get("SQUABBIT_PASSWORD")
        if not self.email or not self.password:
            raise SquabbitError("set SQUABBIT_EMAIL and SQUABBIT_PASSWORD in the booth .env")
        self._http = httpx.Client(timeout=30)
        self._token: str | None = None

    def __enter__(self) -> "SquabbitClient":
        self.sign_in()
        return self

    def __exit__(self, *exc: object) -> None:
        self._http.close()

    def sign_in(self) -> None:
        resp = self._http.post(_SIGNIN, json={
            "email": self.email, "password": self.password, "returnSecureToken": True,
        })
        if resp.status_code != 200:
            reason = resp.json().get("error", {}).get("message", "") if resp.text else ""
            hint = {
                "INVALID_LOGIN_CREDENTIALS": "wrong email or password (or the account has no password; "
                                             "if you sign in with Google/Apple, password sign-in won't work)",
                "EMAIL_NOT_FOUND": "no account for that email",
                "INVALID_PASSWORD": "wrong password",
                "USER_DISABLED": "the account is disabled",
            }.get(reason, reason or "check the .env credentials")
            raise SquabbitError(f"sign-in failed ({resp.status_code}): {hint}")
        self._token = resp.json()["idToken"]
        log.info("signed in to Squabbit as %s", self.email)

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self.sign_in()
        return {"Authorization": f"Bearer {self._token}"}

    def document(self, path: str) -> dict[str, Any] | None:
        """Fetches one document by path, e.g. 'users/<id>'. None if it's missing or not readable."""
        resp = self._http.get(f"{_DOCS}/{path}", headers=self._headers())
        if resp.status_code in (403, 404):
            return None
        resp.raise_for_status()
        return _fields(resp.json())

    def _query(self, collection: str, where: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        """Runs a Firestore structured query and returns the matched documents' fields."""
        filters = [{"fieldFilter": {
            "field": {"fieldPath": f}, "op": op,
            "value": {"stringValue": v} if isinstance(v, str) else {"integerValue": str(v)},
        }} for f, op, v in where]
        query: dict[str, Any] = {"from": [{"collectionId": collection}]}
        if len(filters) == 1:
            query["where"] = filters[0]
        elif filters:
            query["where"] = {"compositeFilter": {"op": "AND", "filters": filters}}
        resp = self._http.post(f"{_DOCS}:runQuery", headers=self._headers(),
                               json={"structuredQuery": query})
        resp.raise_for_status()
        return [_fields(row["document"]) for row in resp.json() if "document" in row]

    def league_by_invite(self, invite_code: str) -> dict[str, Any] | None:
        rows = self._query("leagues", [("inviteCode", "EQUAL", invite_code)])
        return rows[0] if rows else None

    def tournaments(self, league_id: str) -> list[dict[str, Any]]:
        return self._query("tournamentsV2", [("leagueId", "EQUAL", league_id)])

    def scorecards(self, tournament_id: str) -> list[dict[str, Any]]:
        return self._query("scorecards", [("tournamentId", "EQUAL", tournament_id)])

    def tournament_rounds(self, tournament_id: str) -> list[dict[str, Any]]:
        """A tournament's rounds: each carries the course card (holes, tees) and the tee played."""
        resp = self._http.get(f"{_DOCS}/tournamentsV2/{tournament_id}/tournamentRounds", headers=self._headers())
        if resp.status_code in (403, 404):
            return []
        resp.raise_for_status()
        return [_fields(d) for d in resp.json().get("documents", [])]

    def leaderboard(self, tournament_id: str) -> dict[str, Any] | None:
        return self.document(f"tournamentsLeaderboards/{tournament_id}")

    def league_rounds(self, league_id: str) -> list[dict[str, Any]]:
        """Every player round posted in the league: hole scores, the tee, and the handicap index used."""
        return self._query("rounds", [("leagueId", "EQUAL", league_id)])

    def week_cards(self, league_id: str) -> list[dict[str, Any]]:
        """Each league week's Squabbit card (see handicap.week_card), in week order."""
        from .handicap import week_card

        cards = []
        for t in self.tournaments(league_id):
            rounds = self.tournament_rounds(t["_id"])
            card = week_card(t, rounds[0]) if rounds else None
            if card:
                cards.append(card)
        return sorted(cards, key=lambda c: (c["week"] is None, c["week"] or 0, c["date"] or ""))

    def handicaps(self, ids: list[str]) -> dict[str, float | None]:
        """Each user's current profile handicap (18-hole index), keyed by Squabbit user id.

        The authoritative value lives on the player's own `users/<id>` document; the copy cached
        on a league registration goes stale. Fetched in parallel so a round's handful of lookups
        stay quick."""
        from concurrent.futures import ThreadPoolExecutor

        def one(uid: str) -> tuple[str, float | None]:
            doc = self.document(f"users/{uid}")
            return uid, (doc or {}).get("handicap")

        if not ids:
            return {}
        with ThreadPoolExecutor(max_workers=min(6, len(ids))) as pool:
            return dict(pool.map(one, ids))
