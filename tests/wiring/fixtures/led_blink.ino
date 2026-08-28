// LED clignotante D13 + bouton D2 — fixture de validation MVP1.

void setup() {
  pinMode(13, OUTPUT);
  pinMode(2, INPUT);
}

void loop() {
  digitalWrite(13, !digitalRead(2));
  delay(100);
}

/* <<< fn-1_wiring >>>
component: led ; ref: D1 ; color: red ; pins: A=D13, K=GND
component: button ; ref: S1 ; pins: A=D2, B=GND ; pull: external
<<< end >>> */
