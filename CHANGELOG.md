# Historia zmian

## 1.0.0 — 2026-09-29

Pierwsze wydanie. Wydzielone z repozytorium Sejfika, gdzie żyło jako
jednoplikowy `tools/sejfik-run`.

- `run` — wstrzykuje sekrety do zmiennych środowiskowych procesu potomnego
  albo na jego standardowe wejście. Kilka sekretów w jednym wywołaniu.
- `inject` — wypełnia szablon konfiguracji; zapis atomowy, prawa 600.
- `read` — wypisuje sekret na standardowe wyjście, ale odmawia, gdy
  wyjściem jest terminal.
- `whoami` — sprawdza token bez dotykania sekretów.
- Instalator z weryfikacją SHA-256.

Zgodność wstecz: `sejfik-run --ref REF --env NAZWA -- polecenie` nadal
działa przez dowiązanie o tej nazwie.
