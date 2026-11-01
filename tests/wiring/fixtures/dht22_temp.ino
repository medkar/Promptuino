// Capteur DHT22 + LED rouge d'alerte si T > 30°C.

#include <DHT.h>

DHT dht(2, DHT22);

void setup() {
  pinMode(13, OUTPUT);
  Serial.begin(9600);
  dht.begin();
}

void loop() {
  float t = dht.readTemperature();
  digitalWrite(13, t > 30.0);
  delay(2000);
}

/* <<< fn-1_wiring >>>
component: dht22 ; ref: U1 ; pins: VCC=5V, DATA=D2, GND=GND
component: led ; ref: D1 ; color: red ; pins: A=D13, K=GND
<<< end >>> */
