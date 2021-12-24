#
# monitor.py (for O2Popper)
#
# Copyright (c) 2020-2021 MURATA Yasuhisa
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT
#

import wx
import sys
import threading

import builtins
builtins.__dict__['_'] = wx.GetTranslation

class WriteText:
    def __init__(self, logger):
        self.logger = logger
        self.buff = []
        self.lock = threading.Lock()
        self.attr1 = wx.TextAttr(self.logger.GetForegroundColour())
        self.attr2 = wx.TextAttr(wx.Colour(204, 0, 204))

    def write(self, string):
        self.flush(string, False)

    def flush(self, string=None, is_flush=True):
        with self.lock:
            if not is_flush:
                self.buff.append(string)
                return
            
            if not self.buff:
                return

            if len(self.buff) == 1:
                t = self.buff[0]
                if t.startswith('<<'):
                    self.logger.SetDefaultStyle(self.attr2)
                else:
                    self.logger.SetDefaultStyle(self.attr1)
                self.logger.write(t)
                return

            t = self.buff[0]
            if t.startswith('<<'):
                color0 = True
            else:
                color0 = False

            i = 0
            j = 1
            write_ok = False
            attr = self.attr1
            for t in self.buff[1:]:
                if t.startswith('<<'):
                    if not color0:
                        color0 = True
                        attr = self.attr1
                        write_ok = True
                else:
                    if color0:
                        color0 = False
                        attr = self.attr2
                        write_ok = True
                if write_ok:
                    self.logger.SetDefaultStyle(attr)
                    s = ''.join(self.buff[i:j])
                    self.logger.write(s)
                    i = j
                    write_ok = False
                j += 1
                
            if color0:
                attr = self.attr2
            else:
                attr = self.attr1
            self.logger.SetDefaultStyle(attr)
            s = ''.join(self.buff[i:j])
            self.logger.write(s)
            
            self.buff.clear()

class Monitor(wx.Dialog):
    def __init__(self, parent, *args, **kw):
        self.parent = parent
        super().__init__(*args, **kw)
        self.SetIcon(parent.icon)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ----------------------------------------------------------

        self.logger = wx.TextCtrl(self, size=(512,256), style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.text = WriteText(self.logger)
        self.stdout_orig = sys.stdout
        sys.stdout = self.text

        main_sizer.Add(self.logger, proportion=1, flag=wx.LEFT|wx.RIGHT|wx.TOP|wx.EXPAND, border=10)

        # ----------------------------------------------------------

        hbox9 = wx.BoxSizer(wx.HORIZONTAL)
        
        button_clear = wx.Button(self, wx.ID_CLEAR, label=_("Clear"))
        button_clear.Bind(wx.EVT_BUTTON, self.on_clear)

        self.button_start = wx.Button(self, wx.ID_EXECUTE, label=_("Start"))
        self.button_start.Bind(wx.EVT_BUTTON, self.on_start)

        self.button_stop = wx.Button(self, wx.ID_STOP, label=_("Stop"))
        self.button_stop.Bind(wx.EVT_BUTTON, self.on_stop)

        if parent.start_check:
           self.button_start.Enable(False)
        else:
           self.button_stop.Enable(False)

        button_close = wx.Button(self, wx.ID_CLOSE, label=_("Close"))
        button_close.Bind(wx.EVT_BUTTON, self.on_close)

        self.Bind(wx.EVT_CLOSE, self.on_close)

        hbox9.Add(button_clear, flag=wx.LEFT, border=5)
        hbox9.Add(self.button_start, flag=wx.LEFT, border=5)

        hbox9.Add(self.button_stop, flag=wx.LEFT, border=5)
        hbox9.Add(button_close, flag=wx.LEFT|wx.RIGHT, border=5)

        main_sizer.Add(hbox9, flag=wx.ALL|wx.ALIGN_RIGHT, border=10)

        # ----------------------------------------------------------

        self.SetSizerAndFit(main_sizer)
        self.Centre()

        # ----------------------------------------------------------

        parent.set_verbose(True)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, source=self.timer)
        self.timer.Start(30) # 30ms

    def on_timer(self, evt):
        self.text.flush()

    def on_clear(self, evt):
        self.logger.Clear()

    def on_start(self, evt):
        self.button_start.Enable(False)
        self.button_stop.Enable()

        self.parent.start_check = True
        self.parent.event.set()

    def on_stop(self, evt):
        self.button_stop.Enable(False)
        self.button_start.Enable()
        self.parent.start_check = False
        self.parent.task_cancel(self.parent.task)

    def on_close(self, evt):
        self.parent.set_verbose(False)
        if self.parent.start_check:
            self.parent.start_check = False
            self.parent.task_cancel(self.parent.task)
        self.timer.Stop()
        sys.stdout = self.stdout_orig
        self.EndModal(wx.ID_CLOSE)
