#!/usr/bin/env python3
"""Bridge: receives the AsTeRICS face-tracker output as OSC over UDP (port 57111)
and injects it as a virtual mouse through the ydotool daemon socket (uinput).
Needed on GNOME/Wayland, where the ARE's X11 mouse injection is ignored.

OSC in:  /dx <float>   relative x movement
         /cmd <string> a number = relative y movement, or @MOUSE:click,left | @MOUSE:nextclick,{right,double,drag}
                       @MOUSE:action,{toggle,enable,disable}
"""
import os, socket, struct, sys, time, threading

OSC_PORTS = [int(p) for p in os.environ.get('BRIDGE_PORTS', '57111,57112').split(',')]
SOCK = os.environ.get('YDOTOOL_SOCKET') or next(
    (p for p in (os.path.join(os.environ.get('XDG_RUNTIME_DIR', ''), '.ydotool_socket'), '/tmp/.ydotool_socket') if os.path.exists(p)), None)
if not SOCK:
    sys.exit('no ydotool socket found; start ydotoold first')

EV_SYN, EV_KEY, EV_REL = 0, 1, 2
REL_X, REL_Y, BTN_LEFT, BTN_RIGHT = 0, 1, 0x110, 0x111

class UInput:
    def __init__(self, path):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM); self.s.connect(path)
        self.lock = threading.Lock()
    def emit(self, *events):
        with self.lock:
            for t, c, v in events + ((EV_SYN, 0, 0),):
                self.s.send(struct.pack('<qqHHi', 0, 0, t, c, v))
    def move(self, dx, dy):
        self.emit(*(e for e in ((EV_REL, REL_X, dx), (EV_REL, REL_Y, dy)) if e[2]))
    def click(self, btn, times=1):
        for _ in range(times):
            self.emit((EV_KEY, btn, 1)); time.sleep(0.03); self.emit((EV_KEY, btn, 0)); time.sleep(0.05)
    def press(self, btn, down): self.emit((EV_KEY, btn, 1 if down else 0))

class Mouse:
    def __init__(self, ui):
        self.ui, self.enabled, self.nextclick, self.dragging = ui, True, 'left', False
        self.rx = self.ry = 0.0   # fractional remainders
    def move(self, dx, dy):
        if not self.enabled: return
        self.rx += dx; self.ry += dy
        ix, iy = int(self.rx), int(self.ry); self.rx -= ix; self.ry -= iy
        if ix or iy: self.ui.move(ix, iy)
    def command(self, cmd):
        cmd = cmd.strip()
        if not cmd.startswith('@MOUSE:'): return
        kind, _, arg = cmd[7:].partition(',')
        if kind == 'nextclick': self.nextclick = arg
        elif kind == 'action':
            self.enabled = {'enable': True, 'disable': False}.get(arg, not self.enabled)
            print('mouse', 'enabled' if self.enabled else 'disabled', flush=True)
        elif kind == 'click':
            if not self.enabled: return
            kind2, self.nextclick = self.nextclick, 'left'
            if self.dragging: self.ui.press(BTN_LEFT, False); self.dragging = False
            elif kind2 == 'right': self.ui.click(BTN_RIGHT)
            elif kind2 == 'double': self.ui.click(BTN_LEFT, 2)
            elif kind2 == 'drag': self.ui.press(BTN_LEFT, True); self.dragging = True
            else: self.ui.click(BTN_LEFT)

def osc_str(b, i):
    e = b.index(b'\0', i); s = b[i:e].decode(errors='replace'); return s, (e + 4) & ~3
def osc_packets(b):
    """yield (address, args) for a message or (recursively) a bundle"""
    if b.startswith(b'#bundle'):
        i = 16
        while i + 4 <= len(b):
            n = struct.unpack('>i', b[i:i+4])[0]; i += 4
            yield from osc_packets(b[i:i+n]); i += n
        return
    addr, i = osc_str(b, 0)
    tags, i = osc_str(b, i) if i < len(b) and b[i:i+1] == b',' else (',', i)
    args = []
    for t in tags[1:]:
        if t == 'f': args.append(struct.unpack('>f', b[i:i+4])[0]); i += 4
        elif t == 'i': args.append(struct.unpack('>i', b[i:i+4])[0]); i += 4
        elif t == 'd': args.append(struct.unpack('>d', b[i:i+8])[0]); i += 8
        elif t == 's': s, i = osc_str(b, i); args.append(s)
        else: break
    yield addr, args

def main():
    mouse = Mouse(UInput(SOCK))
    import selectors
    sel = selectors.DefaultSelector()
    for port in OSC_PORTS:
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); srv.bind(('127.0.0.1', port)); sel.register(srv, selectors.EVENT_READ)
    print(f'bridge: OSC on udp/{OSC_PORTS} -> {SOCK}', flush=True)
    while True:
      for key, _ in sel.select():
        data, _ = key.fileobj.recvfrom(4096)
        for addr, args in osc_packets(data):
            if addr == '/dx' and args: mouse.move(float(args[0]), 0)
            elif addr == '/dy' and args: mouse.move(0, float(args[0]))
            elif addr == '/cmd' and args:
                txt = str(args[0]).strip()
                try: mouse.move(0, float(txt))          # dy arrives as text
                except ValueError: print('cmd', txt, flush=True); mouse.command(txt)

if __name__ == '__main__':
    main()
