# RobotHand - Dynamixel XL330-M288 Hand-Controller

Eine moderne, feature-reiche Benutzeroberfläche zur präzisen Steuerung einer 5-achsigen robotergestützten Hand (RobotHand). Das System basiert auf Python (Tkinter) und nutzt das offizielle Robotis Dynamixel SDK zur Steuerung von XL330-M288 Servomotoren.

---

## 🚀 Hauptmerkmale

* **Intuitives Dashboard**: Ein ansprechendes Dark-Mode-Interface mit klar strukturierten Kontrollkarten für jeden einzelnen Finger/Motor.
* **Mehrere Betriebsmodi**:
  * **Position Mode (Joint Mode)**: Präzise Winkelsteuerung.
  * **Velocity Mode (Wheel Mode)**: Kontinuierliche Rotation für spezielle Endeffektoren.
  * **Current-Based Position Mode (Soft-Robotic Mode)**: Kraftbegrenzte Positionssteuerung, ideal für sensibles Greifen ohne Beschädigung von Objekten.
* **Synchronisierte Steuerung**: Master-Slider zur simultanen Verstellung aller ausgewählten Motoren.
* **Präzise Mausradsteuerung**: Alle Schieberegler (für Positionen, Grenzwerte, Geschwindigkeiten und Master-Werte) können präzise über das Mausrad gesteuert werden, wenn sich der Mauszeiger darüber befindet. Um Doppeleffekte zu vermeiden, wird das Scrollen des gesamten Fensters währenddessen automatisch blockiert.
* **Echtzeit-Feedback & Sicherheit**:
  * Live-Anzeige von Stromstärke (Stromverbrauch), Position und Temperatur.
  * Automatische Temperaturüberwachung mit Warnmeldungen bei Überhitzung.
  * Auslesen und Visualisieren von Hardware-Fehlercodes direkt aus dem EEPROM/RAM der Motoren.
* **Grasp- & Kontakterkennung**: Intelligente Kontakt- und Spike-Erkennung basierend auf Stromstärkeverläufen zum automatischen Stoppen oder Auslösen von Aktionen bei physischem Widerstand.
* **Kalibrierungssystem**: Einfache Definition von Nullpunkten und Bewegungsgrenzen für jeden Motor, um Überlastungen oder mechanische Beschädigungen zu verhindern.
* **Posen- & Sequenzmanager**:
  * Erstellen, Speichern und Laden von Handstellungen (Posen).
  * Vordefinierte Standard-Grasps (z. B. Edge-Grasp, Top-Grasp, Wall-Grasp).
  * Verketten von Posen zu komplexen Abläufen (Sequenzen) mit individuellen Wartebedingungen (Zeit- oder Kontaktgesteuert).
  * Zyklische (Loop) oder einmalige Ausführung der Sequenzen.

---

## 🛠 Hardware-Anforderungen

1. **Dynamixel XL330-M288 Servos**: 5 Motoren (IDs `0` bis `4`).
2. **Schnittstellenkonverter**: Robotis U2D2 (oder kompatibler USB-zu-RS485/TTL-Konverter).
3. **Stromversorgung**: Passende Stromquelle für die Servos (typischerweise 3.7V - 5.0V für XL330er).
4. **Verbindungskabel**: TTL-Verbindungskabel zur Verkettung der Motoren.

---

## 📦 Software-Anforderungen & Installation

### Voraussetzungen
Stellen Sie sicher, dass Python 3.x auf Ihrem System installiert ist. 

### Bibliotheken installieren
Installieren Sie das offizielle Dynamixel SDK über `pip`:

```bash
pip install dynamixel-sdk
```

*(Tkinter ist in der Standardbibliothek von Python enthalten und muss in der Regel nicht separat installiert werden.)*

### COM-Port & Baudrate konfigurieren
Standardmäßig ist das Skript auf folgende Verbindungsparameter eingestellt:
* **Port**: `COM10`
* **Baudrate**: `115200`

Diese Werte können im Kopfbereich der Datei [motor_control.py](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/motor_control.py) angepasst werden:
```python
COM_PORT = "COM10"
BAUDRATE = 115200
MOTOR_IDS = [0, 1, 2, 3, 4]
```

---

## 📂 Projektstruktur & Konfigurationsdateien

Das Projekt ist modular aufgebaut und speichert Kalibrierungs- und Konfigurationsdaten in strukturierten JSON-Dateien:

* 📄 [motor_control.py](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/motor_control.py): Das Hauptskript mit der Steuerungslogik und der Tkinter-Benutzeroberfläche.
* ⚙️ [calibration.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/calibration.json): Speichert die definierten Nullpunkte (`calib_zero`) und die maximal zulässigen Bewegungsgrenzen (`calib_limit`) pro Motor.
* 🏷️ [motor_names.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/motor_names.json): Enthält die benutzerdefinierten Bezeichnungen der Motoren (z. B. "Daumen-MCP", "Daumen-ALL").
* 💾 [poses.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/poses.json): Datenbank der erstellten Handstellungen und Grasp-Konfigurationen.
* 🎬 [sequences.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/sequences.json): Enthält gespeicherte Bewegungsabläufe mit ihren Frames und Übergangsbedingungen.
* 🖥️ [window_layout.json](file:///c:/Users/miyan/Downloads/Robothand/RobotHand/window_layout.json): Merkt sich die Fenstergröße, Position und den Theme-Status (Dark/Light Mode) beim Schließen der Anwendung.

---

## 📖 Bedienungsanleitung

### 1. Anwendung starten
Führen Sie das Hauptskript aus:
```bash
python motor_control.py
```

### 2. Kalibrierung durchführen
* Bringen Sie die Motoren manuell oder per Regler in die gewünschte Nullstellung (z. B. voll geöffnet). Klicken Sie auf **"Zero"** beim jeweiligen Motor.
* Bewegen Sie die Motoren an das sichere mechanische Limit (z. B. voll geschlossen). Klicken Sie auf **"Limit"** beim jeweiligen Motor.
* Klicken Sie oben auf **"Save Calibration"**, um die Einstellungen dauerhaft zu sichern. Die Steuerung verhindert nun automatisch das Überschreiten dieser Grenzwerte.

### 3. Posen erstellen
* Stellen Sie die Finger in eine gewünschte Greif-Position.
* Geben Sie im rechten Panel unter *Poses* einen Namen ein und klicken Sie auf **"Save Pose"**. Diese Pose ist fortan in der Dropdown-Liste verfügbar.

### 4. Sequenzen programmieren
* Wählen Sie eine Pose aus der Liste.
* Wählen Sie die Wartebedingung für diesen Schritt:
  * **Time**: Wartet eine definierte Zeit in Millisekunden (z. B. 1000 ms).
  * **Grasp (Kontakt)**: Wartet, bis die Sensoren physischen Kontakt (Anstieg der Stromstärke) registrieren oder ein Timeout abgelaufen ist.
* Klicken Sie auf **"Add to Seq"**, um den Schritt anzuhängen.
* Sortieren Sie die Schritte nach Bedarf mit **"Up"** / **"Down"** und speichern Sie die Sequenz unter einem individuellen Namen ab.
* Mit **"Start"** führen Sie den Ablauf aus.