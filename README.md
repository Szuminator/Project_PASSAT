# PASSAT — GroqCloud, Gemini i tryb offline

Passat to desktopowy asystent samochodowy w Pythonie i PySide6. Aplikacja ma
animowany rdzeń, prosty czat, ograniczoną historię rozmowy i wymienne źródło
odpowiedzi. Obecnie dostępne są GroqCloud, opcjonalne Gemini i podstawowy tryb
offline. Mikrofon, trwała pamięć, wyszukiwanie internetowe, GPS i integracja z
samochodem nie są podłączone.

## Struktura

```text
Project_PASSAT/
├── main.py                       # okno PySide6, czat i praca w tle
├── core_widget.py                # animowany rdzeń
├── passat/
│   ├── assistant.py              # historia, osobowość i awaryjny fallback
│   ├── models.py                 # wspólne typy wiadomości i odpowiedzi
│   ├── prompts.py                # instrukcja osobowości
│   ├── settings.py               # odczyt ustawień i .env
│   └── providers/
│       ├── base.py                # wspólny kontrakt i błędy dostawców
│       ├── factory.py             # wybór dostawcy AI albo offline
│       ├── gemini.py              # opcjonalna integracja Google Gen AI SDK
│       ├── groq.py                # integracja z GroqCloud
│       └── offline.py             # proste odpowiedzi bez modelu
├── tests/                         # testy bez klucza i żądań do API
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

GUI rozmawia wyłącznie ze wspólnym `PassatAssistant`. Każdy dostawca przyjmuje
wiadomość, wspólną historię `ChatMessage` oraz instrukcję systemową. Dzięki temu
kolejni dostawcy mogą realizować ten sam kontrakt bez zmian w oknie czatu.

## Wymagania

- Windows 10/11
- Python 3.13
- Klucz wybranego dostawcy jest opcjonalny — bez niego działa tryb offline.

## Instalacja

Otwórz PowerShell w katalogu projektu:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Jeśli PowerShell blokuje aktywację środowiska, pomiń ją i użyj jego interpretera:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Do uruchomienia testów doinstaluj zależności deweloperskie:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## GroqCloud (domyślnie)

1. Utwórz klucz API w [konsoli GroqCloud](https://console.groq.com/keys).
2. Skopiuj przykład konfiguracji i otwórz lokalny plik `.env`:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Uzupełnij klucz w `.env` obok `main.py`:

   ```dotenv
   PASSAT_PROVIDER=groq
   GROQ_API_KEY=tu_wklej_swoj_klucz
   PASSAT_GROQ_MODEL=qwen/qwen3.8-27b
   ```

   `.env` jest wykluczony z Git. Nie wpisuj prawdziwego klucza do kodu ani
   wiadomości. Bez klucza aplikacja uruchomi się w trybie offline.

Model `qwen/qwen3.8-27b` jest obecnie wymieniony w [katalogu modeli Groq](https://console.groq.com/docs/models)
i w tabeli limitów bezpłatnego [planu GroqCloud](https://console.groq.com/docs/rate-limits).
Dokumentacja modelu wskazuje obsługę wielojęzyczną, przydatną do rozmowy po
polsku. Groq oznacza go jako **Preview**, więc może zostać zmieniony lub
wycofany. Nazwa modelu pozostaje konfigurowalna przez `PASSAT_GROQ_MODEL`.
Limity Free obowiązują i mogą się zmieniać; sprawdź je w dokumentacji i swoim koncie.
Passat nie przełącza się na płatne plany ani endpointy.

Oficjalny SDK ma automatyczne ponowienia wyłączone w Passacie. Przy HTTP 429
aplikacja wykona najwyżej jedną dodatkową próbę, jeśli serwer poda
`Retry-After` nie dłuższy niż 15 sekund; w przeciwnym razie pokaże czas
oczekiwania. Timeout odpowiedzi wynosi 60 sekund i nie blokuje GUI.

## Gemini (opcjonalnie)

1. Utwórz klucz w [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Zmień dostawcę i wpisz klucz w lokalnym `.env`:

   ```dotenv
   PASSAT_PROVIDER=gemini
   GEMINI_API_KEY=tu_wklej_swoj_klucz
   PASSAT_GEMINI_MODEL=gemini-3.8-flash
   ```

   `.env` jest wykluczony z Git. Nie wklejaj klucza do kodu, README ani zgłoszeń.

Jeśli chcesz uruchamiać testy Gemini, zainstaluj również `requirements-dev.txt`.
Domyślnym modelem Gemini jest `gemini-3.8-flash`, widoczny w aktualnym
[katalogu modeli Google](https://ai.google.dev/gemini-api/docs/models) i z
bezpłatnym poziomem dla wejścia i wyjścia. Dostępność konkretnego modelu oraz
limity zależą od konta i projektu: sprawdź, czy model jest dostępny w AI Studio,
przetestuj go tam, a aktywne limity zobacz w panelu **Rate limits**. Aktualne
warunki i limity bezpłatne opisuje [cennik Gemini API](https://ai.google.dev/gemini-api/docs/pricing),
a [dokumentacja limitów](https://ai.google.dev/gemini-api/docs/rate-limits)
wyjaśnia, jak je sprawdzić. Nie zakładaj, że limit jest nieograniczony. Możesz
zmienić model w `PASSAT_GEMINI_MODEL`, bez edycji kodu.

Bezpłatny poziom ma ograniczenia. Według informacji Google treści wysyłane w
ramach bezpłatnego poziomu mogą być używane do ulepszania produktów Google;
nie wysyłaj tam danych wrażliwych. Jeśli klucz należy do projektu z włączonym
płatnym rozliczaniem, mogą mieć zastosowanie opłaty. Passat nie konfiguruje
płatności, nie zmienia modelu automatycznie i nie używa narzędzi takich jak
Google Search grounding. Każde żądanie ma limit oczekiwania 120 sekund i
ustawiony niski poziom `thinking`, co pomaga ograniczyć opóźnienie w zwykłej
rozmowie. Przy HTTP 503 SDK ponawia żądanie najwyżej raz, z krótkim odstępem;
pozostałe błędy nie są automatycznie ponawiane.

## Uruchomienie i testy

```powershell
python main.py
```

Testy lokalne nie potrzebują klucza i nie łączą się z API:

```powershell
python -m pytest -q
```

Pole wysyła wiadomość przyciskiem **WYŚLIJ** lub klawiszem **Enter**. Podczas
oczekiwania interfejs pokazuje **MYŚLĘ**; odpowiedź dostawcy AI kończy się
statusem **GOTOWY**, a odpowiedź offline — **OFFLINE**. Początkowy opis wybranego
dostawcy mówi tylko, że jest skonfigurowany. Aplikacja pokazuje powodzenie
połączenia dopiero po otrzymaniu pierwszej odpowiedzi.

Jeśli nie ma klucza albo dostawca AI zwróci błąd, Passat przełącza pojedynczą
wiadomość na prosty tryb offline i pokazuje informację o użytym dostawcy. Tryb
offline rozpoznaje powitania, pytania o tożsamość Passata i tryb działania;
potrafi też podać lokalną godzinę. Pozostałych odpowiedzi nie generuje model
językowy.

## Rozwiązywanie problemów

- **Passat działa offline:** sprawdź, czy `.env` znajduje się obok `main.py`,
  czy `PASSAT_PROVIDER=groq` i czy `GROQ_API_KEY` jest ustawiony. Gemini wymaga
  `PASSAT_PROVIDER=gemini` oraz `GEMINI_API_KEY`.
- **Błąd autoryzacji:** utwórz lub sprawdź klucz u wybranego dostawcy. Aplikacja
  nie pokazuje surowych błędów API ani klucza.
- **Limit Groq:** sprawdź limity Free w konsoli GroqCloud; aplikacja respektuje
  `Retry-After` i nie wykonuje nieograniczonych ponowień.
- **Model niedostępny:** wybierz model dostępny dla projektu i ustaw go w
  `PASSAT_GROQ_MODEL` albo `PASSAT_GEMINI_MODEL`.
- **Zależności:** uruchom `python -m pip install -r requirements-dev.txt`
  w aktywnym środowisku `.venv`. Bez aktywacji:

  ```powershell
  .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
  ```
