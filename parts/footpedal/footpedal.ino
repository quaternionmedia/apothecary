#include <FastLED.h>
#include <Control_Surface.h>

HairlessMIDI_Interface midi;
using namespace MIDI_Notes;

Array<CRGB, 8> leds = {};
#define ledpin 6
NoteRangeFastLED<leds.length> midiled = {leds, note("C#", -2)};


#include <Arduino_Helpers.h> 
#include <AH/Hardware/Button.hpp>
 
NoteButton b1 = {2, { note("C#", -2), CHANNEL_1 }};
NoteButton b2 = {3, { note("D", -2), CHANNEL_1 }};
NoteButton b3 = {4, { note("D#", -2), CHANNEL_1 }};
NoteButton b4 = {5, { note("E", -2), CHANNEL_1 }};
NoteButton b5 = {6, { note("F", -2), CHANNEL_1 }};
NoteButton b6 = {7, { note("F#", -2), CHANNEL_1 }};

 
void setup() {
  pinMode(ledpin, OUTPUT);
  
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
    digitalWrite(LED_BUILTIN, ledState ? HIGH : LOW);
  }
  Control_Surface.loop();
  FastLED.show();

}
