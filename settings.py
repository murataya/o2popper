#
# settings.py (for O2Popper)
#
# Copyright (c) 2020-2021 MURATA Yasuhisa
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT
#

import wx
import wx.lib.intctrl

import os

import builtins
builtins.__dict__['_'] = wx.GetTranslation

class Settings(wx.Dialog):
    def __init__(self, parent, *args, **kw):
        self.parent = parent
        super().__init__(*args, **kw)

        self.pf_windows = parent.pf_windows

        self.SetIcon(parent.icon)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ----------------------------------------------------------

        sbox1 = wx.StaticBox(self, label=_("Authorization"))
        sizer1 = wx.StaticBoxSizer(sbox1, wx.VERTICAL)

        text11 = wx.StaticText(self, label=_("Your emal:"))
        sizer1.Add(text11, flag=wx.LEFT|wx.TOP, border=5)

        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.tc_email = wx.TextCtrl(self)

        self.tc_email.SetMinSize((250, -1))

        hbox1.Add(self.tc_email, proportion=1)
        self.tc_email.Bind(wx.EVT_TEXT, self.on_text)

        self.button_auth = wx.Button(self, label=_("Auth..."))
        hbox1.Add(self.button_auth, flag=wx.LEFT, border=5)
        self.button_auth.Bind(wx.EVT_BUTTON, self.on_auth)

        sizer1.Add(hbox1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=5)

        text12_note = wx.StaticText(self, label=_("Please don't input group-address!"))
        font1 = text12_note.GetFont()
        font1.PointSize -= 1
        text12_note.SetFont(font1)
        text12_note.SetForegroundColour('#cc33cc')
        sizer1.Add(text12_note, flag=wx.LEFT, border=10)
        sizer1.Add((-1, 5))

        main_sizer.Add(sizer1, flag=wx.EXPAND|wx.ALL, border=10)

        # ----------------------------------------------------------

        sbox2 = wx.StaticBox(self, label=_("Secret File"))
        sizer2 = wx.StaticBoxSizer(sbox2, wx.VERTICAL)

        self.radio_built_in = wx.RadioButton(self, label=_("Built-in"), style=wx.RB_GROUP)

        sizer2.Add(self.radio_built_in, flag=wx.TOP|wx.LEFT , border=5)
        self.radio_built_in.Bind(wx.EVT_RADIOBUTTON, self.on_built_in)

        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        self.radio_choose = wx.RadioButton(self)
        hbox2.Add(self.radio_choose)
        self.radio_choose.Bind(wx.EVT_RADIOBUTTON, self.on_choose)

        self.tc_path = wx.TextCtrl(self)

        hbox2.Add(self.tc_path, proportion=1)
        self.button_browse = wx.Button(self, label=_("Browse..."))
        hbox2.Add(self.button_browse, flag=wx.LEFT, border=5)
        self.button_browse.Bind(wx.EVT_BUTTON, self.on_browse)

        sizer2.Add(hbox2, flag=wx.EXPAND|wx.ALL, border=5)

        main_sizer.Add(sizer2, flag=wx.EXPAND|wx.ALL, border=10)

        # ----------------------------------------------------------

        sbox3 = wx.StaticBox(self, label=_("Listen"))
        sizer3 = wx.StaticBoxSizer(sbox3, wx.VERTICAL)

        # SMTP

        hbox31 = wx.BoxSizer(wx.HORIZONTAL)
        self.checkbox_smtp = wx.CheckBox(self, label=_("SMTP"), size=(-1, -1))

        size_smtp = self.checkbox_smtp.GetSize()

        hbox31.Add(self.checkbox_smtp)
        text31 = wx.StaticText(self, label=_("Port"))
        hbox31.Add(text31, flag=wx.LEFT, border=10)
        self.ic_smtp = wx.lib.intctrl.IntCtrl(self, style=wx.TE_RIGHT)
        self.ic_smtp.SetMaxLength(8)
        self.ic_smtp.SetMaxSize((64,-1))

        hbox31.Add(self.ic_smtp, flag=wx.LEFT, border=5)
        sizer3.Add(hbox31, flag=wx.EXPAND|wx.ALL, border=5)

        # POP

        hbox32 = wx.BoxSizer(wx.HORIZONTAL)
        self.checkbox_pop = wx.CheckBox(self, label=_("POP"), size=size_smtp)

        hbox32.Add(self.checkbox_pop)
        text32 = wx.StaticText(self, label=_("Port"))
        hbox32.Add(text32, flag=wx.LEFT, border=10)
        self.ic_pop = wx.lib.intctrl.IntCtrl(self, style=wx.TE_RIGHT)
        self.ic_pop.SetMaxLength(8)
        self.ic_pop.SetMaxSize((64,-1))

        hbox32.Add(self.ic_pop, flag=wx.LEFT, border=5)
        sizer3.Add(hbox32, flag=wx.EXPAND|wx.ALL, border=5)

        # Initial State

        text33 = wx.StaticText(self, label=_("Initial State:"))
        sizer3.Add(text33, flag=wx.LEFT|wx.TOP, border=5)

        hbox33 = wx.BoxSizer(wx.HORIZONTAL)

        self.radio_start = wx.RadioButton(self, label=_("Start"), style=wx.RB_GROUP)
        hbox33.Add(self.radio_start, flag=wx.LEFT, border=50)

        self.radio_stop = wx.RadioButton(self, label=_("Stop"))
        hbox33.Add(self.radio_stop, flag=wx.LEFT, border=5)

        sizer3.Add(hbox33, flag=wx.TOP|wx.BOTTOM, border=5)

        main_sizer.Add(sizer3, flag=wx.ALL, border=10)

        # ----------------------------------------------------------

        sbox4 = wx.StaticBox(self, label=_("Block SMTP"))
        sizer4 = wx.StaticBoxSizer(sbox4, wx.VERTICAL)

        # To+Cc Max

        hbox41 = wx.BoxSizer(wx.HORIZONTAL)
        text41 = wx.StaticText(self, label=_("To+Cc Max"))
        hbox41.Add(text41, flag=wx.LEFT)

        self.to_cc_max = wx.SpinCtrl(self)
        self.to_cc_max.SetRange(0,100)

        hbox41.Add(self.to_cc_max, flag=wx.LEFT, border=5)

        text42 = wx.StaticText(self, label=_("Exclude"))
        hbox41.Add(text42, flag=wx.LEFT, border=10)
        self.to_cc_exclude = wx.TextCtrl(self)
        hbox41.Add(self.to_cc_exclude, flag=wx.LEFT, border=5, proportion=1)

        sizer4.Add(hbox41, flag=wx.EXPAND|wx.ALL, border=5)

        # Remove Header

        self.checkbox_remove_header = wx.CheckBox(self, label=_("Remove X-Mailer/User-Agent header"), size=(-1, -1))
        sizer4.Add(self.checkbox_remove_header, flag=wx.LEFT|wx.TOP|wx.BOTTOM, border=5)

        # Send Delay

        hbox44 = wx.BoxSizer(wx.HORIZONTAL)
        text44a = wx.StaticText(self, label=_("Send Delay"))
        hbox44.Add(text44a, flag=wx.LEFT)

        self.send_delay = wx.SpinCtrl(self)
        self.send_delay.SetRange(0,30)

        hbox44.Add(self.send_delay, flag=wx.LEFT, border=5)
        text44b = wx.StaticText(self, label=_("sec"))
        hbox44.Add(text44b, flag=wx.LEFT, border=5)
        sizer4.Add(hbox44, flag=wx.LEFT|wx.TOP|wx.BOTTOM, border=5)

        main_sizer.Add(sizer4, flag=wx.EXPAND|wx.ALL, border=10)

        # ----------------------------------------------------------

        # OK / Cancel

        hbox9 = wx.BoxSizer(wx.HORIZONTAL)
        
        self.button_ok = wx.Button(self, wx.ID_OK, label=_("OK"))
        self.button_ok.Bind(wx.EVT_BUTTON, self.on_ok)

        button_cancel = wx.Button(self, wx.ID_CANCEL, label=_("Cancel"))

        if parent.pf_windows:
            hbox9.Add(self.button_ok, flag=wx.LEFT, border=5)
            hbox9.Add(button_cancel, flag=wx.LEFT|wx.RIGHT, border=5)
        else:
            hbox9.Add(button_cancel, flag=wx.LEFT, border=5)
            hbox9.Add(self.button_ok, flag=wx.LEFT|wx.RIGHT, border=5)


        main_sizer.Add(hbox9, flag=wx.ALL|wx.ALIGN_RIGHT, border=10)

        # ----------------------------------------------------------

        self.SetSizerAndFit(main_sizer)
        self.Centre()

        # ----------------------------------------------------------

        self.tc_email.SetValue(parent.email)

        if parent.built_in:
            self.radio_built_in.SetValue(True)
            self.button_browse.Enable(False)
            if parent.pf_windows:
                self.tc_path.Enable(False)
        else:
            self.radio_choose.SetValue(True)
        self.tc_path.SetValue(parent.path)

        self.checkbox_smtp.SetValue(parent.smtp)
        self.ic_smtp.SetValue(parent.smtp_port)
        self.checkbox_pop.SetValue(parent.pop)
        self.ic_pop.SetValue(parent.pop_port)

        if parent.start_init:
            self.radio_start.SetValue(True)
        else:
            self.radio_stop.SetValue(True)

        self.to_cc_max.SetValue(parent.to_cc_max)
        self.to_cc_exclude.SetValue(parent.to_cc_exclude)
        self.checkbox_remove_header.SetValue(parent.remove_header)
        self.send_delay.SetValue(parent.send_delay)

    def on_text(self, e):
        email = self.tc_email.GetValue()
        if '@' in email:
            self.button_auth.Enable()
        else:
            self.button_auth.Enable(False)

    def on_auth(self, e):
        email = self.tc_email.GetValue()
        if not '@' in email or '\\' in email or '/' in email:
            wx.MessageBox(_("Invalid email"), caption=_("Error"), style=wx.ICON_ERROR)
            return
        
        store_dir = self.parent.store_dir
        if not os.path.exists(store_dir):
            os.makedirs(store_dir)

        token_file = self.parent.get_token_file(email)
        if os.path.exists(token_file):
            dlg = wx.MessageDialog(None, _("Reset auth-token?"), caption=_("Question"), style=wx.YES_NO|wx.NO_DEFAULT|wx.ICON_WARNING)
            result = dlg.ShowModal()
            dlg.Destroy()
            wx.Yield() # for mac
            if result == wx.ID_YES:
                os.remove(token_file)

        if not self.pf_windows: # for mac
            self.Iconize()

        error_msg = ''
        auth_ok = True
        try:
            self.parent.get_token(email)
        except Exception as e:
            error_name = e.__class__.__name__
            auth_ok = False

            if error_name == 'RefreshError':
                error_msg = e.args[0]
            else:
                error_msg = str(e)

        if not self.pf_windows: # for mac
            self.Iconize(False)
            self.Raise()

        if auth_ok:
            wx.MessageBox(_("Authorization was successful"), caption=_("Success"), style=wx.OK_DEFAULT)
        else:
            wx.MessageBox(error_msg, caption=_("Error"), style=wx.ICON_ERROR)

    def on_built_in(self, e):
        if self.parent.pf_windows:
            self.tc_path.Enable(False)
        self.tc_path.SetModified(False)
        self.button_browse.Enable(False)
     
    def on_choose(self, e):
        self.tc_path.Enable()
        self.button_browse.Enable()
    
    def on_browse(self, e):
        dlg = wx.FileDialog(self, _("Choose a file"), wildcard="JS files (*.js)|*.js|All files (*.*)|*.*", style=wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.tc_path.SetValue(dlg.GetPath())
        dlg.Destroy()

    def on_ok(self, e):
        email = self.tc_email.GetValue()
        if email:
            if not '@' in email or '\\' in email or '/' in email:
                wx.MessageBox(_("Invalid email"), caption=_("Error"), style=wx.ICON_ERROR)
                return

        built_in = self.radio_built_in.GetValue()

        if not built_in:
            path = self.tc_path.GetValue()
            if not os.path.exists(path):
                wx.MessageBox(_("File does not exist:") + "\n" + path, caption=_("Error"), style=wx.ICON_ERROR)
                return

        if not self.checkbox_smtp.GetValue() and not self.checkbox_pop.GetValue():
            wx.MessageBox(_("Both SMTP and POP are unchecked"), caption=_("Error"), style=wx.ICON_ERROR)
            return

        self.parent.email = email
        self.parent.built_in = built_in
        self.parent.path = self.tc_path.GetValue()
        self.parent.smtp = self.checkbox_smtp.GetValue()
        self.parent.smtp_port = self.ic_smtp.GetValue()
        self.parent.pop = self.checkbox_pop.GetValue()
        self.parent.pop_port = self.ic_pop.GetValue()
        self.parent.start_init = self.radio_start.GetValue()

        self.parent.to_cc_max = self.to_cc_max.GetValue()
        self.parent.to_cc_exclude = self.to_cc_exclude.GetValue()
        self.parent.remove_header = self.checkbox_remove_header.GetValue()
        self.parent.send_delay = self.send_delay.GetValue()

        self.EndModal(wx.ID_OK)
