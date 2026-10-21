# Instructions for Claude: set up the AsTeRICS face-tracking mouse on Ubuntu 26.04 (GNOME / Wayland)

Goal: on a fresh Ubuntu 26.04 machine with GNOME on Wayland, install the AsTeRICS Runtime
Environment (ARE) 4.3.0 and make its face-tracking mouse (XFaceTrackerMouse model) move the
real cursor, so it can be used with AsTeRICS Grid via hover (dwell) selection.

This was first done on 2026-10-21 on a ThinkPad Z16 (Ubuntu 26.04.1, GNOME 50.1, Java 25
preinstalled). The whole folder containing this file (`~/asterics`) must be copied to the new
machine, because the steps use the scripts in it:

| File | Purpose |
|---|---|
| `make_uinput_model.py` | Generates the modified ARE models from the stock `XFaceTrackerMouse.acs`. |
| `asterics_uinput_bridge.py` | OSC (UDP 57111) to uinput bridge via the ydotool daemon socket. |
| `start-facemouse.sh` | Launcher: uinput daemon, bridge, ARE with the modified model. |
| `README.md` | User-facing documentation of the result. Keep it with the install. |

## Two facts that drive every step

1. **The ARE needs Java 8.** Its Equinox 3.6 OSGi runtime depends on `javax.xml.bind` etc.
   On Java 11+ the grizzly web service bundle fails with "Missing Constraint", which kills
   the REST API (port 8081) and WebACS. Do not try newer Java. Keep the system default Java
   untouched; patch only the ARE start script.
2. **GNOME on Wayland ignores X11 cursor injection.** The ARE's Mouse plugin uses
   `java.awt.Robot` (XTest via XWayland). The X11-side pointer position still updates, so
   Java-level tests look successful while nothing moves on screen. Do not spend time on
   XTest; a virtual mouse through `uinput` (ydotool) works. The bridge in this folder
   converts the ARE's output to uinput.

## Steps

Commands marked **(user)** need sudo or a re-login, so ask the user to run them. In Claude Code
the user can run them with the `!` prefix so the output lands in the session.

### 1. Check the machine

```bash
cat /etc/os-release | head -3; dpkg --print-architecture; echo $XDG_SESSION_TYPE; java -version 2>&1 | head -1
```

Expect Ubuntu 26.04, amd64, `wayland`. Any preinstalled Java is fine; it stays the default.

### 2. Download and install the ARE

```bash
mkdir -p ~/Downloads/asterics && cd ~/Downloads/asterics
curl -sLO https://github.com/asterics/AsTeRICS/releases/download/4.3.0/asterics-are-4.3.0-ubuntu-22.04.deb
```

**(user)**

```bash
sudo apt-get install -y libhidapi-libusb0
sudo dpkg -i ~/Downloads/asterics/asterics-are-4.3.0-ubuntu-22.04.deb
```

The package has no Java dependency; its post-install prints a reminder about Java 8, creates a
menu entry, two udev rules (FS20, IrTrans), and moves models/profile/data/web to
`/var/opt/asterics-are/` (world-writable, so model files can be written without sudo).

### 3. Java 8 for the ARE only

**(user)**

```bash
sudo apt-get install -y openjdk-8-jre
sudo sed -i.bak 's|^java |/usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java |' /opt/asterics-are/app/start.sh
```

Verify: `grep -n '^/usr/lib/jvm' /opt/asterics-are/app/start.sh` shows line 49. Then launch the
ARE once in the background (`/opt/asterics-are/app/start.sh`), wait ~25 s and check:

```bash
curl -s http://localhost:8081/rest/runtime/model/state      # -> started
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8081/   # -> 200 (WebACS)
```

The only acceptable SEVERE line in the log is "IO Exception while handling ignore ports file".
Note: the stock autostart model begins face tracking immediately with the webcam.

### 4. uinput access

**(user)**

```bash
sudo apt-get install -y ydotool
sudo usermod -aG input $USER
```

The user must log out and back in (or reboot) before step 7 works. Verify afterwards with
`id -nG | grep -w input`. The package provides a per-user `ydotool.service`; the launcher starts
it on demand, and the socket appears at `$XDG_RUNTIME_DIR/.ydotool_socket`.

### 5. Generate the modified models

```bash
M=/var/opt/asterics-are/models
python3 -I ~/asterics/make_uinput_model.py            $M/XFaceTrackerMouse.acs $M/XFaceTrackerMouse_uinput.acs
python3 -I ~/asterics/make_uinput_model.py --hide-gui $M/XFaceTrackerMouse.acs $M/XFaceTrackerMouse_uinput_quiet.acs
```

What the generator does, in case it must be adapted:

- removes the `asterics.Mouse` component and all channels/events into it;
- adds **one** `asterics.OscOutClient` (Port 57111, PeerAddress 127.0.0.1, AddressCh1 `/dx`,
  AddressStringCh `/cmd`) and routes dx into CH1;
- routes dy through `asterics.DoubleToString` and `asterics.MultiSourceString` into the OSC
  string channel, merged with the existing `StringDispatcher` commands;
- adds dispatcher slots `@MOUSE:click,left` (from the dwell Timer) and `@MOUSE:action,toggle`
  (from the On/Off button);
- inserts the new components at the **front** of the component list (they must start before
  `Slider.1`, which sends its initial value immediately);
- sets `Decoration=true`, `AlwaysOnTop=false`, and shifts all panels down 400 units (10000-unit
  virtual screen) so the title bar does not cover the buttons; `--hide-gui` also sets every
  `displayGUI` to false.

Constraints learned the hard way: `OscOutClient` is a singleton (static instance), so a model
can have only one; every CH input triggers a send of all four channels, which is why dy goes as
text; never `pause` the model (the camera cannot be reopened), use stop/start.

### 6. Install the launcher in the app menu

```bash
chmod +x ~/asterics/start-facemouse.sh ~/asterics/asterics_uinput_bridge.py
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/asterics-facemouse.desktop <<EOF
[Desktop Entry]
Type=Application
Name=AsTeRICS Face Mouse
Comment=Head-controlled mouse (AsTeRICS face tracker via uinput bridge)
Exec=$HOME/asterics/start-facemouse.sh
Icon=/opt/asterics-are/asterics-are.png
Terminal=false
Categories=Utility;Accessibility;
EOF
update-desktop-database ~/.local/share/applications 2>/dev/null
```

Check that `Exec=` points at the real path of the launcher on the new machine.

### 7. Test (after the user's re-login)

Ask the user to start "AsTeRICS Face Mouse" from the menu or run `~/asterics/start-facemouse.sh`.
Expected: an ARE window at the right of the screen with Right / Double / Drag / On/Off / Menu
buttons, a Mouse Speed slider, a separate "Camera Mouse" preview with green dots on the face,
and the cursor following head movement. Dwelling still for about a second clicks.

Logs: `~/.local/state/asterics-facemouse/bridge.log` and `are.log`. The bridge prints each
command it receives (`cmd @MOUSE:click,left`), which confirms data is flowing.

Without a re-login the launcher reports "No uinput daemon socket". For a quick test before the
re-login, the user can start a temporary root daemon and stop it afterwards:

```bash
sudo systemd-run --unit=ydotoold-test /usr/bin/ydotoold --socket-path=/tmp/.ydotool_socket --socket-perm=0660 --socket-own=$(id -u):$(id -g)
# ... test ...
sudo systemctl stop ydotoold-test
```

### 8. AsTeRICS Grid

In Grid: **Opções de acesso** (input options) → mouse/touch entry → enable hover (dwell)
selection, about 1 to 1.5 s. Leave scanning, direction, Huffman and sequential access off.

## Diagnostics that proved useful

- Is the ARE sending? `tail -f ~/.local/state/asterics-facemouse/bridge.log`.
- Is uinput reaching the screen? With `YDOTOOL_SOCKET` set to the daemon socket:
  `ydotool mousemove -x 200 -y 0` must visibly move the cursor.
- Multi-monitor: the cursor continues from wherever it is; with external monitors the user may
  simply be watching the wrong screen. Test on a single screen first.
- Do not use `pkill -f <pattern>` from a shell whose own command line contains the pattern; it
  kills the shell. Use `pgrep -f '^python3 -I /path/script'` with an anchored pattern instead.
- GNOME blocks `org.gnome.Shell.Screenshot` for arbitrary callers, so cursor position cannot be
  verified from a script. Schedule visible tests with a delay and ask the user what they saw.

## Things not to do

- Do not change the system default Java or `update-alternatives`.
- Do not attempt an X11 (Xorg) session as the fix; Ubuntu 26.04 GNOME has no Xorg session and
  the uinput bridge makes it unnecessary.
- Do not leave a root ydotoold with a user-owned socket running permanently.
