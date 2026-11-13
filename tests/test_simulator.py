"""Automatische Tests (nur Standardbibliothek: python -m unittest -v).

Sie sichern die Anforderungen aus der Anforderungsliste V4 ab, soweit sie sich im Simulator prüfen lassen.
"""
import json
import math
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pren_sim import brain as B                     # noqa: E402
from pren_sim import protocol as P                  # noqa: E402
from pren_sim.config import Config                  # noqa: E402
from pren_sim.engine import Simulation              # noqa: E402
from pren_sim.experiments import gesture_matrix, monte_carlo, voice_matrix   # noqa: E402
from pren_sim.geometry import field_excess, sector_excess, wrap            # noqa: E402
from pren_sim.scenarios import list_scenarios, load_scenario, run_scenario  # noqa: E402


def ready_sim(seed=3, **env):
    s = Simulation(seed=seed)
    for k, v in env.items():
        s.set_env(**{k: v})
    assert s.wait_ready()
    return s


class Geometry(unittest.TestCase):
    def test_wrap(self):
        self.assertAlmostEqual(abs(wrap(2 * math.pi)), 0.0, places=9)
        self.assertAlmostEqual(wrap(-3.5 * math.pi), 0.5 * math.pi, places=9)

    def test_sector(self):
        h = math.radians(15)
        self.assertEqual(sector_excess(2, 0, h, 5), 0.0)
        self.assertEqual(sector_excess(4.9, 0.3, h, 5), 0.0)
        self.assertGreater(sector_excess(2, 1.5, h, 5), 0.5)       # weit neben dem Segment
        self.assertAlmostEqual(sector_excess(5.5, 0, h, 5), 0.5, places=6)   # hinter dem Bogen
        self.assertGreater(sector_excess(-1.0, 0, h, 5), 0.9)      # hinter dem Scheitel
        self.assertEqual(field_excess(0.0, 0.0, h, 5, 0.0, 0.5, 0.2), 0.0)    # im Startfeld


class Protokoll(unittest.TestCase):
    def test_parse_und_format(self):
        self.assertEqual(P.parse("DRIVE 0.300 -0.5"), ("DRIVE", ["0.300", "-0.5"]))
        self.assertEqual(P.fmt_drive(0.3, -0.5), "DRIVE 0.300 -0.500")
        self.assertEqual(P.parse("   ")[0], "")


class Firmware(unittest.TestCase):
    def test_fahren_nur_im_stand(self):
        s = ready_sim()
        s.link.sbc_send("POSE SITZ")
        s.run_for(2.5)
        self.assertEqual(s.plant.pose, "SITZ")
        s.link.sbc_send("DRIVE 0.3 0")
        s.run_for(0.5)
        self.assertLess(abs(s.plant.v), 0.01)
        self.assertTrue(s.mcu.last_err.startswith("POSE"))

    def test_watchdog_stoppt_bei_stillem_rechner(self):
        s = ready_sim()
        s.link.sbc_send("DRIVE 0.4 0")           # einmaliger Fahrbefehl, danach kommt nichts mehr nach (Absturz)
        s.run_for(0.4)
        self.assertGreater(s.plant.v, 0.1)
        s.run_for(1.5)                            # PING allein darf die Fahrfreigabe nicht verlängern
        self.assertLess(abs(s.plant.v), 0.02)
        self.assertTrue(s.log.find("watchdog"))

    def test_hardware_notaus_ohne_verbindung(self):
        s = ready_sim()
        for _ in range(5):                        # Fahrbefehle regelmässig erneuern (wie das Brain)
            s.link.sbc_send("DRIVE 0.5 0")
            s.run_for(0.2)
        self.assertGreater(s.plant.v, 0.2)
        s.set_env(link_ok=False)
        s.press_estop()
        s.run_for(0.6)
        self.assertLess(abs(s.plant.v), 0.01)
        self.assertTrue(s.mcu.estop)
        self.assertEqual(s.mcu.estop_src, "hw")

    def test_notaus_sperrt_fahren_und_quittieren_nur_nach_entriegeln(self):
        s = ready_sim()
        s.press_estop()
        s.run_for(0.3)
        s.link.sbc_send("ESTOP_RESET")
        s.run_for(0.2)
        self.assertTrue(s.mcu.estop)            # Taster noch gedrückt
        s.release_estop()
        s.link.sbc_send("ESTOP_RESET")
        s.run_for(0.2)
        self.assertFalse(s.mcu.estop)


class Ablauf(unittest.TestCase):
    def test_suchlauf_komplett(self):
        s = ready_sim()
        s.place_bone(3.0, 0.4, 0.5)
        s.say("SUCH")
        self.assertTrue(s.run_until(lambda x: x.log.find("run_complete"), 120))
        t_c = s.log.find("contact_true")[0]["t"]
        t_f = s.log.find("found")[0]["t"]
        self.assertGreaterEqual(t_f, t_c)
        self.assertLess(t_f - t_c, 1.0)                       # Anf. 6.4
        tr = s.log.find("run_truth")[0]["data"]
        self.assertTrue(tr["in_start_field"])                 # Anf. 3.4
        self.assertEqual(tr["pose"], "SITZ")                  # Anf. 3.5
        self.assertEqual(s.brain.state, B.BEREIT)

    def test_fund_wird_vor_der_rueckkehr_gemeldet(self):
        s = ready_sim()
        s.place_bone(2.5, -0.3, 1.0)
        s.say("SUCH")
        s.run_until(lambda x: x.log.find("run_complete"), 120)
        order = [e["data"]["to"] for e in s.log.find("state")]
        self.assertLess(order.index(B.FUND), order.index(B.RUECKKEHR))

    def test_umdrehen_zum_suchbereich(self):
        s = ready_sim()
        s.say("SUCH")
        s.run_until(lambda x: x.brain.state == B.SUCHEN, 20)
        self.assertLess(abs(wrap(s.plant.th - 0.0)), math.radians(8))     # Kopf zeigt in den Suchbereich

    def test_live_mikrofon_durchlaeuft_brain_schwelle(self):
        s = ready_sim()
        s.say_live("SUCH", 0.3, "such")            # zu unsicher: unter der Schwelle 0.6
        s.run_for(2)
        self.assertEqual(s.brain.state, B.BEREIT)
        s.say_live("SUCH", 0.9, "such")
        s.run_for(2)
        self.assertNotEqual(s.brain.state, B.BEREIT)
        self.assertTrue(s.log.find("say_live"))

    def test_taster_ersetzt_ausgefallene_sprache(self):
        s = ready_sim(mic_ok=False)
        s.say("SUCH")
        s.run_for(4)
        self.assertEqual(s.brain.state, B.BEREIT)
        s.press_start()
        s.run_for(1)
        self.assertNotEqual(s.brain.state, B.BEREIT)

    def test_timeout_nach_zwei_minuten_und_rueckkehr(self):
        s = ready_sim()
        s.place_bone(1.5, 3.5, 0.0)                           # ausserhalb des Suchbereichs
        s.say("SUCH")
        self.assertTrue(s.run_until(lambda x: x.log.find("run_complete"), 200))
        rc = s.log.find("run_complete")[0]["data"]
        self.assertEqual(rc["reason"], "timeout")
        self.assertGreaterEqual(rc["search_time"], 120.0)
        self.assertTrue(s.log.find("run_truth")[0]["data"]["in_start_field"])

    def test_geste_wird_nicht_doppelt_ausgefuehrt(self):
        s = ready_sim()
        s.gesture("SITZ")
        s.run_for(5)
        self.assertEqual(len(s.log.find("cmd", name="SITZ")), 1)

    def test_auf_ergibt_stand_auf_vier_beinen(self):          # FAQ 11 / Anf. 5.12
        s = ready_sim()
        s.gesture("PLATZ")
        s.run_until(lambda x: x.plant.pose == "PLATZ" and not x.plant.pose_busy, 8)
        s.run_for(3)
        s.gesture("AUF")
        s.run_until(lambda x: x.plant.pose == "STAND" and not x.plant.pose_busy, 10)
        self.assertEqual(s.plant.pose, "STAND")

    def test_hier_faehrt_auf_die_person_zu(self):
        s = ready_sim(referee_distance=1.5)
        x0 = s.plant.x
        s.say("HIER")
        s.run_until(lambda x: x.log.find("here_done"), 15)
        self.assertGreater(x0 - s.plant.x, 0.3)               # Person liegt in -x
        self.assertGreater(s.world.referee[0], s.plant.x - 1.0)

    def test_nicht_erlaubter_befehl_wird_ignoriert(self):
        s = ready_sim()
        s.gesture("PLATZ")
        s.run_for(6)
        self.assertEqual(s.brain.state, B.PLATZ)
        s.say("SUCH")
        s.run_for(3)
        self.assertEqual(s.brain.state, B.PLATZ)

    def test_alle_uebergaenge_sind_im_diagramm(self):
        s = ready_sim()
        s.place_bone(2.5, 0.0, 0.0)
        s.say("SUCH")
        s.run_until(lambda x: x.log.find("run_complete"), 120)
        self.assertEqual(s.log.find("warn"), [])


class Erkennung(unittest.TestCase):
    def test_sprache_monoton_mit_laerm_und_distanz(self):
        r = voice_matrix(n=300, distances=(0.5, 2.0), noises=(45.0, 60.0), seed=5)["rows"]
        get = lambda d, n: sum(x["correct"] for x in r if x["distance"] == d and x["noise_db"] == n)
        self.assertGreater(get(0.5, 45.0), get(2.0, 45.0))
        self.assertGreater(get(0.5, 45.0), get(0.5, 60.0))
        self.assertGreater(get(2.0, 45.0), get(2.0, 60.0))

    def test_gesten_filter_keine_fehlausloesung_in_ruhe(self):
        self.assertLessEqual(gesture_matrix(n=10, seed=3)["false_triggers_per_10min"], 1)

    def test_deterministisch(self):
        a = voice_matrix(n=50, seed=9)
        b = voice_matrix(n=50, seed=9)
        self.assertEqual(a["rows"], b["rows"])


class Szenarien(unittest.TestCase):
    def test_alle_szenarien_bestehen(self):
        ids = [s["id"] for s in list_scenarios()]
        self.assertGreaterEqual(len(ids), 8)
        for sid in ids:
            with self.subTest(szenario=sid):
                res = run_scenario(load_scenario(sid))
                msg = json.dumps([c for c in res["checks"] if c["status"] == "fail"], ensure_ascii=False)
                self.assertTrue(res["passed"], f"{sid}: Schritte {res['steps']} / Fehler {msg}")

    def test_reproduzierbar(self):
        spec = load_scenario("04_knochen_am_rand")
        a, b = run_scenario(spec, seed=5), run_scenario(spec, seed=5)
        self.assertEqual(a["sim_time"], b["sim_time"])

    def test_monte_carlo_robust(self):
        m = monte_carlo(n=12, seed=2)["summary"]
        self.assertGreaterEqual(m["found_rate"], 0.9)
        self.assertLessEqual(m["report_latency_max"], 1.0)
        self.assertLessEqual(m["return_cm_max"], 10.0)


class Architektur(unittest.TestCase):
    def test_brain_ist_unabhaengig_vom_simulator(self):
        """Das Brain muss unverändert am echten Roboter laufen: keine Abhängigkeit zu Spielfeld/Strecke/Engine."""
        import subprocess
        code = ("import sys; sys.path.insert(0, %r); import pren_sim.brain; "
                "bad = [m for m in ('pren_sim.world', 'pren_sim.plant', 'pren_sim.engine', 'pren_sim.perception', 'pren_sim.mcu') if m in sys.modules]; "
                "print(bad); sys.exit(1 if bad else 0)" % str(ROOT / "src"))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Konfiguration(unittest.TestCase):
    def test_werte_aus_aufgabenstellung(self):
        c = Config()
        self.assertEqual(c.field.sector_angle_deg, 30.0)
        self.assertEqual(c.field.sector_radius, 5.0)
        self.assertEqual(c.field.interaction_radius, 1.5)
        self.assertEqual(c.brain.search_timeout_s, 120.0)
        self.assertLessEqual(c.robot.length, 0.50)          # Anf. 1.1 (max. 50 cm lang)
        self.assertLessEqual(c.robot.width, 0.20)           # Anf. 1.1 (max. 20 cm breit)
        self.assertEqual(c.sim.dt, 0.01)

    def test_merge_und_unbekannter_schluessel(self):
        c = Config.from_dict({"env": {"noise_db": 55}})
        self.assertEqual(c.env.noise_db, 55)
        with self.assertRaises(KeyError):
            Config.from_dict({"env": {"gibt_es_nicht": 1}})


if __name__ == "__main__":
    unittest.main()
