# AsTeRICS face-tracking mouse on Ubuntu 26.04 (GNOME / Wayland)

Head-controlled mouse for AsTeRICS Grid, using the AsTeRICS Runtime Environment (ARE)
face tracker. Set up on 2026-10-21 on a ThinkPad Z16 running Ubuntu 26.04.1, GNOME 50, Wayland.

## Why this folder exists

Two things do not work out of the box on this system:

1. **The ARE needs Java 8.** Its OSGi runtime (Equinox 3.6) relies on `javax.xml.bind` and
   friends that were removed in Java 11. On a newer Java the web service bundle fails to
   resolve, which kills the REST interface (port 8081) and WebACS. The 2019 pull request
   that fixed this upstream was never merged.
2. **GNOME 50 on Wayland ignores the ARE's cursor injection.** The ARE's Mouse plugin uses
   `java.awt.Robot`, i.e. X11 XTest through XWayland. The X11 pointer position updates, so
   the plugin believes it works, but the real cursor never moves. A virtual mouse through
   `uinput` does work, so this folder adds a bridge from the ARE to uinput.

## Files

| File | Purpose |
|---|---|
| `make_uinput_model.py` | Builds `XFaceTrackerMouse_uinput.acs` (full panel, decorated window) and `XFaceTrackerMouse_uinput_quiet.acs` (`--hide-gui`) from the stock `XFaceTrackerMouse.acs`. Replaces the Mouse plugin with an OSC output to the bridge. |
| `asterics_uinput_bridge.py` | Receives the OSC stream (UDP 57111) and injects it as a virtual mouse through the ydotool daemon socket. Handles move, left/right/double click, drag, and On/Off. |
| `start-facemouse.sh` | One-shot launcher: uinput daemon, bridge, then the ARE with the full-panel model (`--quiet` for the hidden variant, minimised automatically if `xdotool` is installed). Closing the ARE window stops everything. |
| `~/.local/share/applications/asterics-facemouse.desktop` | App menu entry "AsTeRICS Face Mouse" that runs the launcher. |
| `claude-instructions.md` | Step-by-step playbook for reproducing this setup on another Ubuntu 26.04 machine (written for Claude Code, usable by a person too). |

## Setup from scratch

### 1. Install the ARE

```bash
curl -LO https://github.com/asterics/AsTeRICS/releases/download/4.3.0/asterics-are-4.3.0-ubuntu-22.04.deb
sudo apt-get install -y libhidapi-libusb0 libxkbcommon-x11-0
sudo dpkg -i asterics-are-4.3.0-ubuntu-22.04.deb
```

The post-install script creates a menu entry, two udev rules (FS20 and IrTrans devices) and
moves the writable folders to `/var/opt/asterics-are/` (models, profile, data, web).

### 2. Install Java 8 and point the ARE at it

```bash
sudo apt-get install -y openjdk-8-jre
sudo sed -i.bak 's|^java |/usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java |' /opt/asterics-are/app/start.sh
```

The system default `java` stays whatever it was (Java 25 here). The backup is
`/opt/asterics-are/app/start.sh.bak`. Re-run the `sed` if a package upgrade replaces the script.

Check: run `/opt/asterics-are/app/start.sh`, then `curl http://localhost:8081/rest/runtime/model/state`
should answer `started` and `http://localhost:8081/` should serve WebACS.

### 3. Install ydotool and allow your user to use uinput

```bash
sudo apt-get install -y ydotool
sudo usermod -aG input $USER
```

Reboot so the group membership takes effect (logging out and back in is not enough, because the
per-user systemd manager survives the logout with the old groups). The package ships a per-user
`ydotool.service`; the launcher starts it on demand. Verify after the reboot with `id -nG | grep input`.

### 4. Build the uinput model

```bash
M=/var/opt/asterics-are/models
python3 -I ~/asterics/make_uinput_model.py            $M/XFaceTrackerMouse.acs $M/XFaceTrackerMouse_uinput.acs
python3 -I ~/asterics/make_uinput_model.py --hide-gui $M/XFaceTrackerMouse.acs $M/XFaceTrackerMouse_uinput_quiet.acs
```

Both models get a decorated window that is not always on top; `--hide-gui` also hides the preview,
slider and buttons (quiet model).

Repeat this only if the stock model changes or you edit the generator.

### 5. Install the menu entry

Create `~/.local/share/applications/asterics-facemouse.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=AsTeRICS Face Mouse
Comment=Head-controlled mouse (AsTeRICS face tracker via uinput bridge)
Exec=/home/manuel/asterics/start-facemouse.sh
Icon=/opt/asterics-are/asterics-are.png
Terminal=false
Categories=Utility;Accessibility;
```

### 6. Configure AsTeRICS Grid

In Grid: **Opções de acesso** → **Acesso com rato/toque** → enable hover (dwell) selection with
a dwell time of about 1 to 1.5 seconds. Leave scanning, direction, Huffman and sequential access off.

## Daily use

1. Start **AsTeRICS Face Mouse** from the app menu, or run `~/asterics/start-facemouse.sh`.
2. The ARE window appears with the model's control panel: buttons **Right**, **Double**, **Drag**,
   **On/Off**, **Menu**, a **Mouse Speed** slider, and a "Camera Mouse" preview. Green dots in the
   preview should sit on your face and follow it. The window has a normal title bar and is not
   always on top, so minimise it once tracking looks right.
   `~/asterics/start-facemouse.sh --quiet` is an alternative with no preview or buttons that is
   minimised automatically when `xdotool` is installed (`sudo apt-get install -y xdotool`).
3. Move your head to move the cursor. Hold still on a cell for about a second to click (the dwell
   timer in the model). Right, Double and Drag arm the next click. On/Off pauses cursor control.
4. Keep the ARE window open while using Grid. Closing it stops the tracker and the bridge.

Tips: face the camera at about arm's length with light on your face, not behind you.
Adjust Mouse Speed in the ARE window if the cursor is too fast or too slow.

## How the pieces connect

```
XFacetrackerLK -> Averager -> Deadzone -> MathEvaluator (speed) --dx--> OscOutClient CH1  ("/dx")
                                                           \--dy--> DoubleToString -> MultiSourceString -> OscOutClient StringIN ("/cmd")
Timer (dwell) / ButtonGrid -> StringDispatcher (@MOUSE:... commands) ----^
OscOutClient --UDP 127.0.0.1:57111--> asterics_uinput_bridge.py --input_event structs--> ydotoold socket --> /dev/uinput
```

Design notes that are not obvious:

- `OscOutClient` is a singleton inside the ARE (static instance), so a model can only have one.
  That is why dy travels as text on the string channel instead of on a second client.
- The ARE lays out panels at absolute coordinates on a 10000-unit virtual screen, starting at the
  window's top edge. With a decorated window the title bar covers that strip, so the generator pushes
  every panel down by `TITLEBAR = 400` units and grows the window by the same amount. The camera
  preview is a separate window and is not affected.
- The bridge components are inserted at the front of the model so they start before `Slider.1`,
  which fires its initial value immediately and would otherwise hit an unopened socket.
- Do not *pause* the model (REST `state/pause`): the face tracker cannot reopen the camera
  afterwards. Use stop then start instead.
- Bridge socket lookup order: `$YDOTOOL_SOCKET`, `$XDG_RUNTIME_DIR/.ydotool_socket`, `/tmp/.ydotool_socket`.
  Ports can be changed with `BRIDGE_PORTS` (default `57111,57112`).

## Troubleshooting

| Symptom | Check |
|---|---|
| ARE shows "Missing Constraint ... grizzly" or WebACS is dead | `start.sh` is not using Java 8. Re-run the `sed` from step 2. |
| Launcher says "No uinput daemon socket" | You are not in the `input` group yet, or haven't rebooted since joining it. |
| Green dots follow the face but the cursor does not move | Bridge not running or not receiving. Look at `~/.local/state/asterics-facemouse/bridge.log` and `are.log`. |
| Only one axis moves | The model has more than one OscOutClient, or a component started before it. Regenerate the model (step 4). |
| Popup "Deployment Error: Couldn't start 3 ... asterics.mw.jnativehook.jar" | `libxkbcommon-x11-0` is missing. `sudo apt-get install -y libxkbcommon-x11-0`. |
| Launcher says "AsTeRICS is already running" | An ARE window is still open (maybe minimised or behind a dialog). Close it, then start again. |
| "Could not open camera device" | Another program holds the webcam, or the model was paused. Stop and start the model, or restart the launcher. |
| Cursor moves on the wrong screen | With several monitors the cursor just continues from where it is; with the Grid window on another screen, move the cursor there first with the touchpad. |

Useful REST calls while the ARE runs:

```bash
curl http://localhost:8081/rest/runtime/model/state
curl -X PUT http://localhost:8081/rest/runtime/model/state/stop
curl -X PUT http://localhost:8081/rest/runtime/model/state/start
curl -X PUT http://localhost:8081/rest/runtime/model -H 'Content-Type: text/xml' \
     --data-binary @/var/opt/asterics-are/models/XFaceTrackerMouse_uinput.acs
```

## License

Public domain under [The Unlicense](LICENSE). AsTeRICS itself is a separate project with its own licensing (see https://www.asterics.eu).
