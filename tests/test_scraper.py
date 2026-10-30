"""Offline tests: parsers, language detection, merging and the full build with mocked sources."""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from zoneinfo import ZoneInfo

from scraper import build, elisa, liiga, mtv, ruutu, viaplay

HEL = ZoneInfo("Europe/Helsinki")

FIX = Path(__file__).parent / "fixtures"
EXTRA = {"Track Positioning", "Timing", "Onboard", "Pitlane"}


def load(name):
    return json.loads((FIX / name).read_text())


class ViaplayTests(unittest.TestCase):
    def test_motorsport_keeps_sessions_and_drops_extra_feeds_and_replays(self):
        ev = viaplay.parse_day(load("viaplay_f1.json"), sport="f1", fmt="Formula 1", extra_feeds=EXTRA)
        self.assertEqual([e["session"] for e in ev], ["2. vapaat harjoitukset", "Aika-ajot"])
        self.assertTrue(all(e["title"] == "Meksikon Grand Prix" for e in ev))
        self.assertEqual(ev[0]["start"], "2026-10-30T19:50:00Z")
        self.assertEqual(ev[0]["url"], "https://viaplay.fi/urheilu/moottoriurheilu/formula-1/meksikon-grand-prix/s1")

    def test_format_filter(self):
        ev = viaplay.parse_day(load("viaplay_f1.json"), sport="motogp", fmt="MotoGP", extra_feeds=EXTRA)
        self.assertEqual(ev, [])

    def test_day_links(self):
        self.assertEqual([l["date"] for l in viaplay.day_links(load("viaplay_f1.json"))], ["2026-10-31", "2026-11-01"])

    def test_language_detection(self):
        fi = {"content": {"description": {"synopsis": "Selostus Antti Mäkinen, asiantuntija Tuomas Grönman."}}}
        en = {"content": {"description": {"synopsis": "Englanninkielinen selostus."}}}
        arr = {"content": {"audioLanguages": [{"code": "fin"}]}}
        none = {"content": {"description": {"synopsis": "Runkosarjaottelu."}}}
        self.assertEqual(viaplay.detect_language(fi), "fi")
        self.assertEqual(viaplay.detect_language(en), "en")
        self.assertEqual(viaplay.detect_language(arr), "fi")
        self.assertIsNone(viaplay.detect_language(none))

    def test_broken_structure_raises(self):
        with self.assertRaises(ValueError):
            viaplay.parse_day({"foo": 1}, sport="f1", fmt=None, extra_feeds=set())


class LiigaTests(unittest.TestCase):
    def test_parse_window_and_unresolved(self):
        first = datetime(2026, 10, 30, tzinfo=timezone.utc)
        last = datetime(2026, 11, 13, tzinfo=timezone.utc)
        ev = liiga.parse(load("liiga.json"), first=first, last=last, tournament="runkosarja")
        self.assertEqual([e["title"] for e in ev], ["Tappara – Ilves", "JYP – TPS"])
        self.assertTrue(all(e["language"] == "fi" for e in ev))

    def test_season(self):
        from datetime import date
        self.assertEqual(liiga.season_for(date(2026, 10, 30)), 2027)
        self.assertEqual(liiga.season_for(date(2027, 3, 1)), 2027)


class MtvTests(unittest.TestCase):
    def test_only_live(self):
        items = mtv.parse_epg(load("mtv_sub.json"), "MTV Sub")
        self.assertEqual([i["title"] for i in items], ["NHL: Detroit Red Wings – Winnipeg Jets", "Liiga: JYP–TPS"])
        self.assertEqual(items[0]["start"], "2026-11-01T18:45:00Z")


class MergeTests(unittest.TestCase):
    def setUp(self):
        first = datetime(2026, 10, 30, tzinfo=timezone.utc)
        last = datetime(2026, 11, 13, tzinfo=timezone.utc)
        self.liiga = liiga.parse(load("liiga.json"), first=first, last=last, tournament="runkosarja")
        self.mtv = mtv.parse_epg(load("mtv_sub.json"), "MTV Sub")
        self.vp_nhl = viaplay.parse_day(load("viaplay_nhl.json"), sport="nhl", fmt="NHL", extra_feeds=EXTRA)

    def test_free_liiga_and_sub_nhl_merge_into_existing_events(self):
        events, report = build.merge(self.vp_nhl, self.liiga, self.mtv, [])
        jyp = next(e for e in events if e["title"] == "JYP – TPS")
        self.assertEqual({b["service"] for b in jyp["broadcasts"]}, {"MTV Katsomo+", "MTV Sub"})
        self.assertTrue(any(b["free"] for b in jyp["broadcasts"]))
        det = [e for e in events if e["sport"] == "nhl" and "Detroit" in e["title"]]
        self.assertEqual(len(det), 1, "Sub-lähetys yhdistyy Viaplayn otteluun")
        self.assertEqual({b["service"] for b in det[0]["broadcasts"]}, {"Viaplay", "MTV Sub"})
        self.assertEqual(report["mtv_unmatched"], [])

    def test_override_adds_disney(self):
        o = {"sport": "nhl", "series": "NHL", "title": "Edmonton Oilers – Dallas Stars",
             "start": "2026-11-03T01:00:00Z", "service": "Disney+", "free": False, "language": "fi",
             "url": "https://www.disneyplus.com/"}
        events, _ = build.merge(self.vp_nhl, [], [], [o])
        edm = next(e for e in events if "Edmonton" in e["title"])
        self.assertEqual({b["service"] for b in edm["broadcasts"]}, {"Viaplay", "Disney+"})
        self.assertTrue(any(b["manual"] for b in edm["broadcasts"]))

    def test_ambiguous_match_is_not_merged(self):
        evs = [build.to_event(dict(e, start="2026-11-01T18:00:00Z", title=t, teams=None))
               for e, t in ((self.vp_nhl[0], "Detroit Red Wings – A"), (self.vp_nhl[0], "Detroit Red Wings – B"))]
        self.assertIsNone(build.find_match(evs, "nhl", datetime(2026, 11, 1, 18, tzinfo=timezone.utc), "Detroit"))


class NflTests(unittest.TestCase):
    def setUp(self):
        from datetime import date
        self.games = ruutu.parse((FIX / "ruutu_nfl.html").read_text(), today=date(2026, 10, 30))
        self.jim = elisa.parse(load("elisa_jim.json"))

    def test_ruutu_parses_games_skips_redzone(self):
        self.assertEqual([g["title"] for g in self.games], [
            "Kansas City Chiefs – Buffalo Bills", "San Francisco 49ers – Dallas Cowboys",
            "Green Bay Packers – Detroit Lions", "Jacksonville Jaguars – Miami Dolphins"])
        self.assertEqual(self.games[0]["start"], "2026-11-01T18:00:00Z")   # 20.00 Suomen aikaa (talviaika)
        self.assertEqual([g["language"] for g in self.games], ["fi", "fi", "en", "fi"])
        self.assertEqual(self.games[0]["url"], "https://www.ruutu.fi/stream/4002")

    def test_ruutu_react_markup_self_closing_tags_and_comments(self):
        from datetime import date
        games = ruutu.parse((FIX / "ruutu_nfl_react.html").read_text(), today=date(2026, 10, 30))
        self.assertEqual([(g["title"], g["start"], g["language"]) for g in games], [
            ("Kansas City Chiefs – Buffalo Bills", "2026-11-01T18:00:00Z", "fi"),
            ("New England Patriots & Co – New York Jets", "2026-11-01T21:25:00Z", "fi")])

    def test_ruutu_only_redzone_is_not_an_error(self):
        from datetime import date
        html = (FIX / "ruutu_nfl_react.html").read_text()
        only_rz = html.split("<li>")[0] + "<li>" + html.split("<li>")[2]
        self.assertEqual(ruutu.parse(only_rz, today=date(2026, 10, 30)), [])

    def test_ruutu_unreadable_cards_raise(self):
        from datetime import date
        html = (FIX / "ruutu_nfl_react.html").read_text().replace("1.11.", "")
        with self.assertRaises(ValueError):
            ruutu.parse(html, today=date(2026, 10, 30))

    def test_ruutu_structure_change_raises(self):
        from datetime import date
        with self.assertRaises(ValueError):
            ruutu.parse("<html><h1>Etusivu</h1></html>", today=date(2026, 10, 30))

    def test_elisa_only_live_nfl_on_supported_channels(self):
        self.assertEqual([(i["channel"], i["start"]) for i in self.jim], [("Jim", "2026-11-01T17:55:00Z")])

    def test_jim_joins_finnish_slot(self):
        events, report = build.merge([], [], [], [], self.games, self.jim)
        kc = next(e for e in events if "Chiefs" in e["title"])
        self.assertEqual({b["service"] for b in kc["broadcasts"]}, {"Ruutu+", "Jim"})
        self.assertTrue(next(b for b in kc["broadcasts"] if b["service"] == "Jim")["free"])
        self.assertEqual(report["nfl_free_unmatched"], [])


class WindowTests(unittest.TestCase):
    def ts(self, local):
        return datetime.fromisoformat(local).replace(tzinfo=HEL)

    def test_inclusive_bounds(self):
        w = ["16:00", "23:00"]
        self.assertTrue(build.in_window(self.ts("2026-11-01T16:00"), w, HEL))
        self.assertTrue(build.in_window(self.ts("2026-11-01T23:00"), w, HEL))
        self.assertFalse(build.in_window(self.ts("2026-11-01T23:25"), w, HEL))
        self.assertFalse(build.in_window(self.ts("2026-11-01T15:59"), w, HEL))
        self.assertFalse(build.in_window(self.ts("2026-11-02T02:00"), w, HEL))
        self.assertTrue(build.in_window(self.ts("2026-11-02T02:00"), None, HEL))

    def test_summer_time_uses_local_clock(self):
        # 19.00 UTC = 22.00 kesäaikaa, 21.00 talviaikaa
        self.assertTrue(build.in_window(datetime(2026, 7, 1, 19, tzinfo=timezone.utc), ["22:00", "22:00"], HEL))
        self.assertTrue(build.in_window(datetime(2026, 12, 1, 19, tzinfo=timezone.utc), ["21:00", "21:00"], HEL))

    def test_finalize_applies_window_per_sport_only(self):
        now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
        last = datetime(2026, 11, 13, tzinfo=timezone.utc)
        evs = [build.to_event(dict(e, sport=sport, title=f"{sport} {e['start']}", end=None))
               for sport in ("nhl", "f1") for e in ({"start": "2026-11-01T19:00:00Z"}, {"start": "2026-11-02T01:00:00Z"})]
        out = build.finalize(evs, now, last, {"nhl": ["16:00", "23:00"]}, HEL)
        self.assertEqual(sorted((e["sport"], e["start"]) for e in out), [
            ("f1", "2026-11-01T19:00:00Z"), ("f1", "2026-11-02T01:00:00Z"), ("nhl", "2026-11-01T19:00:00Z")])


class BuildTests(unittest.TestCase):
    def test_full_build_with_mocked_sources(self):
        def fake_get(url, **kw):
            if "liiga.fi" in url:
                return load("liiga.json") if "runkosarja" in url else []
            if "formula-1" in url:
                return load("viaplay_f1.json")
            if "jaakiekko/nhl" in url:
                return load("viaplay_nhl.json")
            if url.endswith("pcdash-fi/urheilu"):
                return {"_links": {"x": {"href": "https://content.viaplay.fi/pcdash-fi/urheilu/darts"}}}
            return {"_embedded": {}, "_links": {}}

        def fake_post(url, payload, headers=None):
            if "Channels" in payload["query"]:
                return {"data": {"channels": [{"id": "sub", "title": "Sub"}, {"id": "m3", "title": "MTV3"}]}}
            return load("mtv_sub.json") if payload["variables"]["id"] == "sub" else {"data": {"media": {"epg": []}}}

        def fake_elisa(url, **kw):
            if url.endswith("/channels"):
                return {"channels": [{"id": 77, "name": "Jim"}]}
            return load("elisa_jim.json")

        with mock.patch.object(viaplay, "get_json", fake_get), mock.patch.object(liiga, "get_json", fake_get), \
             mock.patch.object(ruutu, "request", lambda url, **kw: (FIX / "ruutu_nfl.html").read_text()), \
             mock.patch.object(elisa, "get_json", fake_elisa), \
             mock.patch.object(mtv, "post_json", fake_post), \
             mock.patch.object(build, "CACHE", FIX.parent / ".tmp-cache"), \
             mock.patch.object(build, "OUT", FIX.parent / ".tmp-site"):
            rc = build.main(["--now", "2026-10-30T18:00:00Z"])
        self.assertEqual(rc, 0)
        data = json.loads((FIX.parent / ".tmp-site" / "schedule.json").read_text())
        sports = {e["sport"] for e in data["events"]}
        self.assertEqual(sports, {"f1", "nhl", "liiga", "nfl"})
        hel = lambda e: datetime.fromisoformat(e["start"].replace("Z", "+00:00")).astimezone(HEL).strftime("%H:%M")
        for e in data["events"]:
            if e["sport"] in ("nhl", "nfl"):
                self.assertTrue("16:00" <= hel(e) <= "23:00", e)
        self.assertEqual(sorted(e["title"] for e in data["events"] if e["sport"] == "nfl"),
                         ["Jacksonville Jaguars – Miami Dolphins", "Kansas City Chiefs – Buffalo Bills"])
        self.assertNotIn("Edmonton Oilers – Dallas Stars", [e["title"] for e in data["events"]])
        self.assertEqual([e["start"] for e in data["events"]], sorted(e["start"] for e in data["events"]))
        self.assertEqual(data["status"]["viaplay-darts"]["state"], "ok")


if __name__ == "__main__":
    unittest.main()
