#!/usr/bin/env python3
"""Testy sejfika. Nie wymagają działającego Sejfika — podstawiają atrapę HTTP.

    python3 tests/test_sejfik.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_loader(
    "sejfik", importlib.machinery.SourceFileLoader("sejfik", str(ROOT / "sejfik"))
)
sejfik = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sejfik)


SECRETS = {
    "sejfik://item/12/password": "haslo-ze-sejfika",
    "sejfik://item/12/login": "sklep-user",
}


class FakeSejfik(BaseHTTPRequestHandler):
    tokens_seen: list[str] = []

    def log_message(self, *args):  # cisza w trakcie testów
        pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/vault/agent/whoami":
            self._json(200, {"ok": True, "actor": {"id": 7, "name": "Bartek"}, "available": 3})
        else:
            self._json(404, {"ok": False, "error": "nie ma"})

    def do_POST(self):
        FakeSejfik.tokens_seen.append(self.headers.get("Authorization", ""))
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")

        if self.path != "/api/vault/agent/resolve":
            return self._json(404, {"ok": False, "error": "nie ma"})

        ref = payload.get("ref")
        if ref in SECRETS:
            return self._json(200, {"ok": True, "value": SECRETS[ref]})
        return self._json(403, {"ok": False, "error": "Brak wpisu w teczce agenta."})


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeSejfik)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        os.environ["SEJFIK_HOME"] = self.home.name
        os.environ["SEJFIK_URL"] = self.url
        os.environ["SEJFIK_TOKEN"] = "token-testowy"
        # Moduł policzył ścieżki przy imporcie — trzeba je przestawić.
        sejfik.CONFIG_DIR = Path(self.home.name)
        sejfik.TOKEN_FILE = Path(self.home.name) / "token"
        sejfik.CONFIG_FILE = Path(self.home.name) / "config"

    def tearDown(self):
        self.home.cleanup()
        for key in ("SEJFIK_HOME", "SEJFIK_URL", "SEJFIK_TOKEN"):
            os.environ.pop(key, None)


class TestReferencje(Base):
    def test_wartosc_nigdy_nie_uchodzi_za_referencje(self):
        resolve = sejfik.Resolver(self.url, "t", "test")
        with self.assertRaises(sejfik.SejfikError) as ctx:
            resolve("moje-tajne-haslo")
        self.assertIn("to nie jest referencja", str(ctx.exception))

    def test_odmawia_nieznanego_pola(self):
        resolve = sejfik.Resolver(self.url, "t", "test")
        with self.assertRaises(sejfik.SejfikError):
            resolve("sejfik://item/12/totp_secret")

    def test_ten_sam_ref_pobierany_raz(self):
        resolve = sejfik.Resolver(self.url, "t", "test")
        before = len(FakeSejfik.tokens_seen)
        resolve("sejfik://item/12/password")
        resolve("sejfik://item/12/password")
        self.assertEqual(1, len(FakeSejfik.tokens_seen) - before)

    def test_wpis_spoza_teczki_agenta(self):
        resolve = sejfik.Resolver(self.url, "t", "test")
        with self.assertRaises(sejfik.SejfikError) as ctx:
            resolve("sejfik://item/999/password")
        self.assertIn("teczce agenta", str(ctx.exception))


class TestToken(Base):
    def test_plik_tokenu_czytelny_dla_innych_jest_odrzucany(self):
        os.environ.pop("SEJFIK_TOKEN")
        sejfik.TOKEN_FILE.write_text("token")
        sejfik.TOKEN_FILE.chmod(0o644)
        with self.assertRaises(sejfik.SejfikError) as ctx:
            sejfik.read_token()
        self.assertIn("chmod 600", str(ctx.exception))

    def test_plik_tokenu_600_dziala(self):
        os.environ.pop("SEJFIK_TOKEN")
        sejfik.TOKEN_FILE.write_text("token-z-pliku\n")
        sejfik.TOKEN_FILE.chmod(0o600)
        self.assertEqual("token-z-pliku", sejfik.read_token())

    def test_token_nie_trafia_do_procesu_potomnego(self):
        resolve = sejfik.Resolver(self.url, "t", "test")
        env = sejfik.child_environment([("HASLO", "sejfik://item/12/password")], resolve)
        self.assertEqual("haslo-ze-sejfika", env["HASLO"])
        self.assertNotIn("SEJFIK_TOKEN", env)
        self.assertNotIn("SEJFIK_AGENT_TOKEN", env)

    def test_brak_adresu_mowi_co_zrobic(self):
        os.environ.pop("SEJFIK_URL")
        with self.assertRaises(sejfik.SejfikError) as ctx:
            sejfik.resolve_url(None)
        self.assertIn("SEJFIK_URL", str(ctx.exception))


class TestInject(Base):
    def test_wypelnia_szablon_i_zawęża_prawa(self):
        template = Path(self.home.name) / "config.tpl"
        target = Path(self.home.name) / "config.yaml"
        template.write_text("api_key: {{ sejfik://item/12/password }}\nuser: {{sejfik://item/12/login}}\n")

        code = sejfik.main(["inject", "-i", str(template), "-o", str(target)])

        self.assertEqual(0, code)
        self.assertEqual("api_key: haslo-ze-sejfika\nuser: sklep-user\n", target.read_text())
        self.assertEqual(0o600, stat.S_IMODE(target.stat().st_mode))

    def test_nie_nadpisuje_bez_pytania(self):
        template = Path(self.home.name) / "t.tpl"
        target = Path(self.home.name) / "istnieje.yaml"
        template.write_text("{{ sejfik://item/12/password }}")
        target.write_text("stare")

        self.assertEqual(2, sejfik.main(["inject", "-i", str(template), "-o", str(target)]))
        self.assertEqual("stare", target.read_text())

    def test_szablon_bez_referencji_to_blad(self):
        template = Path(self.home.name) / "puste.tpl"
        template.write_text("nic tu nie ma\n")
        self.assertEqual(2, sejfik.main(["inject", "-i", str(template), "-o", "-"]))

    def test_nieudane_wypelnienie_nie_zostawia_smieci(self):
        template = Path(self.home.name) / "zly.tpl"
        template.write_text("{{ sejfik://item/999/password }}")
        self.assertEqual(2, sejfik.main(["inject", "-i", str(template),
                                         "-o", str(Path(self.home.name) / "wynik.yaml")]))
        resztki = [p for p in Path(self.home.name).iterdir() if p.name.startswith(".sejfik-")]
        self.assertEqual([], resztki)


class TestRun(Base):
    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        return subprocess.run(
            [sys.executable, str(ROOT / "sejfik"), *args],
            capture_output=True, text=True, env=env, timeout=30,
        )

    def test_sekret_dociera_do_procesu_ale_nie_do_argv(self):
        wynik = self._run(["run", "--env", "HASLO=sejfik://item/12/password",
                           "--", "sh", "-c", 'echo "$HASLO"'])
        self.assertEqual(0, wynik.returncode)
        self.assertEqual("haslo-ze-sejfika", wynik.stdout.strip())

    def test_kod_wyjscia_przechodzi_bez_zmian(self):
        wynik = self._run(["run", "--env", "X=sejfik://item/12/password", "--", "sh", "-c", "exit 42"])
        self.assertEqual(42, wynik.returncode)

    def test_bez_env_i_bez_stdin_odmawia(self):
        wynik = self._run(["run", "--", "true"])
        self.assertEqual(2, wynik.returncode)
        self.assertIn("nie podałeś, co wstrzyknąć", wynik.stderr)

    def test_stdin_podaje_sekret_na_wejscie(self):
        wynik = self._run(["run", "--stdin", "sejfik://item/12/password", "--", "cat"])
        self.assertEqual(0, wynik.returncode)
        self.assertEqual("haslo-ze-sejfika", wynik.stdout.strip())

    def test_read_na_terminal_odmawia(self):
        # stdout przechwycony przez potok nie jest terminalem, więc przechodzi.
        wynik = self._run(["read", "sejfik://item/12/password"])
        self.assertEqual(0, wynik.returncode)
        self.assertEqual("haslo-ze-sejfika", wynik.stdout)

    def test_whoami(self):
        wynik = self._run(["whoami"])
        self.assertEqual(0, wynik.returncode)
        self.assertIn("Bartek", wynik.stdout)


class TestZgodnoscWstecz(Base):
    """Stare `sejfik-run` nadal działa — narzędzie krążyło pod tą nazwą."""

    def _przez_dowiazanie(self, args: list[str]) -> subprocess.CompletedProcess:
        link = Path(self.home.name) / "sejfik-run"
        link.symlink_to(ROOT / "sejfik")
        return subprocess.run(
            [sys.executable, str(link), *args],
            capture_output=True, text=True, env=os.environ.copy(), timeout=30,
        )

    def test_stara_skladnia_env(self):
        wynik = self._przez_dowiazanie(
            ["--ref", "sejfik://item/12/password", "--env", "HASLO", "--", "sh", "-c", 'echo "$HASLO"']
        )
        self.assertEqual(0, wynik.returncode, wynik.stderr)
        self.assertEqual("haslo-ze-sejfika", wynik.stdout.strip())

    def test_stara_skladnia_stdin(self):
        wynik = self._przez_dowiazanie(["--ref", "sejfik://item/12/password", "--stdin", "--", "cat"])
        self.assertEqual(0, wynik.returncode, wynik.stderr)
        self.assertEqual("haslo-ze-sejfika", wynik.stdout.strip())

    def test_stara_skladnia_bez_env_mowi_o_co_chodzi(self):
        wynik = self._przez_dowiazanie(["--ref", "sejfik://item/12/password", "--", "true"])
        self.assertEqual(2, wynik.returncode)
        self.assertIn("--env", wynik.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
