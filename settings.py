#
# settings.py (for O2Popper)
#
# Copyright (c) 2020-2022 MURATA Yasuhisa
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

        notebook = wx.Notebook(self)
        panel1 = wx.Panel(notebook)
        panel2 = wx.Panel(notebook)
        panel3 = wx.Panel(notebook)

        main_sizer.Add(notebook, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.TOP|wx.RIGHT, border=8)

        # ----------------------------------------------------------

        panel1_sizer = wx.BoxSizer(wx.VERTICAL)

        text11 = wx.StaticText(panel1, label=_("Your email:"))
        panel1_sizer.Add(text11, flag=wx.LEFT|wx.TOP, border=10)

        hbox11 = wx.BoxSizer(wx.HORIZONTAL)
        self.cb_email = wx.ComboBox(panel1)
        self.cb_email.SetMinSize((250, -1))
        self.cb_email.SetToolTip(_("Please don't input group-address!"))

        hbox11.Add(self.cb_email, proportion=1)
        self.cb_email.Bind(wx.EVT_TEXT, self.on_text)

        self.button_auth = wx.Button(panel1, label=_("Auth..."))
        hbox11.Add(self.button_auth, flag=wx.LEFT, border=5)
        self.button_auth.Bind(wx.EVT_BUTTON, self.on_auth)

        panel1_sizer.Add(hbox11, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=10)

        hbox12 = wx.BoxSizer(wx.HORIZONTAL)
        hbox12.Add((10, -1))
        self.checkbox_login_hint = wx.CheckBox(panel1, label=_("Send login_hint"))
        hbox12.Add(self.checkbox_login_hint)
        hbox12.Add((5, -1))
        self.choice_actions = wx.Choice(panel1, choices=[_("Actions"), _("Add"), _("Remove")])
        self.choice_actions.SetToolTip(_("Account Actions"))
        self.choice_actions.SetSelection(0)
        hbox12.Add(self.choice_actions, proportion=1)
        self.choice_actions.Bind(wx.EVT_CHOICE, self.on_choice_actions)
        hbox12.Add((5, -1))

        panel1_sizer.Add((-1, 5))
        panel1_sizer.Add(hbox12, flag=wx.ALIGN_RIGHT|wx.RIGHT, border=85)

        # ----------------------------------------------------------

        text13 = wx.StaticText(panel1, label=_("Secret File:"))
        panel1_sizer.Add(text13, flag=wx.LEFT|wx.TOP, border=10)
        panel1_sizer.Add((-1, 5))

        self.radio_built_in = wx.RadioButton(panel1, label=_("Built-in"), style=wx.RB_GROUP)

        panel1_sizer.Add(self.radio_built_in, flag=wx.LEFT, border=10)
        self.radio_built_in.Bind(wx.EVT_RADIOBUTTON, self.on_built_in)

        hbox13 = wx.BoxSizer(wx.HORIZONTAL)
        self.radio_choose = wx.RadioButton(panel1)
        hbox13.Add(self.radio_choose)
        self.radio_choose.Bind(wx.EVT_RADIOBUTTON, self.on_choose)

        self.tc_path = wx.TextCtrl(panel1)

        hbox13.Add(self.tc_path, proportion=1)
        self.button_browse = wx.Button(panel1, label=_("Browse..."))
        hbox13.Add(self.button_browse, flag=wx.LEFT, border=5)
        self.button_browse.Bind(wx.EVT_BUTTON, self.on_browse)

        panel1_sizer.Add((-1, 5))
        panel1_sizer.Add(hbox13, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=10)

        # ----------------------------------------------------------

        cp = wx.CollapsiblePane(panel1, label=_("Details"), style=wx.CP_DEFAULT_STYLE)
        cpane = cp.GetPane()
        cpane_sizer = wx.BoxSizer(wx.VERTICAL)

        text14 = wx.StaticText(cpane, label=_("Client ID:"))
        cpane_sizer.Add(text14)

        hbox14 = wx.BoxSizer(wx.HORIZONTAL)
        self.tc_client_id = wx.TextCtrl(cpane)
        self.tc_client_id.Enable(False)

        hbox14.Add(self.tc_client_id, proportion=1)

        self.button_edit1 = wx.Button(cpane, label=_("Edit"))
        hbox14.Add(self.button_edit1, flag=wx.LEFT, border=5)
        self.button_edit1.Bind(wx.EVT_BUTTON, self.on_button_edit1)

        cpane_sizer.Add(hbox14, flag=wx.EXPAND)

        text15 = wx.StaticText(cpane, label=_("Client Secret:"))

        cpane_sizer.Add(text15, flag=wx.TOP, border=10)

        hbox15 = wx.BoxSizer(wx.HORIZONTAL)
        self.tc_client_secret = wx.TextCtrl(cpane)
        self.tc_client_secret.Enable(False)

        hbox15.Add(self.tc_client_secret, proportion=1)

        self.button_edit2 = wx.Button(cpane, label=_("Edit"))
        hbox15.Add(self.button_edit2, flag=wx.LEFT, border=5)
        self.button_edit2.Bind(wx.EVT_BUTTON, self.on_button_edit2)

        cpane_sizer.Add(hbox15, flag=wx.EXPAND)

        text16 = wx.StaticText(cpane, label=_("Parameters:"))
        cpane_sizer.Add(text16, flag=wx.TOP, border=10)

        self.params = wx.TextCtrl(cpane, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP)
        self.params.SetMinSize((-1, 18*3 + 14))

        cpane_sizer.Add(self.params, proportion=1, flag=wx.EXPAND)
        cpane.SetSizer(cpane_sizer)

        panel1_sizer.Add(cp, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        panel1.SetSizer(panel1_sizer)

        self.params.SetBackgroundColour(wx.Colour(240, 240, 240))

        # ----------------------------------------------------------

        panel2_sizer = wx.BoxSizer(wx.VERTICAL)

        # SMTP

        hbox31 = wx.BoxSizer(wx.HORIZONTAL)
        self.checkbox_smtp = wx.CheckBox(panel2, label=_("SMTP"))

        size_smtp = self.checkbox_smtp.GetSize()

        hbox31.Add(self.checkbox_smtp)
        text31 = wx.StaticText(panel2, label=_("Port"))
        hbox31.Add(text31, flag=wx.LEFT, border=10)
        self.ic_smtp = wx.lib.intctrl.IntCtrl(panel2, style=wx.TE_RIGHT, size=(64, -1))
        self.ic_smtp.SetMaxLength(8)

        hbox31.Add(self.ic_smtp, flag=wx.LEFT, border=5)
        panel2_sizer.Add(hbox31, flag=wx.EXPAND|wx.LEFT|wx.TOP, border=10)

        # POP

        hbox32 = wx.BoxSizer(wx.HORIZONTAL)
        self.checkbox_pop = wx.CheckBox(panel2, label=_("POP"), size=size_smtp)

        hbox32.Add(self.checkbox_pop)
        text32 = wx.StaticText(panel2, label=_("Port"))
        hbox32.Add(text32, flag=wx.LEFT, border=10)
        self.ic_pop = wx.lib.intctrl.IntCtrl(panel2, style=wx.TE_RIGHT, size=(64, -1))
        self.ic_pop.SetMaxLength(8)

        hbox32.Add(self.ic_pop, flag=wx.LEFT, border=5)
        panel2_sizer.Add(hbox32, flag=wx.EXPAND|wx.LEFT|wx.TOP, border=10)

        # IMAP

        hbox33 = wx.BoxSizer(wx.HORIZONTAL)
        self.checkbox_imap = wx.CheckBox(panel2, label=_("IMAP"), size=size_smtp)

        hbox33.Add(self.checkbox_imap)
        text33 = wx.StaticText(panel2, label=_("Port"))
        hbox33.Add(text33, flag=wx.LEFT, border=10)
        self.ic_imap = wx.lib.intctrl.IntCtrl(panel2, style=wx.TE_RIGHT, size=(64, -1))
        self.ic_imap.SetMaxLength(8)

        hbox33.Add(self.ic_imap, flag=wx.LEFT, border=5)
        panel2_sizer.Add(hbox33, flag=wx.EXPAND|wx.LEFT|wx.TOP, border=10)

        # Initial State

        text34 = wx.StaticText(panel2, label=_("Initial State:"))
        panel2_sizer.Add(text34, flag=wx.LEFT|wx.TOP, border=10)

        hbox34 = wx.BoxSizer(wx.HORIZONTAL)

        self.radio_start = wx.RadioButton(panel2, label=_("Start"), style=wx.RB_GROUP)
        hbox34.Add(self.radio_start, flag=wx.LEFT, border=55)

        self.radio_stop = wx.RadioButton(panel2, label=_("Stop"))
        hbox34.Add(self.radio_stop, flag=wx.LEFT, border=5)

        panel2_sizer.Add(hbox34, flag=wx.TOP, border=5)

        panel2.SetSizer(panel2_sizer)

        # ----------------------------------------------------------

        panel3_sizer = wx.BoxSizer(wx.VERTICAL)

        # To+Cc Max

        hbox41 = wx.BoxSizer(wx.HORIZONTAL)
        text41 = wx.StaticText(panel3, label=_("To+Cc Max"))
        hbox41.Add(text41, flag=wx.LEFT)

        self.to_cc_max = wx.SpinCtrl(panel3)
        self.to_cc_max.SetRange(0,100)

        hbox41.Add(self.to_cc_max, flag=wx.LEFT, border=5)

        text42 = wx.StaticText(panel3, label=_("Exclude"))
        hbox41.Add(text42, flag=wx.LEFT, border=10)
        self.to_cc_exclude = wx.TextCtrl(panel3)
        hbox41.Add(self.to_cc_exclude, flag=wx.LEFT, border=5, proportion=1)

        panel3_sizer.Add(hbox41, flag=wx.EXPAND|wx.ALL, border=10)

        hbox43 = wx.BoxSizer(wx.HORIZONTAL)
        text43a = wx.StaticText(panel3, label=_("Send Delay"))
        hbox43.Add(text43a, flag=wx.LEFT)

        self.send_delay = wx.SpinCtrl(panel3)
        self.send_delay.SetRange(0,30)

        hbox43.Add(self.send_delay, flag=wx.LEFT, border=5)
        text43b = wx.StaticText(panel3, label=_("sec"))
        hbox43.Add(text43b, flag=wx.LEFT, border=5)

        panel3_sizer.Add(hbox43, flag=wx.LEFT|wx.BOTTOM, border=10)

        # Remove Header

        self.checkbox_remove_header = wx.CheckBox(panel3, label=_("Remove X-Mailer/User-Agent header"))

        panel3_sizer.Add(self.checkbox_remove_header, flag=wx.LEFT|wx.BOTTOM, border=10)

        # Change Envelope-From

        self.checkbox_change_env_from = wx.CheckBox(panel3, label=_("Change Envelope-From"))

        panel3_sizer.Add(self.checkbox_change_env_from, flag=wx.LEFT|wx.BOTTOM, border=10)

        # Block list

        text44 = wx.StaticText(panel3, label=_("Block list:"))
        panel3_sizer.Add(text44, flag=wx.LEFT, border=10)

        self.block_list = wx.TextCtrl(panel3, style=wx.TE_MULTILINE)
        panel3_sizer.Add(self.block_list, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

        panel3.SetSizer(panel3_sizer)

        # ----------------------------------------------------------

        notebook.AddPage(panel1, _("OAuth2"))
        notebook.AddPage(panel2, _("Listen"))
        notebook.AddPage(panel3, _("Block SMTP"))

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

        main_sizer.Add(hbox9, flag=wx.ALL|wx.ALIGN_RIGHT, border=8)

        # ----------------------------------------------------------

        self.SetSizerAndFit(main_sizer)
        self.Centre()

        # ----------------------------------------------------------

        self.path_edit_flag = True

        self.cb_select = -1 # main-edit mode

        # deepcopy: from parent.sub_data to self.sub_data
        sub_data = {}
        for k, v in parent.sub_data.items():
            sub_data[k] = v.copy()
        self.sub_data = sub_data

        email = parent.email

        if self.sub_data:
            self.cb_email.SetItems(list(self.sub_data)) # on_text() is called here
        self.cb_email.SetValue(email) # on_text() is called here

        self.client_id = parent.client_id
        self.client_secret = parent.client_secret

        if self.cb_select >= 0: # sub-edit mode
            self.set_sub_data(email)
        else: # main-edit mode
            self.checkbox_login_hint.SetValue(parent.login_hint)

            if parent.built_in:
                self.radio_built_in.SetValue(True)
                self.button_browse.Enable(False)
                if parent.pf_windows:
                    self.tc_path.Enable(False)
            else:
                self.radio_choose.SetValue(True)
            self.tc_path.SetValue(parent.path)

            if self.client_id:
                self.tc_client_id.SetValue('*' * len(self.client_id))
            if self.client_secret:
                self.tc_client_secret.SetValue('*' * len(self.client_secret))

            self.params.SetValue(parent.params_info)

        self.checkbox_smtp.SetValue(parent.smtp)
        self.ic_smtp.SetValue(parent.smtp_port)
        self.checkbox_pop.SetValue(parent.pop)
        self.ic_pop.SetValue(parent.pop_port)
        self.checkbox_imap.SetValue(parent.imap)
        self.ic_imap.SetValue(parent.imap_port)

        if parent.start_init:
            self.radio_start.SetValue(True)
        else:
            self.radio_stop.SetValue(True)

        self.to_cc_max.SetValue(parent.to_cc_max)
        self.to_cc_exclude.SetValue(parent.to_cc_exclude)
        self.send_delay.SetValue(parent.send_delay)
        self.checkbox_remove_header.SetValue(parent.remove_header)
        self.checkbox_change_env_from.SetValue(parent.change_env_from)
        self.block_list.SetValue(parent.block_list)

        self.tc_path.Bind(wx.EVT_TEXT, self.on_path)

    def on_text(self, e):
        email = self.cb_email.GetValue()
        i = email.find('@')
        if i <= 0 or i >= len(email) - 1:
            self.button_auth.Enable(False)
            return

        cb_select_bak = self.cb_select
        self.cb_select = self.cb_email.FindString(email)

        if cb_select_bak >= 0 and self.cb_select >= 0:
            accounts = self.cb_email.GetItems()
            self.set_sub_data_before(accounts[cb_select_bak])
            self.set_sub_data(email)
            return

        self.button_auth.Enable()

    def set_sub_data(self, email):
        account_data = self.sub_data[email]

        login_hint = account_data.get('login_hint', False)
        self.checkbox_login_hint.SetValue(login_hint)

        built_in = account_data.get('built_in', False)
        if built_in:
            self.radio_built_in.SetValue(True)
            self.button_browse.Enable(False)
            if self.parent.pf_windows:
                self.tc_path.Enable(False)
        else:
            self.radio_choose.SetValue(True)
            self.button_browse.Enable(True)
            if self.parent.pf_windows:
                self.tc_path.Enable(True)

        path = account_data.get('path', '')
        self.path_edit_flag = False
        self.tc_path.SetValue(path)
        self.path_edit_flag = True

        self.client_id = account_data.get('client_id', None)
        if self.client_id:
            if self.tc_client_id.IsEnabled():
                self.tc_client_id.SetValue(self.client_id)
            else:
                self.tc_client_id.SetValue('*' * len(self.client_id))
        else:
            self.tc_client_id.SetValue('')

        self.client_secret = account_data.get('client_secret', None)
        if self.client_secret:
            if self.tc_client_secret.IsEnabled():
                self.tc_client_secret.SetValue(self.client_secret)
            else:
                self.tc_client_secret.SetValue('*' * len(self.client_secret))
        else:
            self.tc_client_secret.SetValue('')
        
        sub_info = self.parent.params_sub_info.get(email, '')
        self.params.SetValue(sub_info)
        if sub_info:
            self.button_auth.Enable()
        else:
            self.button_auth.Enable(False)

    def set_sub_data_before(self, email):
        account_data = self.sub_data[email]

        v_old = account_data.get('login_hint', False)
        v = self.checkbox_login_hint.GetValue()
        if v != v_old:
            account_data['login_hint'] = v

        v_old = account_data.get('built_in', False)
        v = self.radio_built_in.GetValue()
        if v != v_old:
            account_data['built_in'] = v

        v_old = account_data.get('path', '')
        v = self.tc_path.GetValue()
        if v != v_old:
            account_data['path'] = v

        if self.tc_client_id.IsEnabled():
            v_old = account_data.get('client_id')
            v = self.tc_client_id.GetValue()
            if v != v_old:
                if v:
                    account_data['client_id'] = v
                else:
                    account_data.pop('client_id', None)

        if self.tc_client_secret.IsEnabled():
            v_old = account_data.get('client_secret')
            v  = self.tc_client_secret.GetValue()
            if v != v_old:
                if v:
                    account_data['client_secret'] = v
                else:
                    account_data.pop('client_secret', None)

    def on_choice_actions(self, e):
        email = self.cb_email.GetValue()
        if not email:
            self.choice_actions.SetSelection(0)
            return

        i = self.choice_actions.GetSelection()
        j = self.cb_email.FindString(email)
 
        if i == 1: # Add Account
            if j >= 0:
                self.choice_actions.SetSelection(0)
                return
            if not '@' in email or '\\' in email or '/' in email:
                wx.MessageBox(_("Invalid email"), caption=_("Error"), style=wx.ICON_ERROR)
                self.choice_actions.SetSelection(0)
                return

            built_in = self.radio_built_in.GetValue()
            if not built_in:
                path = self.tc_path.GetValue()
                if not os.path.exists(path):
                    wx.MessageBox(_("File does not exist:") + "\n" + path, caption=_("Error"), style=wx.ICON_ERROR)
                    self.choice_actions.SetSelection(0) # dev
                    return

            login_hint = self.checkbox_login_hint.GetValue()
            path = self.tc_path.GetValue()
            if self.tc_client_id.IsEnabled():
                client_id = self.tc_client_id.GetValue()
            else:
                client_id = None
            if self.tc_client_secret.IsEnabled():
                client_secret = self.tc_client_secret.GetValue()
            else:
                client_secret = None

            account_data = {
                'login_hint': login_hint,
                'built_in': built_in,
                'path': path,
            }
            if client_id:
                account_data['client_id'] = client_id
            if client_secret:
                account_data['client_secret'] = client_secret

            self.cb_email.Append(email)
            self.sub_data[email] = account_data
        elif i == 2: # Remove Account
            if j < 0:
                self.choice_actions.SetSelection(0)
                return
            self.cb_email.SetSelection(j)
            self.cb_email.Delete(j)
            self.sub_data.pop(email, None)

        self.choice_actions.SetSelection(0)
        self.cb_email.SetValue("")
        self.cb_select = -1

    def on_auth(self, e):
        email = self.cb_email.GetValue()
        if not '@' in email or '\\' in email or '/' in email:
            wx.MessageBox(_("Invalid email"), caption=_("Error"), style=wx.ICON_ERROR)
            return
        if self.checkbox_login_hint.GetValue():
            login_hint = True
        else:
            login_hint = None
        store_dir = self.parent.store_dir
        if not os.path.exists(store_dir):
            os.makedirs(store_dir)

        user_params = self.parent.args.user_params
        if email in user_params:
            params = user_params[email]
        else:
            params = self.parent.params
        token_file = params.get_token_file(email)
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
            params.get_token(email, login_hint)
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
        self.button_auth.Enable(False)
        self.set_disable_auth()

    def on_choose(self, e):
        self.tc_path.Enable()
        self.button_browse.Enable()
        self.set_disable_auth()

    def on_browse(self, e):
        dlg = wx.FileDialog(self, _("Choose a file"), wildcard="JS files (*.js)|*.js|All files (*.*)|*.*", style=wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.tc_path.SetValue(dlg.GetPath())
        dlg.Destroy()

    def on_path(self, e):
        if self.path_edit_flag:
            self.set_disable_auth()

    def set_disable_auth(self):
        self.button_auth.Enable(False)
        self.params.SetValue('')
        if self.cb_select >= 0: # sub-edit mode
            email = self.cb_email.GetValue()
            self.parent.params_sub_info.pop(email, None)

    def on_button_edit1(self, e):
        self.tc_client_id.Enable()
        self.button_edit1.Enable(False)
        if self.client_id:
            self.tc_client_id.SetValue(self.client_id)
        self.tc_client_id.SetFocus()

    def on_button_edit2(self, e):
        self.tc_client_secret.Enable()
        self.button_edit2.Enable(False)
        if self.client_secret:
            self.tc_client_secret.SetValue(self.client_secret)
        self.tc_client_secret.SetFocus()

    def on_ok(self, e):
        email = self.cb_email.GetValue()
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

        if not self.checkbox_smtp.GetValue() and not self.checkbox_pop.GetValue() and not self.checkbox_imap.GetValue():
            wx.MessageBox(_("SMTP, POP and IMAP are all unchecked"), caption=_("Error"), style=wx.ICON_ERROR)
            return

        login_hint = self.checkbox_login_hint.GetValue()
        path = self.tc_path.GetValue()

        if self.tc_client_id.IsEnabled():
            v = self.tc_client_id.GetValue()
            if v:
                client_id = v
            else:
                client_id = None
        else:
            client_id = self.client_id
        if self.tc_client_secret.IsEnabled():
            v = self.tc_client_secret.GetValue()
            if v:
                client_secret = v
            else:
                client_secret = None
        else:
            client_secret = self.client_secret

        if email:
            j = self.cb_email.FindString(email)
        else:
            j = -1

        if j >= 0: # sub-edit mode
            # save account
            account_data = {
                'login_hint': login_hint,
                'built_in': built_in,
                'path': path,
            }
            if client_id:
                account_data['client_id'] = client_id
            if client_secret:
                account_data['client_secret'] = client_secret

            self.sub_data[email] = account_data

        self.parent.email = email
        self.parent.login_hint = login_hint
        self.parent.built_in = built_in
        self.parent.path = path
        self.parent.client_id = client_id
        self.parent.client_secret = client_secret

        self.parent.smtp = self.checkbox_smtp.GetValue()
        self.parent.smtp_port = self.ic_smtp.GetValue()
        self.parent.pop = self.checkbox_pop.GetValue()
        self.parent.pop_port = self.ic_pop.GetValue()
        self.parent.imap = self.checkbox_imap.GetValue()
        self.parent.imap_port = self.ic_imap.GetValue()
        self.parent.start_init = self.radio_start.GetValue()

        self.parent.to_cc_max = self.to_cc_max.GetValue()
        self.parent.to_cc_exclude = self.to_cc_exclude.GetValue()
        self.parent.send_delay = self.send_delay.GetValue()
        self.parent.remove_header = self.checkbox_remove_header.GetValue()
        self.parent.change_env_from = self.checkbox_change_env_from.GetValue()
        self.parent.block_list = self.block_list.GetValue()

        self.parent.sub_data = self.sub_data

        self.EndModal(wx.ID_OK)
