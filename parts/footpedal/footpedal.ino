// FastLED 3.10 and Control Surface 2.1 each define std::initializer_list for AVR, and
// FastLED.h's global `using fl::round` reaches Control Surface's cmath. So: FastLED's
// list alone (Control Surface skips its own under _INITIALIZER_LIST), Control Surface
// before the rest of FastLED, then Control Surface's FastLED LEDs, which Control_Surface.h
// includes only when FastLED came first. The versions are pinned in firmware.json.
#include <crgb.h>  // a header at FastLED's root, so arduino-cli puts FastLED on the include path
#include <fl/stl/initializer_list.h>
#define _INITIALIZER_LIST
#include <Control_Surface.h>
#include <FastLED.h>
#include <MIDI_Inputs/LEDs/NoteCCKPRangeFastLED.hpp>

HairlessMIDI_Interface midi;

// Notes 1 to 6, C#-2 to F#-2 where C-2 is note 0; Control Surface counts from C-1 = 0.
Array<CRGB, 8> leds = {};
#define ledpin 6
NoteRangeFastLED<leds.length> midiled = {leds, MIDI_Notes::Db[-1]};

NoteButton b1 = {2, {MIDI_Notes::Db[-1], Channel_1}};
NoteButton b2 = {3, {MIDI_Notes::D[-1], Channel_1}};
NoteButton b3 = {4, {MIDI_Notes::Eb[-1], Channel_1}};
NoteButton b4 = {5, {MIDI_Notes::E[-1], Channel_1}};
NoteButton b5 = {8, {MIDI_Notes::F[-1], Channel_1}};
NoteButton b6 = {7, {MIDI_Notes::Gb[-1], Channel_1}};

void setup() {
  FastLED.addLeds<NEOPIXEL, ledpin>(leds.data, leds.length);
  FastLED.setCorrection(TypicalPixelString);
  midiled.setBrightness(128);
  Control_Surface.begin();
}

void loop() {
  Control_Surface.loop();
  FastLED.show();
}
