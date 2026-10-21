#!/usr/bin/env python3
"""Build XFaceTrackerMouse_uinput.acs from the stock XFaceTrackerMouse.acs:
replaces the X11 Mouse actuator with a single OSC output to the local uinput bridge.
(The OscOutClient plugin is a singleton, so one instance carries everything:
 dx on CH1, dy as text and the click commands merged on the string channel.)"""
import sys
import xml.etree.ElementTree as ET

args = [a for a in sys.argv[1:] if not a.startswith('--')]
hide_gui = '--hide-gui' in sys.argv          # no camera preview / slider / buttons, window not always on top
src, dst = args[0], args[1]
tree = ET.parse(src); root = tree.getroot()
comps, chans, evs = root.find('components'), root.find('channels'), root.find('eventChannels')

# 1. drop the X11 Mouse component and everything wired to it
for c in list(comps):
    if c.get('type_id') == 'asterics.Mouse': comps.remove(c)
for ch in list(chans):
    if ch.find('target/component').get('id') == 'Mouse.1': chans.remove(ch)
for ev in list(evs):
    if ev.find('targets/target/component').get('id') == 'Mouse.1': evs.remove(ev)

# 2. new components, inserted at the front so they start before the slider fires its initial value
def comp(cid, tid, inputs, outputs, props, x, y):
    c = ET.Element('component', id=cid, type_id=tid); comps.insert(0, c)
    ET.SubElement(c, 'description').text = 'uinput bridge'
    ports = ET.SubElement(c, 'ports')
    for p in inputs: ET.SubElement(ET.SubElement(ports, 'inputPort', portTypeID=p), 'properties')
    for p in outputs: ET.SubElement(ET.SubElement(ports, 'outputPort', portTypeID=p), 'properties')
    pr = ET.SubElement(c, 'properties')
    for n, v in props: ET.SubElement(pr, 'property', name=n, value=v)
    lay = ET.SubElement(c, 'layout'); ET.SubElement(lay, 'posX').text = str(x); ET.SubElement(lay, 'posY').text = str(y)
comp('Merge', 'asterics.MultiSourceString', ['input1', 'input2', 'input3', 'input4'], ['output'], [], 500, 200)
comp('DyToStr', 'asterics.DoubleToString', ['input'], ['output'], [], 400, 200)
comp('Osc', 'asterics.OscOutClient', ['CH1', 'CH2', 'CH3', 'CH4', 'StringIN'], [],
     [('Port', '57111'), ('PeerAddress', '127.0.0.1'), ('AddressCh1', '/dx'), ('AddressStringCh', '/cmd')], 607, 27)

def channel(cid, sc, sp, tc, tp):
    ch = ET.SubElement(chans, 'channel', id=cid); ET.SubElement(ch, 'description')
    s = ET.SubElement(ch, 'source'); ET.SubElement(s, 'component', id=sc); ET.SubElement(s, 'port', id=sp)
    t = ET.SubElement(ch, 'target'); ET.SubElement(t, 'component', id=tc); ET.SubElement(t, 'port', id=tp)
channel('uinput.dx', 'MathEvaluator.1', 'out', 'Osc', 'CH1')
channel('uinput.dy', 'MathEvaluator.1.1', 'out', 'DyToStr', 'input')
channel('uinput.dyStr', 'DyToStr', 'output', 'Merge', 'input1')
channel('uinput.cmd', 'StringDispatcher.1', 'output', 'Merge', 'input2')
channel('uinput.osc', 'Merge', 'output', 'Osc', 'StringIN')

# 3. dwell click and On/Off become dispatcher slots so they reach the bridge as strings
sd = [c for c in comps if c.get('type_id') == 'asterics.StringDispatcher'][0]
for p in sd.find('properties'):
    if p.get('name') == 'slot4': p.set('value', '@MOUSE:click,left')
    if p.get('name') == 'slot5': p.set('value', '@MOUSE:action,toggle')
def event(eid, sc, sp, tc, tp):
    ev = ET.SubElement(evs, 'eventChannel', id=eid); ET.SubElement(ev, 'description')
    s = ET.SubElement(ET.SubElement(ev, 'sources'), 'source'); ET.SubElement(s, 'component', id=sc); ET.SubElement(s, 'eventPort', id=sp)
    t = ET.SubElement(ET.SubElement(ev, 'targets'), 'target'); ET.SubElement(t, 'component', id=tc); ET.SubElement(t, 'eventPort', id=tp)
event('uinput.dwellClick', 'Timer.1', 'periodFinished', 'StringDispatcher.1', 'dispatchSlot4')
event('uinput.toggle', 'ButtonGrid.1', 'button4', 'StringDispatcher.1', 'dispatchSlot5')

root.set('modelName', dst.rsplit('/', 1)[-1])

# 4. window: normal title bar (minimise/close buttons) and not always on top, so it can sit behind Grid
gui = root.find('modelGUI')
gui.find('AlwaysOnTop').text = 'false'
gui.find('Decoration').text = 'true'
win = gui.find('AREGUIWindow')   # keep the stock geometry: the panels are placed at these virtual-screen coordinates
# the title bar covers the top of the content area, so push every panel down by its height (10000-unit screen)
TITLEBAR = 400
for c in comps:
    g = c.find('gui')
    if g is not None: g.find('posY').text = str(int(g.find('posY').text) + TITLEBAR)
win.find('height').text = str(int(win.find('height').text) + TITLEBAR)
# optional quiet mode: hide every GUI element as well
if hide_gui:
    for c in comps:
        for p in c.iter('property'):
            if p.get('name') == 'displayGUI': p.set('value', 'false')
    win.find('width').text = '300'; win.find('height').text = '120' 
ET.indent(tree, space='  ')
tree.write(dst, encoding='UTF-8', xml_declaration=True)
print('wrote', dst)
