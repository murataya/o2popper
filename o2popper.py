#
# o2popper.py
#
# Copyright (c) 2020-2021 MURATA Yasuhisa
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT
#

import wx
import wx.adv
import wx.lib.newevent

import platform
import base64
import icon_data
from io import BytesIO

import o2pop
import threading
import sys
import pickle
import os

import settings
import monitor

__version__ = '1.0.3'

MY_APP_NAME = 'O2Popper'

import builtins
builtins.__dict__['_'] = wx.GetTranslation

class BlockSmtp(object):
    def __init__(self, parent):
        self.parent = parent
        self.cancel = False
        self.task = None

    def run(self):
        evt = self.parent.block_smtp_event()
        wx.PostEvent(self.parent, evt)

class SendingDialog(wx.Dialog):
    def __init__(self, parent, *args, **kw):
        # self.parent = parent
        super().__init__(*args, **kw)

        self.SetIcon(parent.icon)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        text1 = wx.StaticText(self, label=_("Waiting to be sent..."), size=(250,-1))
        main_sizer.Add(text1, flag=wx.LEFT|wx.TOP, border=15)

        # -----------------------------------------------------------------
        self.count = 0
        self.delay = parent.send_delay

        self.gauge = wx.Gauge(self, range=self.delay, style=wx.GA_HORIZONTAL|wx.GA_PROGRESS)
        main_sizer.Add(self.gauge, flag=wx.EXPAND|wx.ALL, border=15)

        self.Bind(wx.EVT_TIMER, self.on_timer)
        self.timer = wx.Timer(self)
        self.timer.Start(1000)

        # -----------------------------------------------------------------

        line = wx.StaticLine(self)
        main_sizer.Add(line, flag=wx.EXPAND|wx.ALL, border=10)
        button_cancel = wx.Button(self, wx.ID_CANCEL, label=_("Cancel"))
        main_sizer.Add(button_cancel, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.ALIGN_RIGHT, border=15)
        self.SetSizerAndFit(main_sizer)
        self.Centre()

    def __del__(self):
        self.timer.Stop()

    def on_timer(self, evt):
        self.count = self.count + 1
        if self.count > self.delay:
            self.EndModal(wx.ID_CLOSE)
            return
        self.gauge.SetValue(self.count)

    def on_close(self, evt):
        self.EndModal(wx.ID_CLOSE)

def get_datadir():
    home = os.path.expanduser('~')
    pf = platform.system()

    if pf == 'Windows':
        return os.path.join(home, 'AppData', 'Roaming')
    elif pf == 'Linux':
        return os.path.join(home, '.local', 'share')
    elif pf == 'Darwin':
        return os.path.join(home, 'Library', 'Application Support')
    else:
        return ''

class MainMenu(wx.adv.TaskBarIcon):
    def __init__(self, frame):
        self.frame = frame
        super().__init__()

        data = base64.b64decode(icon_data.ICON_DATA)
        bitmap = wx.Image(BytesIO(data)).ConvertToBitmap()
        self.icon = wx.Icon()
        self.icon.CopyFromBitmap(bitmap)
        self.SetIcon(self.icon, tooltip=MY_APP_NAME)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_left_down)

        if platform.system() == 'Windows':
            self.pf_windows = True
        else:
            self.pf_windows = False
                
        self.store_dir = os.path.join(get_datadir(), MY_APP_NAME)
        o2pop.STORE_DIR = self.store_dir

        self.ini_file = os.path.join(self.store_dir, 'o2popper_ini' + '.pickle')
        if os.path.exists(self.ini_file):
            with open(self.ini_file, 'rb') as ini:
                ini_data = pickle.load(ini)

            self.email = ini_data['email']
            self.built_in = ini_data['built_in']
            self.path = ini_data['path']
            self.smtp = ini_data['smtp']
            self.smtp_port = ini_data['smtp_port']
            self.pop = ini_data['pop']
            self.pop_port = ini_data['pop_port']
            self.start_init = ini_data['start_init']

            self.to_cc_max = ini_data['to_cc_max']
            self.to_cc_exclude = ini_data['to_cc_exclude']
            self.remove_header = ini_data['remove_header']
            self.send_delay = ini_data['send_delay']

        else:
            self.email = ''
            self.built_in = True
            self.path = ''
            self.smtp = True
            self.smtp_port = o2pop.args.smtp_port
            self.pop = True
            self.pop_port = o2pop.args.pop_port
            self.start_init = False

            self.to_cc_max = 10
            self.to_cc_exclude = ''
            self.remove_header = False
            self.send_delay = 5

        self.get_token_file = o2pop.get_token_file
        self.get_token = o2pop.get_token

        # ------------------------------------------------------------

        self.block_smtp_event, evt_delay = wx.lib.newevent.NewEvent()
        self.Bind(evt_delay, self.on_delay)
        self.block_smtp = BlockSmtp(self)
        o2pop.BLOCK_SMTP = self.block_smtp

        # ------------------------------------------------------------

        self.loop = None
        self.task = None
        self.exit = False
        self.run_main = False
        self.event = threading.Event()

        if self.start_init:
            self.monitor_menu = False
            self.start_check = True
            self.event.set()
        else:
            self.monitor_menu = True
            self.start_check = False

        self.thread = threading.Thread(target=self.do_task)
        self.thread.start()

    def on_delay(self, e):
        dlg = SendingDialog(self, None, title=_("Delay Sending"), style=wx.DEFAULT_DIALOG_STYLE|wx.STAY_ON_TOP)
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_CANCEL:
            self.block_smtp.cancel = True
        self.task_cancel(self.block_smtp.task)

    def CreatePopupMenu(self):
        menu = wx.Menu()

        self.settings_item = wx.MenuItem(menu, wx.ID_SETUP, text=_('Settings...'))
        menu.Append(self.settings_item)

        if self.monitor_menu:
            menu.Bind(wx.EVT_MENU, self.on_settings, source=self.settings_item)
        else:
            self.settings_item.Enable(False)

        menu.AppendSeparator()

        self.monitor_item = wx.MenuItem(menu, wx.ID_INFO, text=_('Monitor...'))
        menu.Append(self.monitor_item)

        if self.monitor_menu:
            menu.Bind(wx.EVT_MENU, self.on_monitor, source=self.monitor_item)
        else:
            self.monitor_item.Enable(False)

        menu.AppendSeparator()

        self.start_item = menu.AppendCheckItem(wx.ID_EXECUTE, _('Start'))
        menu.Bind(wx.EVT_MENU, self.on_start, source=self.start_item)

        self.stop_item = menu.AppendCheckItem(wx.ID_STOP, _('Stop'))

        if self.start_check:
            self.start_item.Check()
            self.start_item.Enable(False)
            self.settings_item.Enable(False)
        else:
            self.stop_item.Check()
            self.stop_item.Enable(False)

        menu.Bind(wx.EVT_MENU, self.on_stop, source=self.stop_item)

        menu.AppendSeparator()
        item = wx.MenuItem(menu, wx.ID_ABOUT, text=_('About...'))
        menu.Append(item)
        menu.Bind(wx.EVT_MENU, self.on_about, source=item)

        menu.AppendSeparator()

        self.exit_item = wx.MenuItem(menu, wx.ID_EXIT, text=_('Exit'))
        menu.Append(self.exit_item)

        menu.Bind(wx.EVT_MENU, self.on_exit, source=self.exit_item)

        return menu

    def on_left_down(self, e):
        menu = self.CreatePopupMenu()
        self.PopupMenu(menu)
        menu.Destroy()

    def on_settings(self, e):
        dlg = settings.Settings(self, None, title=_("Settings"), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER|wx.MINIMIZE_BOX)
        result = dlg.ShowModal()
        dlg.Destroy()

        if result != wx.ID_OK:
            return
        o2pop.args.email = self.email
        if self.email:
            o2pop.EMAIL = self.email.encode()

        if self.built_in:
            o2pop.args.client_secret_file = None
        else:
            o2pop.args.client_secret_file = self.path

        o2pop.client_config = o2pop.load_client_secret_file(o2pop.args.client_secret_file)
        o2pop.client_id, o2pop.client_secret = o2pop.get_id_secret(o2pop.client_config)

        o2pop.args.no_smtp = not self.smtp
        o2pop.args.smtp_port = self.smtp_port

        o2pop.args.no_pop = not self.pop
        o2pop.args.pop_port = self.pop_port

        ini_data = {
            'email': self.email,
            'built_in': self.built_in,
            'path': self.path,
            'smtp': self.smtp,
            'smtp_port': self.smtp_port,
            'pop': self.pop,
            'pop_port': self.pop_port,
            'start_init': self.start_init,

            'to_cc_max': self.to_cc_max,
            'to_cc_exclude': self.to_cc_exclude,
            'remove_header': self.remove_header,
            'send_delay': self.send_delay,
        }

        if not os.path.exists(self.store_dir):
            os.makedirs(self.store_dir)

        with open(self.ini_file, 'wb') as ini:
            pickle.dump(ini_data, ini)

    def on_monitor(self, e):
        dlg = monitor.Monitor(self, None, title=_("Monitor"), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)

        self.monitor_menu = False
        dlg.ShowModal()
        dlg.Destroy()

        self.monitor_menu = True

    def on_start(self, e):
        self.monitor_menu = False
        self.start_check = True
        self.event.set()

    def on_stop(self, e):
        self.monitor_menu = True
        self.start_check = False
        self.task_cancel(self.task)

    def do_task(self):
        while True:
            self.event.wait()
            if self.exit:
                break
            self.run_main = True

            o2pop.run_main(o2pop.main(self))

            if self.exit:
                break

            self.event.clear()
            self.run_main = False

    def task_cancel(self, task):
        o2pop.task_cancel(self.loop, task)

    def set_verbose(self, v):
        o2pop.args.verbose = v

    def on_about(self, e):
        aboutInfo = wx.adv.AboutDialogInfo()
        aboutInfo.SetName(MY_APP_NAME)
        aboutInfo.SetVersion(__version__)
        aboutInfo.SetCopyright("(C) 2020-2021 MURATA Yasuhisa")
        aboutInfo.SetWebSite("https://www.nips.ac.jp/~murata/o2popper/")
        aboutInfo.SetIcon(self.icon)

        t = sys.version
        i = t.find('(')
        j = t.find('[')
        ver = t[:i] + t[j:]
        s = f'Includes:\nPython {ver}\n{o2pop.ssl.OPENSSL_VERSION}\nwxPython {wx.version()}\ngoogle-auth-oauthlib'
        aboutInfo.SetDescription(s)

        wx.adv.AboutBox(aboutInfo)

    def on_exit(self, e):
        wx.CallAfter(self.Destroy)
        self.frame.Close()

class App(wx.App):
    def OnInit(self):

        if getattr(sys, 'frozen', False):
            basedir = os.path.dirname(sys.executable)
        elif __file__:
            basedir = os.path.dirname(__file__)

        locale_dir = os.path.join(basedir, "locale")
        wx.Locale.AddCatalogLookupPathPrefix(locale_dir)

        if os.path.exists(locale_dir):
            lang = wx.LANGUAGE_DEFAULT
        else:
            lang = wx.LANGUAGE_ENGLISH_US

        self.locale = wx.Locale(lang)
        if self.locale.IsOk():
            self.locale.AddCatalog(MY_APP_NAME.lower())
        else:
            self.locale = None

        self.name = MY_APP_NAME + '-%s' % wx.GetUserId()
        self.instance = wx.SingleInstanceChecker(self.name)

        if self.instance.IsAnotherRunning():
            wx.MessageBox(MY_APP_NAME + " " + _("is running"), caption=_("Error"), style=wx.ICON_ERROR)
            return False

        frame = wx.Frame(None)
        self.SetTopWindow(frame)
        self.main_menu = MainMenu(frame)

        if platform.system() == 'Darwin':
            o2pop.args.ca_file = '/etc/ssl/cert.pem'

        o2pop.IP_ADDR = o2pop.get_ip()

        return True

try:
    app = App()
except:
    sys.exit(0)

main_menu = app.main_menu

try:
    app.MainLoop()
finally:
    main_menu.exit = True
    if main_menu.run_main:
        main_menu.task_cancel(main_menu.task)
    else:
        main_menu.event.set()
    main_menu.thread.join()
