#include <Control_Surface.h>

HairlessMIDI_Interface midi;
using namespace MIDI_Notes;
NoteValueLED led = { LED_BUILTIN, note(C, 4) };

// Include the library
#include <Arduino_Helpers.h>
 
#include <AH/Hardware/Button.hpp>
 
// Create a Button object that reads a push button connected to pin 2:
Button pushbutton = {2};
 
// The pin with the LED connected:
const pin_t ledPin = LED_BUILTIN;
 
void setup() {
  pinMode(ledPin, OUTPUT);
  pushbutton.begin();
  // You can invert the input, for use with normally closed (NC) switches:
  // pushbutton.invert();
  Control_Surface.begin();
}
 
void loop() {
  static bool ledState = LOW;
  // Read the digital input, debounce the signal, and check the state of
  // the button:
  if (pushbutton.update() == Button::Falling) {
    ledState = !ledState; // Invert the state of the LED
    // Update the LED with the new state
    digitalWrite(ledPin, ledState ? HIGH : LOW);
  }
  Control_Surface.loop(); 
}
