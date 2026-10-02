# Historia zmian

## 1.2.0 — 2026-10-02

- `send` — wysyła plik, zrzut ekranu (`--screen`) albo obraz ze schowka
  (`--clipboard`) jako przesyłkę i wypisuje gotowy link. Zrzut robi
  pierwsze dostępne narzędzie: grim+slurp, gnome-screenshot, spectacle,
  maim, scrot, ImageMagick, screencapture. Link ląduje też w schowku,
  jeśli jest czym go tam wstawić.

Używa osobnego klucza (`~/.sejfik/send-token`, `SEJFIK_SEND_TOKEN`), który
umie wyłącznie utworzyć przesyłkę. Maszyna wysyłająca zrzuty nie ma powodu
nosić klucza do haseł, a jeden klucz do wszystkiego oznaczałby dokładnie to.

Wymaga Sejfika z endpointem POST /api/transfers.

## 1.1.0 — 2026-09-29

Domknięcie cyklu życia hasła: dotąd klient umiał hasło wskazać i użyć,
ale nie stworzyć. Kończyło się to radą „wygeneruj sobie sam i wklej do
Sejfika", czyli sekret i tak szedł przez ludzkie ręce — a najbliższa
pokusa to poprosić model o wymyślenie hasła, które wtedy zostaje
w transkrypcie na zawsze.

- `create-login` — zakłada wpis z hasłem wygenerowanym po stronie Sejfika.
- `rotate-password` — nowe hasło dla istniejącego wpisu; poprzednie
  zostaje w historii. Przyjmuje numer wpisu albo referencję.

Oba wypisują referencję na standardowe wyjście, a opis dla człowieka na
strumień błędów, więc `REF=$(sejfik create-login --name X)` łapie samą
referencję.

Wymaga Sejfika z endpointami /api/vault/agent/items.

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
