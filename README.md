# 🤖 RobotHand – Dynamixel XL330-M288 Hand-Controller

[![Python Version](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-Tkinter-lightgrey.svg)](https://docs.python.org/3/library/tkinter.html)
[![Dynamixel SDK](https://img.shields.io/badge/SDK-Dynamixel_Protocol_2.0-red.svg)](https://emanual.robotis.com/docs/en/software/dynamixel/dynamixel_sdk/overview/)
[![Platform Support](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-brightgreen.svg)](https://github.com/Robotis-GIT/DynamixelSDK)

Diese Software bietet eine moderne, intuitive Benutzeroberfläche zur präzisen Steuerung einer robotergestützten Hand (**RobotHand**). Sie wurde speziell für das Projekt "Soft!-robotic Hands" (SoSe 2026) konzipiert und ermöglicht eine elastische, kraftgesteuerte Seilzug- und Fingersteuerung basierend auf **Dynamixel XL330-M288** Servomotoren.

Die Architektur folgt dem MVC-Muster (Model-View-Controller) mit einem dedizierten Hintergrund-Thread zur seriellen Kommunikation. Dies sorgt für eine flüssige, verzögerungsfreie Benutzeroberfläche und schützt die Hardware durch kontinuierliche Telemetrieüberwachung.

---

## 🚀 Hauptmerkmale

### 1. Betriebsmodi
* **Position Mode (Joint Mode)**: Klassische Winkelregelung der Servos.
* **Velocity Mode (Wheel Mode / Endlos-Rotation)**: Endlose Drehung mit kontinuierlicher Geschwindigkeitsregelung (z. B. für Spindeln oder Seilwickler).
* **Current-Based Position Mode (Soft-Robotic Mode)**: Positionsregelung mit aktiver Strombegrenzung. Ermöglicht ein nachgiebiges Greifen und schützt die mechanischen Seilzüge vor dem Reißen.

### 2. Live-Telemetrie & Überlastungsschutz (Hardware-Schutz)
* **Live-Stromaufzeichnung**: Grafische Echtzeitüberwachung des Motorstroms (mA) aller 5 Kanäle im unteren Plot-Bereich.
* **Temperatur-Wächter**: Permanent überwachte Motortemperaturen. Überschreitet ein Motor $55\text{ }^\circ\text{C}$, färbt sich die Anzeige rot und ein Warnbanner wird eingeblendet.
* **Hardware-Diagnose**: Direktes Auslesen des EEPROM-Fehlerregisters der XL330-Servos (z. B. Overload, Overheating) mit optischem Statussymbol ($\checkmark$ oder $\text{Warning}$).
* **EMERGENCY STOP**: Sofortige Deaktivierung des Drehmoments (Torque OFF) für alle Motoren über eine dedizierte Taste.

### 3. Kontakt- & Greiferkennung
* **Flankenerkennung (Rate-of-Change)**: Erkennt plötzliche Strompeaks bei physischem Widerstand.
* **Gleitender Durchschnitt**: Rauschfreie Berechnung über ein konfigurierbares Messfenster (`CONTACT_AVG_WINDOW = 5`), um Fehlauslösungen zu vermeiden.
* **Indikatoren**: Dreistufiger Status pro Motor (● `No Contact` / ● `Approaching` (Annäherung) / ● `Contact!` (Kontakt)).

---

## 📸 Benutzeroberfläche

Die GUI folgt einem aufgeräumten, minimalistischen Design, um den Fokus auf die Steuerung zu legen:
* **Dark & Light Mode**: Ein augenfreundliches Dark Theme (`#0c0c14` Hintergrund) sowie ein sauberer Light Mode (`#f8fafc` Slate-Hintergrund) mit Farbakzenten zur klaren Unterscheidung der Motorkanäle.
* **Zweisprachiges Design**: Die Benutzeroberfläche ist auf Englisch gehalten (Industriestandard), während detaillierte Tooltips (Hover-Erklärungen) auf Deutsch eine schnelle Einarbeitung im Labor gewährleisten.
* **Übersichtliches Layout**: Klar strukturierte Motorkarten mit abgerundeten Abständen, frei von störenden Rahmenlinien.
* **Intuitive Bedienung**: Alle Regler (Positionen, Strombegrenzungen, Geschwindigkeiten, Master-Werte) können präzise mit dem Mausrad verstellt werden. Das Scrollen des Hauptfensters wird währenddessen intelligent blockiert.
* **Undo-Funktion (Rückgängig)**: Manuelle Slider-Bewegungen können per Knopfdruck oder via `Strg + Z` rückgängig gemacht werden.

---

## 🎓 Ausrichtung auf das Robotik-Projekt (SoSe 2026)

* **Opponierbarkeit**: Unterstützung von bis zu 5 Motoren (IDs `0` bis `4`). Perfekt ausgelegt für vier Finger und einen Daumen.
* **Passive Nachgiebigkeit**: Durch den Current-Based Position Mode geben die Finger bei mechanischem Widerstand elastisch nach, was ein feinfühliges Greifen zerbrechlicher Objekte ermöglicht.
* **Pflicht-Grasps**: Die geforderten Demogriffe (**Edge-Grasp**, **Top-Grasp** und **Wall-Grasp**) sowie die Grundstellung **Hand Open** sind direkt im System als Vorlagen integriert.
* **Wiederholbarkeit (Ablaufsteuerung)**: Der integrierte Sequenz-Player ermöglicht die automatische, fehlerfreie Wiederholung von Greif- und Ablagevorgängen (z. B. exakt 3 Durchläufe für die Projektdemonstration).

---

## 🛠 Hardware-Verkabelung

```text
+------------+     USB     +----------------+   Half-Duplex   +----------+
|  Steuer-   | <=========> |  Robotis U2D2  | <-------------> | Motor #0 | (Daumen-MCP)
|    PC      |             |   Konverter    |   TTL-Bus       +----------+
+------------+             +----------------+                      |
                                   ^                               V
                                   | External Power           +----------+
                                   +--- (5.6V)         | Motor #1 | (Daumen-ALL)
                                                              +----------+
                                                                   |
                                                                   V
                                                                  ...
                                                              +----------+
                                                              | Motor #4 | (Motor 4)
                                                              +----------+
```

---

## 📦 Installation & Setup

1. **Python 3** herunterladen und installieren.
2. Das offizielle **Robotis Dynamixel SDK** sowie **Pillow** (für Graphen-Bilder) installieren:
   ```bash
   pip install dynamixel-sdk pillow
   ```
3. Die Hardware-Konfigurationen in der Datei [config.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/config.json) anpassen (COM-Port, Baudrate und verwendete Motor-IDs):
   ```json
   {
     "hardware": {
       "port": "COM10",
       "baudrate": 115200
     },
     "motors": {
       "ids": [0, 1, 2, 3, 4]
     }
   }
   ```

---

## 📖 Kurzanleitung zur Bedienung

### 1. Verbindung herstellen
* Starte die GUI mit `python motor_control.py` (oder direkt über `python main.py`).
* Klicke oben links auf **"Connect"**. Der Status wechselt auf ● **ONLINE**.

### 2. Finger kalibrieren
* Fahre einen Finger manuell (über die Benutzeroberfläche, im Endlos-Modus oder bei ausgeschaltetem Torque von Hand) in die offene Position. Klicke auf **"Set Zero"**.
* Fahre denselben Finger in die voll geschlossene Greifposition. Klicke auf **"Set Limit"**.
* Drücke auf das Speichern-Symbol, um die Kalibrierung in die `calibration.json` zu schreiben.
* *Hinweis*: Nach der Kalibrierung wechselt der Motor automatisch in den sicheren *Current-Based Position* Modus. Der Slider skaliert nun linear zwischen 0 % (Zero) und 100 % (Limit).

### 3. Posen speichern und Sequenzen abspielen
* **Pose anlegen**: Bringe die Finger in Position, vergib oben rechts einen Namen (z. B. "Greif-Bereit") und klicke auf das Disketten-Symbol.
* **Schritt hinzufügen**: Wähle eine Pose im Dropdown, stelle die Wartebedingung ein (`ms` für Zeitdauer) und klicke auf **"+ Sequence"**.
* **Sequenz bearbeiten**: Klicke doppelt auf einen Eintrag in der Liste der Ablaufsteuerung, um den Schritt-Editor to öffnen. Hier können Geschwindigkeiten und Greifkräfte pro Finger separat justiert werden.
* **Ablauf starten**: Klicke auf den blauen **"Start"**-Button.

---

## 📂 Projektstruktur & Dateien

Das Projekt ist modular aufgebaut:

### Python-Module
* **[motor_control.py](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/motor_control.py)**: Start-Wrapper (aus Abwärtskompatibilität).
* **[main.py](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/main.py)**: Zentraler App-Controller, der die GUI und den Hintergrundthread verbindet.
* **[ui.py](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/ui.py)**: Tkinter-UI-Definitionen, Grafik-Rendern, Styles.
* **[hardware.py](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/hardware.py)**: Thread-Manager für serielle Bus-Kommunikation und Datenabfragen.
* **[models.py](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/models.py)**: Thread-sichere Datenmodelle (`MotorState`, `RobotState`).
* **[calibration.py](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/calibration.py)**: Logik zur Winkelberechnung und Nullpunkt-Ausrichtung.
* **[sequences.py](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/sequences.py)**: Steuerung des Sequenz-Ablauf-Players.
* **[test_app.py](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/test_app.py)**: Automatisierte Unit-Tests. Führe sie aus mit:
  ```bash
  python -m unittest test_app.py
  ```

### Datenspeicherungen (JSON)
* **[config.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/config.json)**: Globale Hardware- und UI-Parameter.
* **[calibration.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/calibration.json)**: Ticks für den Nullpunkt (geöffnet) und das Limit (geschlossen) pro Motor ID.
* **[motor_names.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/motor_names.json)**: Anzeigenamen der Motoren.
* **[poses.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/poses.json)**: Gespeicherte Posen (Positionen, Stromgrenzen, Geschwindigkeiten).
* **[sequences.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/sequences.json)**: Gespeicherte Sequenzen und Abläufe.
