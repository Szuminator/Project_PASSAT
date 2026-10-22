# PASSAT — etap 1

Minimalny szkielet desktopowego asystenta w Pythonie. Na tym etapie aplikacja
pokazuje animowany rdzeń i pozwala przełączać jego stany testowe. Nie łączy się
z internetem i nie używa mikrofonu ani modelu AI.

## Struktura

```text
Project_PASSAT/
├── main.py          # okno, przyciski stanów i uruchomienie aplikacji
├── core_widget.py   # rysowanie i animacja świetlnego rdzenia
├── requirements.txt # zależność PySide6
└── README.md        # instrukcja instalacji i obsługi
```

## Wymagania

- Windows 10 lub 11
- Python 3.13

## Instalacja i uruchomienie w Windows

Otwórz PowerShell w katalogu projektu i wykonaj:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Jeśli PowerShell blokuje aktywację środowiska, można pominąć aktywację i
uruchamiać polecenia przez interpreter środowiska:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Obsługa

Po uruchomieniu zobaczysz nazwę PASSAT, status **GOTOWY** i animowany rdzeń.
Przyciski pod rdzeniem przełączają stany **GOTOWY**, **SŁUCHAM**, **MYŚLĘ**,
**MÓWIĘ** i **OFFLINE**. Przycisk **ZAMKNIJ PASSATA** zamyka okno i kończy
pracę aplikacji.

Animacja działa lokalnie przez `QPainter` i `QTimer`. `main.py` zawiera okno
oraz obsługę stanów, a `core_widget.py` samodzielnie rysuje i animuje rdzeń.
