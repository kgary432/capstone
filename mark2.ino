// Arduino LED control via Serial input
// Turns on pink LED when '1' is pressed, blue LED when '2' is pressed

const int pinkLED = 8;   // Pin for pink LED
const int blueLED = 9;  // Pin for blue LED
const int pink2LED = 10; // Pin for second pink LED

void setup() {
  pinMode(pinkLED, OUTPUT);
  pinMode(blueLED, OUTPUT);
  pinMode(pink2LED, OUTPUT);
  
  // Start serial communication
  Serial.begin(9600);
  Serial.println("Press 1 for pink LED, 2 for blue LED");
}

void loop() {
  // Check if data is available in Serial input
  if (Serial.available() > 0) {
    char input = Serial.read();  // Read a single character
    // Turn off both LEDs before switching
    digitalWrite(pinkLED, LOW);
    digitalWrite(blueLED, LOW);
    digitalWrite(pink2LED, LOW);

    // Handle key presses
    if (input == '1') {
      digitalWrite(pinkLED, HIGH);
      Serial.println("Pink LED ON");
      delay(1000);
    } 
    else if (input == '2') {
      digitalWrite(blueLED, HIGH);
      Serial.println("Blue LED ON");
      delay(1000);

    } 
    else if (input == '3') {
      digitalWrite(pink2LED, HIGH);
      Serial.println("Pink 2 LED ON");
      delay(1000);
    } 
    else {
      Serial.println("Invalid input. Press 1, 2, or 3.");
    }
    Serial.println(input);
  } 
}

