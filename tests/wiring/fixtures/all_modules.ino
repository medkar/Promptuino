// Fixture MVP3 — tous les types de composants supportes (vue d'ensemble visuelle).

#include <DHT.h>
#include <Servo.h>
#include <Wire.h>

DHT dht(2, DHT22);
Servo myServo;

void setup() {
  pinMode(13, OUTPUT);
  pinMode(7, OUTPUT);          // buzzer
  pinMode(8, OUTPUT);          // hcsr04 trig
  pinMode(9, INPUT);           // hcsr04 echo
  myServo.attach(11);
  Wire.begin();
  dht.begin();
}

void loop() {
  delay(100);
}

/* <<< fn-1_wiring >>>
component: dht22 ; ref: U1 ; pins: VCC=5V, DATA=D2, GND=GND
component: hcsr04 ; ref: U2 ; pins: VCC=5V, TRIG=D8, ECHO=D9, GND=GND
component: lcd_i2c ; ref: U3 ; address: 0x27 ; pins: VCC=5V, GND=GND, SDA=A4, SCL=A5
component: oled_ssd1306 ; ref: U4 ; address: 0x3C ; pins: VCC=5V, GND=GND, SDA=A4, SCL=A5
component: servo ; ref: M1 ; pins: VCC=5V, GND=GND, SIG=D11
component: buzzer ; ref: B1 ; pins: +=D7, -=GND
component: potentiometer ; ref: P1 ; value: 10k ; pins: A=5V, W=A0, B=GND
component: led ; ref: D1 ; color: green ; pins: A=D13, K=GND
<<< end >>> */
