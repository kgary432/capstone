#include <Adafruit_NeoPixel.h>

#define LED_PIN 6
#define NUM_LEDS 30

Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

void setup() {
  Serial.begin(115200);
  strip.begin();
  strip.show();
}

void loop() {
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    int bass, mid, treble, beat;
    if (sscanf(input.c_str(), "%d,%d,%d,%d", &bass, &mid, &treble, &beat) == 4) {
      uint32_t color = strip.Color(bass, mid, treble);
      for (int i = 0; i < NUM_LEDS; i++) {
        strip.setPixelColor(i, color);
      }

      // Add beat flash effect
      if (beat == 1) {
        strip.setBrightness(255);
      } else {
        strip.setBrightness(150);
      }

      strip.show();
    }
  }
}
