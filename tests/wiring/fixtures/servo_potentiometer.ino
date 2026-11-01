// Servomoteur dont l'angle suit la position d'un potentiometre.

#include <Servo.h>

Servo myServo;
const int POT = A0;

void setup() {
  myServo.attach(11);
}

void loop() {
  int v = analogRead(POT);
  int angle = map(v, 0, 1023, 0, 180);
  myServo.write(angle);
  delay(15);
}

/* <<< fn-1_wiring >>>
component: potentiometer ; ref: P1 ; value: 10k ; pins: A=5V, W=A0, B=GND
component: servo ; ref: M1 ; pins: VCC=5V, GND=GND, SIG=D11
<<< end >>> */
