#!/usr/bin/python3

import sys
import os
import time
from BluetoothHID import BluetoothHIDService
from evdev_xkb_map import evdev_xkb_map, modkeys
import keymap
from Xlib import X, display, Xutil
from dbus.mainloop.glib import DBusGMainLoop
from threading import Timer

"""
Change this CONTROLLER_MAC to the mac of your own device
"""
CONTROLLER_MAC = "18:56:80:AE:63:E7"
X_WINDOW_DIMENSIONS=(1366,768)
POINTER_SPEED=0.8 #Should be between 0.1 and 3
POINTER_MOVEMENT_THRESHOLD=5
CONSTANT_REFRESH_PERIOD=100

usbhid_map = {}
with open("keycode.txt") as f:
    for line in f.read().splitlines():
        if not line.startswith(";") and len(line) > 1:
            l = line.split(maxsplit=1)
            usbhid_keycode = int(l[0])
            usbhid_keyname = l[1]
            usbhid_map[usbhid_keycode] = usbhid_keyname

def initConstants(j,eventCounter):
    with open("constants.txt","r") as f:
        lines=f.readlines()
        global POINTER_SPEED
        POINTER_SPEED=float(lines[1])
        global POINTER_MOVEMENT_THRESHOLD
        POINTER_MOVEMENT_THRESHOLD=int(lines[2])
        global CONSTANT_REFRESH_PERIOD
        CONSTANT_REFRESH_PERIOD=int(lines[3])
        print('constant refreshed-',j,eventCounter)

# Application window (only one)
class Window(object):
    def __init__(self, display):
        self.d = display
        self.objects = []

        # Find which screen to open the window on
        self.screen = self.d.screen()

        self.window = self.screen.root.create_window(
            50, 50, X_WINDOW_DIMENSIONS[0], X_WINDOW_DIMENSIONS[1], 2,
            self.screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,

            # special attribute values
            background_pixel=self.screen.white_pixel,
            event_mask=(X.ExposureMask |
                        X.StructureNotifyMask |
                        X.ButtonPressMask |
                        X.ButtonReleaseMask |
                        X.Button1MotionMask) |
                       X.KeyPressMask |
                       X.KeyReleaseMask,
            colormap=X.CopyFromParent,
        )

        self.gc = self.window.create_gc(
            foreground=self.screen.black_pixel,
            background=self.screen.white_pixel,
        )

        # Set some WM info

        self.WM_DELETE_WINDOW = self.d.intern_atom('WM_DELETE_WINDOW')
        self.WM_PROTOCOLS = self.d.intern_atom('WM_PROTOCOLS')

        self.window.set_wm_name('EmuBTHID')
        self.window.set_wm_icon_name('EmuBTHID')
        self.window.set_wm_protocols([self.WM_DELETE_WINDOW])
        self.window.set_wm_hints(flags=Xutil.StateHint,
                                 initial_state=Xutil.NormalState)

        self.window.set_wm_normal_hints(flags=(Xutil.PPosition | Xutil.PSize
                                               | Xutil.PMinSize),
                                        min_width=20,
                                        min_height=20)
        # Map the window, making it visible
        self.window.map()

    def grab(self):
        print("Grab!")
        ret = self.window.grab_pointer(False, X.ButtonReleaseMask | X.ButtonPressMask | X.PointerMotionMask,
                                       X.GrabModeAsync, X.GrabModeAsync, self.window, X.NONE, X.CurrentTime)
        ret = self.window.grab_keyboard(False, X.GrabModeAsync, X.GrabModeAsync, X.CurrentTime)

    def ungrab(self):
        print("UnGrab!")
        self.d.ungrab_pointer(X.CurrentTime)
        self.d.ungrab_keyboard(X.CurrentTime)

    # Main loop, handling events
    def loop(self, send_call_back):
        kbd_state = bytearray([
            0xA1,
            0x01,  # Report ID
            0x00,  # Modifier keys
            0x00,  # preserve
            0x00,  # 6 key
            0x00,
            0x00,
            0x00,
            0x00,
            0x00
        ])
        mouse_state = bytearray([
            0xA1,
            0x02,  # Report ID
            0x00,  # mouse button, in this byte XXXXX(button2)(button1)(button0)
            0x00,  # X displacement
            0x00,  # Y displacement
        ])
        expose_count = 0
        grab_trigger_hint = ('KEY_LEFTCTRL', 'KEY_LEFTALT', 'KEY_LEFTSHIFT', 'KEY_B')
        grab_trigger = set(keymap.keytable[k] for k in grab_trigger_hint)
        grab_cnt = len(grab_trigger)
        grabbed = False
        geometry = self.window.get_geometry()
        prev_x = None
        prev_y = None
        hint_x = geometry.width // 5
        hint_y = geometry.height // 5
        hint_str = 'Press Ctrl+Alt+Shift+B to   Grab'.encode()
        i=CONSTANT_REFRESH_PERIOD
        j=1
        eventCounter=0
        while 1:
            if i==CONSTANT_REFRESH_PERIOD:
                initConstants(j,eventCounter)
                i=0
                j+=1
            i+=1
            e = self.d.next_event()
            # Window has been destroyed, quit
            if e.type == X.DestroyNotify:
                print("Destroy")
                sys.exit(0)
            if e.type == X.KeyPress:
                usbhid_keycode = evdev_xkb_map[e.detail]
                # print("key pressed: {}".format(usbhid_map[usbhid_keycode]))
                if usbhid_keycode in modkeys:
                    kbd_state[2] |= modkeys[usbhid_keycode]
                    # import ipdb
                    # ipdb.set_trace()
                else:
                    for i in range(4, 10):
                        if kbd_state[i] == 0x00:
                            kbd_state[i] = usbhid_keycode
                            break
                send_call_back(bytes(kbd_state))
                if usbhid_keycode in grab_trigger:
                    grab_cnt -= 1
                    print(grab_cnt)
                    if (grab_cnt == 0):
                        if grabbed:
                            self.ungrab()
                            grabbed = False
                            hint_str = 'Press Ctrl+Alt+Shift+B to   Grab'.encode()
                            self.window.image_text(self.gc, hint_x, hint_y, hint_str)

                        else:
                            self.grab()
                            grabbed = True
                            hint_str = 'Press Ctrl+Alt+Shift+B to UnGrab'.encode()
                            self.window.image_text(self.gc, hint_x, hint_y, hint_str)

            if e.type == X.KeyRelease:
                usbhid_keycode = evdev_xkb_map[e.detail]
                # print("key released: {}".format(usbhid_map[evdev_xkb_map[e.detail]]))
                if usbhid_keycode in modkeys:
                    kbd_state[2] &= ~modkeys[usbhid_keycode]
                else:
                    for i in range(4, 10):
                        if kbd_state[i] == usbhid_keycode:
                            kbd_state[i] = 0x00
                            break
                if usbhid_keycode in grab_trigger:
                    grab_cnt += 1
                    print(grab_cnt)
                send_call_back(bytes(kbd_state))

            # Some part of the window has been exposed,
            # redraw all the objects.
            if e.type == X.Expose:
                expose_count += 1
                print("Exposed : {}".format(expose_count))
                geometry = self.window.get_geometry()
                hint_x = geometry.width // 5
                hint_y = geometry.height // 5
                self.window.image_text(self.gc, hint_x, hint_y, hint_str)

            # Left button pressed, start to draw
            if e.type == X.ButtonPress:
                # print("Button press: {}".format(e.detail))
                if (e.detail <= 3):
                    mouse_state[2] |= 1 << (e.detail - 1)
                send_call_back(bytes(mouse_state))

            if e.type == X.ButtonRelease:
                # print("Button release: {}".format(e.detail))
                mouse_state[2] &= ~(1 << (e.detail - 1))
                send_call_back(bytes(mouse_state))

            if e.type == X.ClientMessage:
                if e.client_type == self.WM_PROTOCOLS:
                    fmt, data = e.data
                    if fmt == 32 and data[0] == self.WM_DELETE_WINDOW:
                        sys.exit(0)
            if e.type == X.MotionNotify:
                #print("Motion: ({x},{y})".format(x=e.event_x, y=e.event_y))
                if prev_x is None:
                    prev_x=e.event_x
                if prev_y is None:
                    prev_y=e.event_y
                #if prev_x is not None and prev_y is not None and (abs(prev_x-e.event_x)>POINTER_MOVEMENT_THRESHOLD or abs(prev_y-e.event_y)>POINTER_MOVEMENT_THRESHOLD):
                if (abs(prev_x-e.event_x)>POINTER_MOVEMENT_THRESHOLD or abs(prev_y-e.event_y)>POINTER_MOVEMENT_THRESHOLD):
                    pos_x = max(-128, min(int((e.event_x - prev_x) * POINTER_SPEED), 127))
                    mouse_state[3] = pos_x if pos_x >= 0 else (256 + pos_x)
                    pos_y = max(-128, min(int((e.event_y - prev_y) * POINTER_SPEED), 127))
                    mouse_state[4] = pos_y if pos_y >= 0 else (256 + pos_y)
                    send_call_back(bytes(mouse_state))
                    prev_x = e.event_x
                    prev_y = e.event_y
                    eventCounter+=1
                '''if prev_x is not None and prev_y is not None:
                    #pos_x = max(-128, min(int((e.event_x - prev_x) * 2), 127))
                    mouse_state[3] = 128 + e.event_x - prev_x
                    #pos_y = max(-128, min(int((e.event_y - prev_y) * 2), 127))
                    mouse_state[4] = 128 + e.event_y - prev_y
                    #print("    ({},{})".format(mouse_state[3], mouse_state[4]))
                    send_call_back(bytes(mouse_state))'''

                if e.event_x > geometry.width - 30:
                    self.window.warp_pointer(50, e.event_y)
                    prev_x = 50
                elif e.event_x < 30:
                    self.window.warp_pointer(geometry.width - 50, e.event_y)
                    prev_x = geometry.width - 50
                #else:
                #    prev_x = e.event_x

                if e.event_y > geometry.height - 30:
                    self.window.warp_pointer(e.event_x, 50)
                    prev_y = 50
                elif e.event_y < 30:
                    self.window.warp_pointer(e.event_x, geometry.height - 50)
                    prev_y = geometry.height - 50
                #else:
                #    prev_y = e.event_y

if __name__ == '__main__':
    DBusGMainLoop(set_as_default=True)
    service_record = open("sdp_record_kbd.xml").read()
    d = display.Display()
    d.change_keyboard_control(auto_repeat_mode=X.AutoRepeatModeOff)
    try:
        bthid_srv = BluetoothHIDService(service_record, CONTROLLER_MAC)
        Window(d).loop(bthid_srv.send)
        #Window(d).loop(print)
    finally:
        d.change_keyboard_control(auto_repeat_mode=X.AutoRepeatModeOn)
        d.get_keyboard_control()
        d.ungrab_keyboard(X.CurrentTime)
        d.ungrab_pointer(X.CurrentTime)
        print("Exit")
