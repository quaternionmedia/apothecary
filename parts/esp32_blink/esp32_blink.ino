// esp32_blink -- smoke-test firmware for an ESP32 dev board.
//
// Blinks the on-board LED and prints a heartbeat over serial so a fresh
// board/toolchain can be verified end to end: compile, upload, and read back.
// Most classic ESP32 devkits (DOIT, NodeMCU-32S, WROOM-32) wire the LED to
// GPIO 2; boards whose variant defines LED_BUILTIN use that instead.
//
// Identification protocol (what `apothecary firmware listen` and the /firmware
// page look for): print `apothecary <sketch>: hello` at boot and again every
// ANNOUNCE_EVERY beats, so a monitor that attaches late still learns which
// sketch is running without a reset.

#ifndef LED_BUILTIN
#define LED_BUILTIN 2
#endif

static const unsigned long PERIOD_MS = 500;
static const unsigned long ANNOUNCE_EVERY = 10;  // beats (~5 s at PERIOD_MS 500)

static void announce() {
  Serial.println("apothecary esp32_blink: hello");
  Serial.printf("chip: %s rev %d, %d core(s), %lu MHz, LED on GPIO %d\n",
                ESP.getChipModel(), ESP.getChipRevision(), ESP.getChipCores(),
                (unsigned long)ESP.getCpuFreqMHz(), LED_BUILTIN);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  delay(100);
  Serial.println();
  announce();
}

void loop() {
  static bool on = false;
  static unsigned long beats = 0;
  on = !on;
  digitalWrite(LED_BUILTIN, on ? HIGH : LOW);
  if (on) {
    Serial.printf("blink %lu\n", ++beats);
    if (beats % ANNOUNCE_EVERY == 0) {
      announce();
    }
  }
  delay(PERIOD_MS);
}
