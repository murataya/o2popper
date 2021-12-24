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

__version__ = '2.0.0'

MY_APP_NAME = 'O2Popper'

import builtins
builtins.__dict__['_'] = wx.GetTranslation

DEFAULT_BLOCK_LIST = '@gmai.com'

class BlockSmtp:
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
        main_sizer.Add((-1, 5))
        main_sizer.Add(self.gauge, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=15)

        self.Bind(wx.EVT_TIMER, self.on_timer)
        self.timer = wx.Timer(self)
        self.timer.Start(1000)

        # -----------------------------------------------------------------

        hbox2 = wx.BoxSizer(wx.HORIZONTAL)

        text21 = wx.StaticText(self, label=_("Envelope-From:"), style=wx.ALIGN_RIGHT)
        hbox2.Add(text21)
        s = parent.env_from
        text22 = wx.StaticText(self, label=s)
        text22.SetForegroundColour('#0033ff')
        hbox2.Add(text22, flag=wx.LEFT, border=5)

        main_sizer.Add((-1, 5))
        main_sizer.Add(hbox2, flag=wx.LEFT|wx.RIGHT, border=15)

        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        text31 = wx.StaticText(self, label=_("To+Cc+Bcc:"), size=text21.GetSize(), style=wx.ALIGN_RIGHT)
        hbox3.Add(text31)
        s = str(parent.rcpt_count)
        text32 = wx.StaticText(self, label=s)
        text32.SetForegroundColour('#0033ff')
        hbox3.Add(text32, flag=wx.LEFT, border=5)

        main_sizer.Add(hbox3, flag=wx.LEFT|wx.RIGHT, border=15)

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

def parse_block_list(block_list):
    if not block_list:
        return None

    r = []
    for t in block_list.encode().translate(bytes.maketrans(b',\r\n', b'   ')).lower().split():
        if t.find(b'@') > 0 and (not t.startswith(b'.')):
            r.append((t, True))
        else:
            r.append((t, False))
    return r

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

        self.rcpt_count = 0
        self.env_from = ''
  
        self.args = o2pop.args
        self.params = o2pop.params
        self.params.parent = self
        self.params.store_dir = self.store_dir = os.path.join(get_datadir(), MY_APP_NAME)

        self.ini_file = os.path.join(self.store_dir, 'o2popper_ini' + '.pickle')
        if os.path.exists(self.ini_file):
            with open(self.ini_file, 'rb') as ini:
                ini_data = pickle.load(ini)

            self.email = ini_data['email']
            self.login_hint = ini_data.get('login_hint', False) # new
            self.built_in = ini_data['built_in']
            self.path = ini_data['path']
            self.client_id = ini_data.get('client_id') # new
            self.client_secret = ini_data.get('client_secret') # new
            self.smtp = ini_data['smtp']
            self.smtp_port = ini_data['smtp_port']
            self.pop = ini_data['pop']
            self.pop_port = ini_data['pop_port']
            self.start_init = ini_data['start_init']

            self.to_cc_max = ini_data['to_cc_max']
            self.to_cc_exclude = ini_data['to_cc_exclude']
            self.send_delay = ini_data['send_delay']
            self.remove_header = ini_data['remove_header']
            self.change_env_from = ini_data.get('change_env_from', False) # new
            self.block_list = ini_data.get('block_list', DEFAULT_BLOCK_LIST) # new
            self.block_list_parsed = None

            self.params_info = ''
            self.set_client_config()
        else:
            self.email = ''
            self.login_hint = False
            self.built_in = True
            self.path = ''
            self.client_id = None
            self.client_secret = None
            self.smtp = True
            self.smtp_port = self.args.smtp_port
            self.pop = True
            self.pop_port = self.args.pop_port
            self.start_init = False

            self.to_cc_max = 10
            self.to_cc_exclude = ''
            self.send_delay = 5
            self.remove_header = False
            self.change_env_from = False
            self.block_list = DEFAULT_BLOCK_LIST
            self.block_list_parsed = parse_block_list(self.block_list)

            self.params_info = self.params.info()

        # ------------------------------------------------------------

        self.block_smtp_event, evt_delay = wx.lib.newevent.NewEvent()
        self.Bind(evt_delay, self.on_delay)
        self.block_smtp = BlockSmtp(self)

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

    def set_client_config(self):
        if self.email:
            self.params.email = self.email.encode()
        
        if self.built_in:
            self.params.path = None
        else:
            self.params.path = self.path

        self.args.no_smtp = not self.smtp
        self.args.smtp_port = self.smtp_port

        self.args.no_pop = not self.pop
        self.args.pop_port = self.pop_port

        self.block_list_parsed = parse_block_list(self.block_list)

        self.params.reset(self)
        self.params_info = self.params.info()

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

        self.set_client_config()

        ini_data = {
            'email': self.email,
            'login_hint': self.login_hint,
            'built_in': self.built_in,
            'path': self.path,

            'smtp': self.smtp,
            'smtp_port': self.smtp_port,
            'pop': self.pop,
            'pop_port': self.pop_port,
            'start_init': self.start_init,

            'to_cc_max': self.to_cc_max,
            'to_cc_exclude': self.to_cc_exclude,
            'send_delay': self.send_delay,
            'remove_header': self.remove_header,
            'change_env_from': self.change_env_from,
            'block_list': self.block_list,
        }

        if self.client_id:
            ini_data['client_id'] = self.client_id
        if self.client_secret:
            ini_data['client_secret'] = self.client_secret

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

        o2pop.params.ip_addr = o2pop.get_ip()

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
