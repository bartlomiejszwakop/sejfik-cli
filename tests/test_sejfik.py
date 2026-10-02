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
    last_upload: bytes = b""

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
        raw = self.rfile.read(length)

        if self.path == "/api/transfers":
            if not self.headers.get("Authorization", "").endswith("klucz-przesylek"):
                return self._json(401, {"ok": False, "error": "Klucz nieprawidłowy albo odwołany."})
            FakeSejfik.last_upload = raw
            return self._json(201, {
                "ok": True,
                "url": "https://sejfik.example/s/abcdef1234567890",
                "expires_at": "2026-10-03T12:00:00+00:00",
                "download_limit": None,
            })

        payload = json.loads(raw or b"{}")

        if self.path == "/api/vault/agent/items":
            if not payload.get("name"):
                return self._json(422, {"ok": False, "error": "Wpis musi mieć nazwę."})
            return self._json(201, {
                "ok": True, "item_id": 1608, "name": payload["name"],
                "password_ref": "sejfik://item/1608/password",
            })

        if self.path == "/api/vault/agent/items/1608/rotate":
            return self._json(200, {
                "ok": True, "item_id": 1608, "name": "Sklep",
                "password_ref": "sejfik://item/1608/password",
            })

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


class TestZakladanie(Base):
    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "sejfik"), *args],
            capture_output=True, text=True, env=os.environ.copy(), timeout=30,
        )

    def test_na_wyjscie_idzie_sama_referencja(self):
        wynik = self._run(["create-login", "--name", "Sklep ALSO", "--url", "https://also.com"])
        self.assertEqual(0, wynik.returncode, wynik.stderr)
        # Dokładnie to, co złapie REF=$(sejfik create-login ...).
        self.assertEqual("sejfik://item/1608/password", wynik.stdout.strip())
        # Opis dla człowieka nie zaśmieca wyjścia.
        self.assertIn("Sklep ALSO", wynik.stderr)

    def test_odpowiedz_nie_zawiera_hasla(self):
        wynik = self._run(["create-login", "--name", "Sklep"])
        self.assertNotIn("password=", wynik.stdout + wynik.stderr)
        self.assertEqual(1, (wynik.stdout + wynik.stderr).count("sejfik://item/1608/password"))

    def test_rotacja_przyjmuje_numer_i_referencje(self):
        for cel in ("1608", "sejfik://item/1608/password"):
            wynik = self._run(["rotate-password", cel])
            self.assertEqual(0, wynik.returncode, wynik.stderr)
            self.assertEqual("sejfik://item/1608/password", wynik.stdout.strip())
            self.assertIn("historii wpisu", wynik.stderr)

    def test_rotacja_odrzuca_bzdurny_cel(self):
        wynik = self._run(["rotate-password", "moje-haslo"])
        self.assertEqual(2, wynik.returncode)
        self.assertIn("ani numer wpisu, ani referencja", wynik.stderr)

    def test_blad_serwera_dociera_do_uzytkownika(self):
        wynik = self._run(["rotate-password", "999"])
        self.assertEqual(2, wynik.returncode)
        self.assertIn("sejfik:", wynik.stderr)


class TestWysylanie(Base):
    def setUp(self):
        super().setUp()
        os.environ["SEJFIK_SEND_TOKEN"] = "klucz-przesylek"
        sejfik.SEND_TOKEN_FILE = Path(self.home.name) / "send-token"

    def tearDown(self):
        os.environ.pop("SEJFIK_SEND_TOKEN", None)
        super().tearDown()

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "sejfik"), *args],
            capture_output=True, text=True, env=os.environ.copy(), timeout=60,
        )

    def test_plik_leci_i_link_wraca_na_wyjscie(self):
        plik = Path(self.home.name) / "zrzut.png"
        plik.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

        wynik = self._run(["send", str(plik), "--note", "Blad na produkcji"])

        self.assertEqual(0, wynik.returncode, wynik.stderr)
        # Dokładnie to, co złapie LINK=$(sejfik send ...).
        self.assertEqual("https://sejfik.example/s/abcdef1234567890", wynik.stdout.strip())
        self.assertIn("Przesyłka gotowa", wynik.stderr)

    def test_plik_naprawde_dociera_w_multipart(self):
        plik = Path(self.home.name) / "zrzut.png"
        plik.write_bytes(b"\x89PNG-TRESC-PLIKU")
        self._run(["send", str(plik), "--note", "opis"])

        wyslane = FakeSejfik.last_upload
        self.assertIn(b"PNG-TRESC-PLIKU", wyslane)
        self.assertIn(b'name="files[]"; filename="zrzut.png"', wyslane)
        self.assertIn(b"opis", wyslane)

    def test_opcje_ida_do_serwera(self):
        plik = Path(self.home.name) / "a.png"
        plik.write_bytes(b"x")
        self._run(["send", str(plik), "--hours", "1", "--downloads", "1", "--length", "48"])

        wyslane = FakeSejfik.last_upload
        for oczekiwane in (b'name="hours"', b'name="downloads"', b'name="length"', b"48"):
            self.assertIn(oczekiwane, wyslane)

    def test_bez_niczego_nie_wysyla(self):
        wynik = self._run(["send"])
        self.assertEqual(2, wynik.returncode)
        self.assertIn("nie ma czego wysłać", wynik.stderr)

    def test_brakujacy_plik_mowi_ktory(self):
        wynik = self._run(["send", "/nie/ma/takiego.png"])
        self.assertEqual(2, wynik.returncode)
        self.assertIn("nie ma pliku", wynik.stderr)

    def test_uzywa_klucza_przesylek_a_nie_tokenu_agenta(self):
        # Token agenta nie ma prawa wysyłać przesyłek i odwrotnie.
        plik = Path(self.home.name) / "a.png"
        plik.write_bytes(b"x")
        os.environ["SEJFIK_SEND_TOKEN"] = "token-testowy"  # to jest token AGENTA

        wynik = self._run(["send", str(plik)])

        self.assertEqual(2, wynik.returncode)
        self.assertIn("klucza przesyłek", wynik.stderr)

    def test_brak_klucza_mowi_gdzie_go_wziac(self):
        os.environ.pop("SEJFIK_SEND_TOKEN")
        plik = Path(self.home.name) / "a.png"
        plik.write_bytes(b"x")

        wynik = self._run(["send", str(plik)])

        self.assertEqual(2, wynik.returncode)
        self.assertIn("klucze przesyłek", wynik.stderr)

    def test_plik_klucza_czytelny_dla_innych_jest_odrzucany(self):
        os.environ.pop("SEJFIK_SEND_TOKEN")
        sejfik.SEND_TOKEN_FILE.write_text("klucz-przesylek")
        sejfik.SEND_TOKEN_FILE.chmod(0o644)

        with self.assertRaises(sejfik.SejfikError) as ctx:
            sejfik.read_send_token()
        self.assertIn("chmod 600", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
