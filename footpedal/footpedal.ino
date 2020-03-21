#include <FastLED.h>
#include <Control_Surface.h>

HairlessMIDI_Interface midi;
using namespace MIDI_Notes;
NoteValueLED led = { LED_BUILTIN, note(C, 4) };


Array<CRGB, 8> leds = {};
constexpr uint8_t ledpin = 6;
NoteRangeFastLED<leds.length> midiled = {leds, note(C#, -2), CHANNEL_1};


#include <Arduino_Helpers.h> 
#include <AH/Hardware/Button.hpp>
 
Button pushbutton = {2};

 
void setup() {
  pinMode(ledPin, OUTPUT);
  
  FastLED.addLeds<NEOPIXEL, ledpin>(leds.data, leds.length);
  FastLED.setCorrection(TypicalPixelString);
  midiled.setBrightness(128);
  
  pushbutton.begin();
  Control_Surface.begin();
}

void loop() {
  static bool ledState = LOW;
  if (pushbutton.update() == Button::Falling) {
    ledState = !ledState;
    digitalWrite(ledPin, ledState ? HIGH : LOW);
  }
  Control_Surface.loop();
  FastLED.show();

}
