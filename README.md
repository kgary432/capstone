# capstone

to run:

1. Connect microcontroller to computer, (In Arduino IDE) check port number and update in main.py if necessary,
   then compile and upload firmware to microcontroller.

2. Close Arduino IDE, Arduino cannot handle more than one attempted input so the Arduino IDE must be fully killed for the main script to work. Otherwise you will get a busy error message or similar.

3. type the following and check that you can see main.py in the list. if not you can use the command 'cd ..' to move up a level, or 'cd nameOfFolder' to enter a folder

```bash
ls
```

4. start the venv by typing:

```bash
source .venv/bin/activate
poetry run python3 main.py
```

to start the program, then control + C to end it when you're done.

5. to leave the venv, type

```bash
deactivate
```
