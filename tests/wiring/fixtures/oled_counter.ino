// Compteur de pressions de bouton affiche sur un OLED SSD1306 I2C.

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

Adafruit_SSD1306 display(128, 64, &Wire, -1);

const int BTN = 2;
int count = 0;
int lastState = HIGH;

void setup() {
  pinMode(BTN, INPUT_PULLUP);
  Wire.begin();
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
}

void loop() {
  int state = digitalRead(BTN);
  if (state == LOW && lastState == HIGH) count++;
  lastState = state;

  display.clearDisplay();
  display.setCursor(0, 0);
  display.print("Count: ");
  display.println(count);
  display.display();
  delay(20);
}

/* <<< fn-1_wiring >>>
component: oled_ssd1306 ; ref: U1 ; address: 0x3C ; pins: VCC=5V, GND=GND, SDA=A4, SCL=A5
component: button ; ref: S1 ; pull: internal ; pins: A=D2, B=GND
<<< end >>> */
