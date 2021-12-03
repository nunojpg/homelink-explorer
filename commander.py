#!/usr/bin/env python3

from tkinter import *
from enum import IntEnum, Enum
from functools import partial
import threading, serial, math, time, signal

class Cmd(IntEnum):
    disable                = 0
    keepalive              = 0x1100000000000000
    ch_learn               = 0x1281000000000000 #60s to learn. If fail previous setting is unchanged
    ch_tx                  = 0x1382000000000000
    ch_clear               = 0x1383000000000000
    ch_config_UR_secplusv1 = 0x1384000000000000 #configure to Security+ (Chamberlain, LiftMaster, Craftsman, etc)
    ch_config_D            = 0x1384000100000000 #configure to somloq (?) with random id

# the * in the messages below can be any channel number
class Ans(Enum):
    dead                   = 'z\rt0060\r'
    sleeping               = 'z\rt00680000000000000000\r'
    learn_or_tx_ack        = 'z\rt00681100000000000000\r'
    unrecognized_cmd       = 'z\rt0068117A000000000000\r'
    invalid_ch             = 'z\rt0068117B000000000000\r'
    dontknow1              = 'z\rt0068117C000000000000\r'
    channel_empty_or_busy  = 'z\rt0068117D000000000000\r'
    ch_standby_last_tx     = 'z\rt0068140000000*000000\r'
    ch_tx_fixed            = 'z\rt0068140000020*000000\r'
    ch_tx_rolling          = 'z\rt0068140000030*000000\r'
    ch_learn_complete      = 'z\rt0068140000040*000000\r'
    ch_learn_rolling       = 'z\rt0068140000050*000000\r'
    ch_learn_ongoing       = 'z\rt0068140000070*000000\r'
    ch_mode_change_rolling = 'z\rt0068140000080*000000\r'
    ch_learn_fail          = 'z\rt00681400000B0*000000\r'
    ch_mode_change         = 'z\rt00681400000C0*000000\r'
    no_previous            = 'z\rt006814000000FF000000\r'
    dontknow2              = 'z\rt006812000F0000000000\r'
    dontknow3              = 'z\rt00681300000000000000\r'
    dontknow4              = 'z\rt00681300345800000000\r'
    dontknow5              = 'z\rt00681400000CFF000000\r'
    dontknow6              = 'z\rt006815005108400F0000\r'

    @classmethod
    def has_value(cls, value):
        return value in cls._value2member_map_

    @classmethod
    def has_value_ch(cls, value):
        if len(value) != 24:
            return false
        return (value[0:16] + '*' + value[17:]) in cls._value2member_map_

class GUI(threading.Thread):
    def command_ch(self, n):
        ch = self.var.get()
        global cmd
        if n == Cmd.ch_clear:
            print(ch)
            if ch <= 7:
                cmd = int(n) + (0x010000000000<<ch)
            else:
                cmd = int(n) + (0x000100000000<<(ch-8))
        else:
            cmd = int(n) + 0x010000000000*ch


    def command(self, n):
        global cmd
        cmd = n

    def run(self):
        self.root = Tk()
        self.root.title("Homelink")

        frame = Frame(self.root)
        frame.pack()
        self.labelText = StringVar()
        Label(frame, textvariable=self.labelText, width=30, anchor="w").pack(side=TOP, anchor="w")

        Button(frame, text="Disable"   , command=partial(self.command, Cmd.disable  )).pack(side=TOP, anchor="w")
        Button(frame, text="Keep Alive", command=partial(self.command, Cmd.keepalive)).pack(side=TOP, anchor="w")

        self.var = IntVar()
        for i in range(0,15): #15 channels: 0-14
            Radiobutton(frame, text=i, variable=self.var, value=i).pack(side=TOP, anchor="w")

        Button(frame, text="Tx                 ", command=partial(self.command_ch, Cmd.ch_tx                 )).pack(side=TOP, anchor="w")
        Button(frame, text="Learn              ", command=partial(self.command_ch, Cmd.ch_learn              )).pack(side=TOP, anchor="w")
        Button(frame, text="Config UR secplusv1", command=partial(self.command_ch, Cmd.ch_config_UR_secplusv1)).pack(side=TOP, anchor="w")
        Button(frame, text="Config D           ", command=partial(self.command_ch, Cmd.ch_config_D           )).pack(side=TOP, anchor="w")
        Button(frame, text="Clear              ", command=partial(self.command_ch, Cmd.ch_clear              )).pack(side=TOP, anchor="w")


        self.root.mainloop()

    def stop(self):
        self.root.quit()
        self.root.update()

    def answer(self, text):
        self.labelText.set(text)

class LUC:
    def __init__(self, com):
        self.ser = serial.Serial(com, timeout=0.02)
        if self.ser is None:
            raise NameError('SerialPortNotPresent')
        self.ser.reset_output_buffer()
        self.ser.reset_input_buffer()

    def close(self):
        self.ser.write(b'C\r')
        if self.ser.readline() != b'\r':
            raise Exception()

    def requestFirmwareVersion(self):
        self.ser.write(b'v\r')
        line = self.ser.readline().decode("utf-8")
        return line.replace("v", "").replace("\r", "")

    def requestHardwareVersion(self):
        self.ser.write(b'V\r')
        line = self.ser.readline().decode("utf-8")
        return line.replace("V", "").replace("\r", "")

    def highSpeed(self):
        self.ser.write(b'S1\r')
        if self.ser.readline() != b'\r':
            raise Exception()

    def openAsMonitor(self):
        self.ser.write(b'l\r')
        if self.ser.readline() != b'\r':
            raise Exception()

    def frameTX(self, id, data):
        data_str = hex(data).replace("0x", "")
        data_len = math.floor(len(data_str) / 2)
        self.ser.write(('t0' + hex(id).replace("0x", "").rjust(2, '0') + str(data_len) + data_str + '\r').encode())
        if self.ser.readline() != (b'z\rt0' + hex(id).replace("0x", "").rjust(2, '0').encode() + b'0\r'):
            raise Exception()

    def frameRX(self, id, len):
        line = ('r0' + hex(id).replace("0x", "").rjust(2, '0') + str(len) + '\r')
        self.ser.write(line.encode())
        return self.ser.readline().decode()

    def deInitSerial(self):
        self.ser.flush()
        self.ser.close()
        del self.ser

    def __del__(self):
        self.deInitSerial()

class LIN(threading.Thread):
    def __init__(self, *args, **kwargs):
        super(LIN, self).__init__(*args, **kwargs)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()

    def run(self):
        lin = LUC('/dev/ttyACM0')
        lin.close()
        print("Hardware " + lin.requestHardwareVersion())
        print("Firmware " + lin.requestFirmwareVersion())
        lin.highSpeed()
        lin.openAsMonitor()
        global cmd
        while not self.stopped():
            if cmd != Cmd.disable:
                lin.frameTX(0x3,int(cmd))
                if cmd != Cmd.keepalive:
                    cmd = Cmd.keepalive
            time.sleep(0.25)
            ans = lin.frameRX(0x6,8)
            if Ans.has_value(ans):
                human = Ans(ans)
            elif Ans.has_value_ch(ans):
                ch = int(ans[16],16)
                human = str(Ans(ans[0:16] + '*' + ans[17:])) + " CH" + str(ch)
            else:
                print(ans)
                raise Exception()
            print(human)
            if gui:
                gui.answer(human)
            time.sleep(0.25)

def sigint_handler(sig, frame):
    gui.stop()
    lin.stop()

cmd = Cmd.disable

signal.signal(signal.SIGINT, sigint_handler)
lin = LIN()
gui = GUI()
lin.start()
gui.start()
gui.join()
lin.stop()
