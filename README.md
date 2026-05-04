# capstone

mark2.ino is final firmware for this project, anything else is experimental.

to run:

1. Connect microcontroller to computer, (In Arduino IDE) check port number and update in main.py if necessary,
   then compile and upload firmware to microcontroller.
2. Close Arduino IDE, Arduino cannot handle more than one attempted input so the Arduino IDE must be fully killed for the main script to work. Otherwise you will get a busy error message or similar.
3. Open main.py
4. poetry run python main.py, to start the program, then control + C to end process
5. If any errors occur they are likely with poetry. Double check Python version is compatible and all dependencies are installed.
