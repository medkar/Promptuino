// HC-SR04 + buzzer : alarme de proximite.

const int TRIG = 8;
const int ECHO = 9;
const int BUZZ = 7;

void setup() {
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  pinMode(BUZZ, OUTPUT);
}

long readDistance() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  long d = pulseIn(ECHO, HIGH);
  return d / 58;
}

void loop() {
  long cm = readDistance();
  if (cm < 20) tone(BUZZ, 1000, 100);
  delay(100);
}

/* <<< fn-1_wiring >>>
component: hcsr04 ; ref: U1 ; pins: VCC=5V, TRIG=D8, ECHO=D9, GND=GND
component: buzzer ; ref: B1 ; pins: +=D7, -=GND
<<< end >>> */
