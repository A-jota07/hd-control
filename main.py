#!/usr/bin/env python3
import os
import sys
import threading
import subprocess
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from modules.database import DatabaseManager
from modules.disk_manager import DiskManager
from modules.theme import DARK_CSS, LIGHT_CSS


class HDControlApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="HD Control Studio — Diagnóstico, Inventário e Provisionamento")
        self.set_default_size(980, 620)
        self.set_size_request(760, 480)
        self.set_resizable(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.db = DatabaseManager()
        self.is_dark_theme = True
        self.css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.connected_disks = []
        self.selected_live_disk = None
        self.selected_copy_items = []
        self._last_disk_signature = ""

        self._build_ui()
        self._apply_theme()
        self.refresh_all_data()

        # Monitoramento automático da porta USB / SATA a cada 4 segundos
        GLib.timeout_add_seconds(4, self._auto_poll_usb_drives)

    def _apply_theme(self):
        css = DARK_CSS if self.is_dark_theme else LIGHT_CSS
        self.css_provider.load_from_data(css.encode("utf-8"))
        if hasattr(self, "theme_btn"):
            self.theme_btn.set_label("☀  Tema Claro (P&B)" if self.is_dark_theme else "☾  Tema Escuro (P&B)")

    def _toggle_theme(self, _btn):
        self.is_dark_theme = not self.is_dark_theme
        self._apply_theme()

    def _build_ui(self):
        root_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root_vbox)

        # --- TOPBAR ---
        topbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        topbar.get_style_context().add_class("topbar")

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_hexpand(True)
        lbl_title = Gtk.Label(label="HD CONTROL // SISTEMA DE CONTROLE E PROVISIONAMENTO DE DISCOS")
        lbl_title.set_xalign(0)
        lbl_title.set_line_wrap(True)
        lbl_title.get_style_context().add_class("section-title")

        lbl_sub = Gtk.Label(
            label="Diagnóstico SMART (UDisks2/smartctl) • Controle de HDs • Formatação & Instalação de SO/Arquivos USB"
        )
        lbl_sub.set_xalign(0)
        lbl_sub.set_line_wrap(True)
        lbl_sub.get_style_context().add_class("subtitle")
        title_box.pack_start(lbl_title, False, False, 0)
        title_box.pack_start(lbl_sub, False, False, 0)
        topbar.pack_start(title_box, True, True, 0)

        btn_refresh = Gtk.Button(label="↻  Escanear USB")
        btn_refresh.connect("clicked", lambda _: self.refresh_all_data(notify=True))
        topbar.pack_end(btn_refresh, False, False, 0)

        self.theme_btn = Gtk.Button(label="☀  Tema Claro (P&B)")
        self.theme_btn.connect("clicked", self._toggle_theme)
        topbar.pack_end(self.theme_btn, False, False, 0)

        root_vbox.pack_start(topbar, False, False, 0)

        # --- KPI CARDS BAR ---
        kpi_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        kpi_box.set_margin_top(8)
        kpi_box.set_margin_bottom(4)
        kpi_box.set_margin_start(12)
        kpi_box.set_margin_end(12)

        self.kpi_total_lbl = self._create_kpi_card(kpi_box, "HDs REGISTRADOS", "0")
        self.kpi_working_lbl = self._create_kpi_card(kpi_box, "FUNCIONANDO", "0", highlight=True)
        self.kpi_defective_lbl = self._create_kpi_card(kpi_box, "COM DEFEITO", "0")
        self.kpi_testing_lbl = self._create_kpi_card(kpi_box, "EM TESTE", "0")
        self.kpi_needed_lbl = self._create_kpi_card(kpi_box, "PCs SEM HD/SSD", "0")

        root_vbox.pack_start(kpi_box, False, False, 0)

        # --- MAIN BODY (SIDEBAR + STACK) ---
        body_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        body_hbox.set_margin_top(4)
        root_vbox.pack_start(body_hbox, True, True, 0)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sidebar.set_size_request(210, -1)
        sidebar.get_style_context().add_class("sidebar")
        sidebar.set_margin_end(0)
        sidebar.set_border_width(8)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_size_request(218, -1)
        sidebar_scroll.add(sidebar)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)

        self.nav_buttons = {}
        pages = [
            ("scanner", "01. Leitor USB & Diagnóstico", self._build_scanner_page()),
            ("inventory", "02. Controle de HDs (Tabela)", self._build_inventory_page()),
            ("format_os", "03. Formatar & Instalar SO / Arq.", self._build_format_os_page()),
            ("lab_pcs", "04. Computadores & Bancada", self._build_lab_pcs_page()),
            ("logs", "05. Histórico de Operações", self._build_logs_page()),
        ]

        for page_id, page_title, widget in pages:
            if page_id == "scanner":
                # A tela do scanner (paned) gerencia a rolagem interna de forma responsiva
                self.stack.add_named(widget, page_id)
            else:
                scrolled = Gtk.ScrolledWindow()
                scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
                scrolled.add(widget)
                self.stack.add_named(scrolled, page_id)

            btn = Gtk.Button(label=page_title)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            for child in btn.get_children():
                if isinstance(child, Gtk.Label):
                    child.set_xalign(0)
            btn.connect("clicked", self._on_nav_clicked, page_id)
            sidebar.pack_start(btn, False, False, 0)
            self.nav_buttons[page_id] = btn

        # Atalho rápido para GSmartControl na barra lateral
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(12)
        sep.set_margin_bottom(12)
        sidebar.pack_start(sep, False, False, 0)

        lbl_ext = Gtk.Label(label="FERRAMENTAS INTEGRÁVEIS")
        lbl_ext.set_xalign(0)
        lbl_ext.get_style_context().add_class("stat-label")
        sidebar.pack_start(lbl_ext, False, False, 4)

        btn_gsmart = Gtk.Button(label="↗  Abrir GSmartControl")
        btn_gsmart.connect("clicked", self._open_gsmartcontrol)
        sidebar.pack_start(btn_gsmart, False, False, 0)

        btn_export = Gtk.Button(label="⬇  Exportar Relatório CSV")
        btn_export.connect("clicked", self._export_csv_dialog)
        sidebar.pack_start(btn_export, False, False, 0)

        body_hbox.pack_start(sidebar_scroll, False, False, 0)
        body_hbox.pack_start(self.stack, True, True, 0)

        # --- STATUS BAR ---
        status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        status_hbox.get_style_context().add_class("status-bar")
        self.status_label = Gtk.Label(
            label="Pronto. Monitoramento automático de HDs na porta USB/SATA ativo."
        )
        self.status_label.set_xalign(0)
        self.status_spinner = Gtk.Spinner()
        status_hbox.pack_start(self.status_spinner, False, False, 0)
        status_hbox.pack_start(self.status_label, True, True, 0)

        lbl_sync = Gtk.Label(label="Sincronizado com SQLite + workspace/HDs.txt")
        lbl_sync.get_style_context().add_class("mono")
        status_hbox.pack_end(lbl_sync, False, False, 0)

        root_vbox.pack_start(status_hbox, False, False, 0)

        self._update_nav_styles("scanner")

    def _create_kpi_card(self, parent_box, title: str, initial_val: str, highlight: bool = False):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.get_style_context().add_class("card-highlight" if highlight else "card")
        lbl_t = Gtk.Label(label=title)
        lbl_t.set_xalign(0)
        lbl_t.get_style_context().add_class("stat-label")
        lbl_v = Gtk.Label(label=initial_val)
        lbl_v.set_xalign(0)
        lbl_v.get_style_context().add_class("stat-value")
        card.pack_start(lbl_t, False, False, 0)
        card.pack_start(lbl_v, False, False, 0)
        parent_box.pack_start(card, True, True, 0)
        return lbl_v

    def _on_nav_clicked(self, _btn, page_id: str):
        self.stack.set_visible_child_name(page_id)
        self._update_nav_styles(page_id)

    def _update_nav_styles(self, active_id: str):
        for pid, btn in self.nav_buttons.items():
            ctx = btn.get_style_context()
            ctx.remove_class("nav-btn")
            ctx.remove_class("nav-btn-active")
            ctx.add_class("nav-btn-active" if pid == active_id else "nav-btn")

    def set_status(self, message: str, busy: bool = False):
        GLib.idle_add(self._set_status_ui, message, busy)

    def _set_status_ui(self, message: str, busy: bool):
        self.status_label.set_text(message)
        if busy:
            self.status_spinner.start()
        else:
            self.status_spinner.stop()

    # =========================================================================
    # ABA 1: LEITOR USB & DIAGNÓSTICO DE HDs CONECTADOS
    # =========================================================================
    def _build_scanner_page(self):
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_margin_top(8)
        paned.set_margin_bottom(8)
        paned.set_margin_start(10)
        paned.set_margin_end(10)
        paned.set_position(340)
        paned.set_wide_handle(True)

        # Lado Esquerdo: Lista de Discos Físicos Conectados
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left_box.set_margin_end(6)

        hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl = Gtk.Label(label="DISCOS CONECTADOS (USB / SATA / NVMe)")
        lbl.set_xalign(0)
        lbl.get_style_context().add_class("section-title")
        hdr_box.pack_start(lbl, True, True, 0)

        self.chk_show_sys = Gtk.CheckButton(label="Exibir sistema")
        self.chk_show_sys.set_active(True)
        self.chk_show_sys.connect("toggled", lambda _: self.refresh_connected_disks())
        hdr_box.pack_end(self.chk_show_sys, False, False, 0)
        left_box.pack_start(hdr_box, False, False, 0)

        # TreeView de discos ao vivo
        # Colunas: 0:DevPath, 1:Tipo/Porta, 2:Modelo, 3:Capacidade, 4:Serial, 5:Saúde SMART, 6:Status no Controle
        self.live_store = Gtk.ListStore(str, str, str, str, str, str, str)
        self.live_tree = Gtk.TreeView(model=self.live_store)
        self.live_tree.set_headers_visible(True)
        self.live_tree.get_selection().connect("changed", self._on_live_disk_selected)

        cols = [
            ("Dev", 0, 65),
            ("Porta", 1, 65),
            ("Modelo", 2, 115),
            ("Tam.", 3, 60),
            ("SMART", 5, 80),
            ("Status", 6, 80),
        ]
        for title, idx, width in cols:
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, renderer, text=idx)
            col.set_resizable(True)
            self.live_tree.append_column(col)

        scroll_live = Gtk.ScrolledWindow()
        scroll_live.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_live.set_vexpand(True)
        scroll_live.add(self.live_tree)
        left_box.pack_start(scroll_live, True, True, 0)

        hint = Gtk.Label(
            label="HDs no leitor USB aparecem no topo. Selecione um para ver detalhes."
        )
        hint.set_xalign(0)
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("subtitle")
        left_box.pack_start(hint, False, False, 0)

        # Lado Direito: Painel de Inspeção, Aprovação Rápida e Diagnóstico SMART
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right_box.set_margin_start(6)
        right_box.set_hexpand(True)

        card_detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_detail.get_style_context().add_class("card")
        card_detail.set_hexpand(True)

        self.lbl_sel_disk_title = Gtk.Label(label="Selecione um disco à esquerda")
        self.lbl_sel_disk_title.set_xalign(0)
        self.lbl_sel_disk_title.set_line_wrap(True)
        self.lbl_sel_disk_title.get_style_context().add_class("section-title")
        card_detail.pack_start(self.lbl_sel_disk_title, False, False, 0)

        self.lbl_sel_disk_meta = Gtk.Label(
            label="Informações técnicas, horas de uso e setores defeituosos serão exibidos aqui."
        )
        self.lbl_sel_disk_meta.set_xalign(0)
        self.lbl_sel_disk_meta.set_line_wrap(True)
        self.lbl_sel_disk_meta.get_style_context().add_class("mono")
        card_detail.pack_start(self.lbl_sel_disk_meta, False, False, 0)

        # Botões de Diagnóstico Técnico (Grid responsivo de 2 colunas para nunca truncar na lateral)
        diag_grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        diag_grid.set_hexpand(True)

        btn_smart_deep = Gtk.Button(label="🔍 Diagnóstico SMART")
        btn_smart_deep.set_hexpand(True)
        btn_smart_deep.connect("clicked", self._on_run_deep_smart)

        btn_surf_test = Gtk.Button(label="⚡ Teste Leitura I/O")
        btn_surf_test.set_hexpand(True)
        btn_surf_test.connect("clicked", self._on_run_surface_test)

        btn_go_format = Gtk.Button(label="⚙ Formatar / SO →")
        btn_go_format.set_hexpand(True)
        btn_go_format.connect("clicked", self._on_jump_to_format)

        diag_grid.attach(btn_smart_deep, 0, 0, 1, 1)
        diag_grid.attach(btn_surf_test, 1, 0, 1, 1)
        diag_grid.attach(btn_go_format, 0, 1, 2, 1)
        card_detail.pack_start(diag_grid, False, False, 0)

        # Formulário de Classificação Rápida no Controle de HDs
        sep_f = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        card_detail.pack_start(sep_f, False, False, 2)

        lbl_reg = Gtk.Label(label="CLASSIFICAR E SALVAR ESTE HD NO CONTROLE")
        lbl_reg.set_xalign(0)
        lbl_reg.get_style_context().add_class("stat-label")
        card_detail.pack_start(lbl_reg, False, False, 0)

        grid_reg = Gtk.Grid(column_spacing=8, row_spacing=6)
        grid_reg.set_hexpand(True)
        lbl_m = Gtk.Label(label="Máquina/Destino:")
        lbl_m.set_xalign(0)
        self.entry_quick_machine = Gtk.Entry()
        self.entry_quick_machine.set_placeholder_text("Ex: Dell #04, Bematech #01, Estoque LEIA...")
        self.entry_quick_machine.set_hexpand(True)

        lbl_n = Gtk.Label(label="Observações:")
        lbl_n.set_xalign(0)
        self.entry_quick_notes = Gtk.Entry()
        self.entry_quick_notes.set_placeholder_text("Ex: Sem bad blocks, ruído normal...")
        self.entry_quick_notes.set_hexpand(True)

        grid_reg.attach(lbl_m, 0, 0, 1, 1)
        grid_reg.attach(self.entry_quick_machine, 1, 0, 1, 1)
        grid_reg.attach(lbl_n, 0, 1, 1, 1)
        grid_reg.attach(self.entry_quick_notes, 1, 1, 1, 1)
        card_detail.pack_start(grid_reg, False, False, 0)

        verdict_grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        verdict_grid.set_hexpand(True)

        btn_mark_ok = Gtk.Button(label="✓ FUNCIONANDO")
        btn_mark_ok.get_style_context().add_class("primary-btn")
        btn_mark_ok.set_hexpand(True)
        btn_mark_ok.connect("clicked", self._on_quick_classify, "Funcionando")

        btn_mark_bad = Gtk.Button(label="✕ COM DEFEITO")
        btn_mark_bad.get_style_context().add_class("danger-btn")
        btn_mark_bad.set_hexpand(True)
        btn_mark_bad.connect("clicked", self._on_quick_classify, "Com Defeito")

        btn_mark_test = Gtk.Button(label="⏳ EM TESTE")
        btn_mark_test.set_hexpand(True)
        btn_mark_test.connect("clicked", self._on_quick_classify, "Em Teste")

        verdict_grid.attach(btn_mark_ok, 0, 0, 1, 1)
        verdict_grid.attach(btn_mark_bad, 1, 0, 1, 1)
        verdict_grid.attach(btn_mark_test, 0, 1, 2, 1)

        card_detail.pack_start(verdict_grid, False, False, 0)
        right_box.pack_start(card_detail, False, False, 0)

        # Saída do Relatório SMART / Partições
        lbl_rep = Gtk.Label(label="SAÍDA TÉCNICA SMART / PARTIÇÕES")
        lbl_rep.set_xalign(0)
        lbl_rep.get_style_context().add_class("stat-label")
        right_box.pack_start(lbl_rep, False, False, 0)

        self.smart_textview = Gtk.TextView()
        self.smart_textview.set_editable(False)
        self.smart_textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.smart_textview.get_style_context().add_class("mono")

        scroll_rep = Gtk.ScrolledWindow()
        scroll_rep.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_rep.set_size_request(-1, 140)
        scroll_rep.set_vexpand(True)
        scroll_rep.add(self.smart_textview)
        right_box.pack_start(scroll_rep, True, True, 0)

        # Envolve o lado direito em um ScrolledWindow responsivo nos dois eixos
        right_scroll = Gtk.ScrolledWindow()
        right_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        right_scroll.set_hexpand(True)
        right_scroll.set_vexpand(True)
        right_scroll.add(right_box)

        paned.pack1(left_box, resize=True, shrink=True)
        paned.pack2(right_scroll, resize=True, shrink=True)
        return paned

    # =========================================================================
    # ABA 2: CONTROLE DE HDs (BANCO DE DADOS COMPLETO + CADASTRO MANUAL)
    # =========================================================================
    def _build_inventory_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_top(8)
        vbox.set_margin_bottom(8)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        # Barra de Filtro e Busca
        filter_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label="CONTROLE DE HDs & SSDs")
        lbl.get_style_context().add_class("section-title")
        filter_bar.pack_start(lbl, False, False, 0)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Buscar serial, modelo...")
        self.search_entry.set_width_chars(18)
        self.search_entry.connect("changed", lambda _: self.refresh_drives_table())
        filter_bar.pack_start(self.search_entry, False, False, 4)

        self.filter_combo = Gtk.ComboBoxText()
        for st in ["Todos", "Funcionando", "Com Defeito", "Em Teste", "Formatado", "SO Instalado"]:
            self.filter_combo.append_text(st)
        self.filter_combo.set_active(0)
        self.filter_combo.connect("changed", lambda _: self.refresh_drives_table())
        filter_bar.pack_start(self.filter_combo, False, False, 0)

        btn_add_manual = Gtk.Button(label="+ Cadastrar HD")
        btn_add_manual.get_style_context().add_class("primary-btn")
        btn_add_manual.connect("clicked", self._on_add_manual_drive_dialog)
        filter_bar.pack_end(btn_add_manual, False, False, 0)

        vbox.pack_start(filter_bar, False, False, 0)

        # Tabela de HDs registrados
        self.drives_store = Gtk.ListStore(int, str, str, str, str, str, str, int, int, str, str, str)
        self.drives_tree = Gtk.TreeView(model=self.drives_store)
        self.drives_tree.get_selection().connect("changed", self._on_db_drive_selected)

        cols = [
            ("ID", 0, 40),
            ("Status", 1, 95),
            ("Modelo HD/SSD", 2, 140),
            ("Serial", 3, 110),
            ("Tam.", 4, 60),
            ("Tipo", 5, 55),
            ("SMART", 6, 80),
            ("Bad Sec.", 7, 65),
            ("Uso (h)", 8, 65),
            ("Destino", 9, 95),
            ("Observações", 10, 140),
            ("Último Teste", 11, 110),
        ]
        for title, idx, width in cols:
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, renderer, text=idx)
            col.set_resizable(True)
            col.set_sort_column_id(idx)
            self.drives_tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.add(self.drives_tree)
        vbox.pack_start(scroll, True, True, 0)

        # Barra de Edição do Item Selecionado (Grid compacto)
        edit_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        edit_card.get_style_context().add_class("card")

        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.lbl_edit_id = Gtk.Label(label="Selecione um HD acima:")
        self.lbl_edit_id.get_style_context().add_class("mono")
        row1.pack_start(self.lbl_edit_id, False, False, 0)

        self.combo_edit_status = Gtk.ComboBoxText()
        for st in ["Funcionando", "Com Defeito", "Em Teste", "Formatado", "SO Instalado"]:
            self.combo_edit_status.append_text(st)
        self.combo_edit_status.set_active(0)
        row1.pack_start(self.combo_edit_status, False, False, 0)

        self.entry_edit_machine = Gtk.Entry()
        self.entry_edit_machine.set_placeholder_text("Máquina / Destino...")
        self.entry_edit_machine.set_hexpand(True)
        row1.pack_start(self.entry_edit_machine, True, True, 0)

        btn_save_edit = Gtk.Button(label="Salvar Alterações")
        btn_save_edit.get_style_context().add_class("primary-btn")
        btn_save_edit.connect("clicked", self._on_save_db_drive_edit)
        row1.pack_end(btn_save_edit, False, False, 0)

        btn_del_drive = Gtk.Button(label="Excluir")
        btn_del_drive.get_style_context().add_class("danger-btn")
        btn_del_drive.connect("clicked", self._on_delete_db_drive)
        row1.pack_end(btn_del_drive, False, False, 0)
        edit_card.pack_start(row1, False, False, 0)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.entry_edit_notes = Gtk.Entry()
        self.entry_edit_notes.set_placeholder_text("Observações sobre o HD...")
        self.entry_edit_notes.set_hexpand(True)
        row2.pack_start(self.entry_edit_notes, True, True, 0)
        edit_card.pack_start(row2, False, False, 0)

        vbox.pack_start(edit_card, False, False, 0)
        return vbox

    # =========================================================================
    # ABA 3: FORMATAR HD, GRAVAR SO (ISO/IMG) E COPIAR ARQUIVOS
    # =========================================================================
    def _build_format_os_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_top(8)
        vbox.set_margin_bottom(8)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        # Seleção do Disco Alvo (Apenas discos NÃO-sistema podem ser formatados)
        target_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        target_card.get_style_context().add_class("card-highlight")

        lbl_t = Gtk.Label(label="DISCO ALVO (USB / SECUNDÁRIO):")
        lbl_t.get_style_context().add_class("section-title")
        target_card.pack_start(lbl_t, False, False, 0)

        self.combo_target_disk = Gtk.ComboBoxText()
        self.combo_target_disk.set_hexpand(True)
        target_card.pack_start(self.combo_target_disk, True, True, 0)

        btn_reload_targets = Gtk.Button(label="↻ Atualizar")
        btn_reload_targets.connect("clicked", lambda _: self.refresh_connected_disks())
        target_card.pack_start(btn_reload_targets, False, False, 0)

        vbox.pack_start(target_card, False, False, 0)

        # Notebook de Operações (Abas separadas em vez de 3 cards lado a lado)
        notebook = Gtk.Notebook()
        notebook.set_scrollable(True)

        # --- MÓDULO 1: FORMATAÇÃO ---
        fmt_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        fmt_card.set_border_width(10)
        fmt_card.get_style_context().add_class("card")

        lbl_f1 = Gtk.Label(label="1. FORMATAR HD / SSD")
        lbl_f1.set_xalign(0)
        lbl_f1.get_style_context().add_class("section-title")
        fmt_card.pack_start(lbl_f1, False, False, 0)

        lbl_f1_sub = Gtk.Label(
            label="Recria a tabela de partições (GPT/MBR) e formata o HD conectado no leitor USB."
        )
        lbl_f1_sub.set_xalign(0)
        lbl_f1_sub.set_line_wrap(True)
        lbl_f1_sub.get_style_context().add_class("subtitle")
        fmt_card.pack_start(lbl_f1_sub, False, False, 0)

        grid_fmt = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid_fmt.attach(Gtk.Label(label="Tabela de Partição:", xalign=0), 0, 0, 1, 1)
        self.combo_ptable = Gtk.ComboBoxText()
        self.combo_ptable.append_text("GPT (UEFI Moderno - Recomendado)")
        self.combo_ptable.append_text("MBR / MSDOS (BIOS Legado)")
        self.combo_ptable.set_active(0)
        grid_fmt.attach(self.combo_ptable, 1, 0, 1, 1)

        grid_fmt.attach(Gtk.Label(label="Sistema de Arquivos:", xalign=0), 0, 1, 1, 1)
        self.combo_fstype = Gtk.ComboBoxText()
        for fs in ["EXT4 (Linux Nativo)", "exFAT (Windows & Linux)", "FAT32 (Universal)", "BTRFS (Linux Moderno)"]:
            self.combo_fstype.append_text(fs)
        self.combo_fstype.set_active(0)
        grid_fmt.attach(self.combo_fstype, 1, 1, 1, 1)

        grid_fmt.attach(Gtk.Label(label="Rótulo (Nome do HD):", xalign=0), 0, 2, 1, 1)
        self.entry_fs_label = Gtk.Entry()
        self.entry_fs_label.set_text("HD_VERIFICADO")
        grid_fmt.attach(self.entry_fs_label, 1, 2, 1, 1)

        fmt_card.pack_start(grid_fmt, False, False, 4)

        btn_do_format = Gtk.Button(label="⚙ Formatar Disco Selecionado")
        btn_do_format.get_style_context().add_class("primary-btn")
        btn_do_format.connect("clicked", self._on_execute_format)
        fmt_card.pack_start(btn_do_format, False, False, 4)

        notebook.append_page(fmt_card, Gtk.Label(label="1. Formatar HD/SSD"))

        # --- MÓDULO 2: INSTALAR SO / GRAVAR IMAGEM ISO / CLONAR ---
        iso_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        iso_card.set_border_width(10)
        iso_card.get_style_context().add_class("card")

        lbl_f2 = Gtk.Label(label="2. INSTALAR SO / GRAVAR ISO OU IMG")
        lbl_f2.set_xalign(0)
        lbl_f2.get_style_context().add_class("section-title")
        iso_card.pack_start(lbl_f2, False, False, 0)

        lbl_f2_sub = Gtk.Label(
            label="Grava uma imagem de Sistema Operacional (.iso / .img) diretamente no HD externo."
        )
        lbl_f2_sub.set_xalign(0)
        lbl_f2_sub.set_line_wrap(True)
        lbl_f2_sub.get_style_context().add_class("subtitle")
        iso_card.pack_start(lbl_f2_sub, False, False, 0)

        lbl_iso_pick = Gtk.Label(label="Imagem ISO / IMG detectada ou selecione arquivo:", xalign=0)
        iso_card.pack_start(lbl_iso_pick, False, False, 0)

        iso_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry_iso_path = Gtk.Entry()
        self.entry_iso_path.set_hexpand(True)
        local_isos = DiskManager.find_local_isos()
        if local_isos:
            self.entry_iso_path.set_text(local_isos[0])
        else:
            self.entry_iso_path.set_placeholder_text("/caminho/para/sistema.iso")
        iso_hbox.pack_start(self.entry_iso_path, True, True, 0)

        btn_browse_iso = Gtk.Button(label="Procurar...")
        btn_browse_iso.connect("clicked", self._on_browse_iso)
        iso_hbox.pack_start(btn_browse_iso, False, False, 0)
        iso_card.pack_start(iso_hbox, False, False, 0)

        btn_flash_iso = Gtk.Button(label="💿 Gravar Imagem de SO no Disco (Direct Flash)")
        btn_flash_iso.get_style_context().add_class("primary-btn")
        btn_flash_iso.connect("clicked", self._on_execute_flash_iso)
        iso_card.pack_start(btn_flash_iso, False, False, 4)

        notebook.append_page(iso_card, Gtk.Label(label="2. Gravar Imagem de SO (ISO/IMG)"))

        # --- MÓDULO 3: COPIAR ARQUIVOS / PASTAS PADRÃO ---
        copy_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        copy_card.set_border_width(10)
        copy_card.get_style_context().add_class("card")

        lbl_f3 = Gtk.Label(label="3. TRANSFERIR ARQUIVOS / KIT PADRÃO")
        lbl_f3.set_xalign(0)
        lbl_f3.get_style_context().add_class("section-title")
        copy_card.pack_start(lbl_f3, False, False, 0)

        lbl_f3_sub = Gtk.Label(
            label="Monta a partição do HD externo e copia pastas, instaladores ou drivers."
        )
        lbl_f3_sub.set_xalign(0)
        lbl_f3_sub.set_line_wrap(True)
        lbl_f3_sub.get_style_context().add_class("subtitle")
        copy_card.pack_start(lbl_f3_sub, False, False, 0)

        pick_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_add_files = Gtk.Button(label="+ Arquivos")
        btn_add_files.connect("clicked", self._on_add_copy_files)
        pick_btns.pack_start(btn_add_files, False, False, 0)

        btn_add_folder = Gtk.Button(label="+ Pasta")
        btn_add_folder.connect("clicked", self._on_add_copy_folder)
        pick_btns.pack_start(btn_add_folder, False, False, 0)

        btn_clear_copy = Gtk.Button(label="Limpar")
        btn_clear_copy.connect("clicked", self._on_clear_copy_list)
        pick_btns.pack_start(btn_clear_copy, False, False, 0)
        copy_card.pack_start(pick_btns, False, False, 0)

        self.lbl_copy_list = Gtk.Label(label="Nenhum item selecionado.")
        self.lbl_copy_list.set_xalign(0)
        self.lbl_copy_list.set_line_wrap(True)
        self.lbl_copy_list.get_style_context().add_class("mono")
        copy_card.pack_start(self.lbl_copy_list, False, False, 0)

        subf_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        subf_box.pack_start(Gtk.Label(label="Subpasta destino:", xalign=0), False, False, 0)
        self.entry_dest_subfolder = Gtk.Entry()
        self.entry_dest_subfolder.set_text("Arquivos_Padrao")
        subf_box.pack_start(self.entry_dest_subfolder, True, True, 0)
        copy_card.pack_start(subf_box, False, False, 0)

        btn_do_copy = Gtk.Button(label="📁 Montar HD e Copiar Arquivos")
        btn_do_copy.get_style_context().add_class("primary-btn")
        btn_do_copy.connect("clicked", self._on_execute_copy_files)
        copy_card.pack_start(btn_do_copy, False, False, 4)

        notebook.append_page(copy_card, Gtk.Label(label="3. Transferir Arquivos / Pastas"))

        vbox.pack_start(notebook, False, False, 0)

        # Console de Saída de Provisionamento
        lbl_con = Gtk.Label(label="LOG DE EXECUÇÃO")
        lbl_con.set_xalign(0)
        lbl_con.get_style_context().add_class("stat-label")
        vbox.pack_start(lbl_con, False, False, 0)

        self.provision_textview = Gtk.TextView()
        self.provision_textview.set_editable(False)
        self.provision_textview.get_style_context().add_class("mono")
        scroll_p = Gtk.ScrolledWindow()
        scroll_p.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_p.set_size_request(-1, 130)
        scroll_p.set_vexpand(True)
        scroll_p.add(self.provision_textview)
        vbox.pack_start(scroll_p, True, True, 0)
        return vbox

    # =========================================================================
    # ABA 4: COMPUTADORES & BANCADA (IMPORTADO DE 'computadores' / LEIA)
    # =========================================================================
    def _build_lab_pcs_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_top(8)
        vbox.set_margin_bottom(8)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label="LEVANTAMENTO DE COMPUTADORES E PERIFÉRICOS")
        lbl.get_style_context().add_class("section-title")
        hdr.pack_start(lbl, True, True, 0)

        btn_add_pc_group = Gtk.Button(label="+ Adicionar Lote")
        btn_add_pc_group.connect("clicked", self._on_add_lab_item_dialog)
        hdr.pack_end(btn_add_pc_group, False, False, 0)
        vbox.pack_start(hdr, False, False, 0)

        # TreeView de lotes de computadores
        self.lab_store = Gtk.ListStore(int, str, str, int, int, int, int, int, int, int, int, str)
        self.lab_tree = Gtk.TreeView(model=self.lab_store)
        self.lab_tree.get_selection().connect("changed", self._on_lab_item_selected)

        cols = [
            ("ID", 0, 35),
            ("Cat.", 1, 75),
            ("Marca / Modelo", 2, 130),
            ("Total", 3, 50),
            ("Func.", 4, 55),
            ("Sem Func.", 5, 70),
            ("Com RAM", 6, 65),
            ("Sem RAM", 7, 65),
            ("HDD", 8, 45),
            ("SSD", 9, 45),
            ("Sem HD/SSD", 10, 80),
            ("Observações / Peças", 11, 160),
        ]
        for title, idx, width in cols:
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, renderer, text=idx)
            col.set_resizable(True)
            self.lab_tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.add(self.lab_tree)
        vbox.pack_start(scroll, True, True, 0)

        # Painel de atualização rápida das contagens (Grid 4 colunas compacto)
        edit_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        edit_card.get_style_context().add_class("card")

        lbl_ed = Gtk.Label(label="ATUALIZAR CONTAGEM DO LOTE SELECIONADO", xalign=0)
        lbl_ed.get_style_context().add_class("stat-label")
        edit_card.pack_start(lbl_ed, False, False, 0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        self.entry_lab_brand = Gtk.Entry()
        self.spin_lab_total = Gtk.SpinButton.new_with_range(0, 999, 1)
        self.spin_lab_working = Gtk.SpinButton.new_with_range(0, 999, 1)
        self.spin_lab_not_working = Gtk.SpinButton.new_with_range(0, 999, 1)
        self.spin_lab_with_hdd = Gtk.SpinButton.new_with_range(0, 999, 1)
        self.spin_lab_with_ssd = Gtk.SpinButton.new_with_range(0, 999, 1)
        self.spin_lab_no_storage = Gtk.SpinButton.new_with_range(0, 999, 1)
        self.spin_lab_with_ram = Gtk.SpinButton.new_with_range(0, 999, 1)
        self.spin_lab_no_ram = Gtk.SpinButton.new_with_range(0, 999, 1)
        self.entry_lab_notes = Gtk.Entry()
        self.entry_lab_notes.set_hexpand(True)

        grid.attach(Gtk.Label(label="Marca/Modelo:", xalign=0), 0, 0, 1, 1)
        grid.attach(self.entry_lab_brand, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Total:", xalign=0), 2, 0, 1, 1)
        grid.attach(self.spin_lab_total, 3, 0, 1, 1)

        grid.attach(Gtk.Label(label="Funcionando:", xalign=0), 0, 1, 1, 1)
        grid.attach(self.spin_lab_working, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="Sem Funcionar:", xalign=0), 2, 1, 1, 1)
        grid.attach(self.spin_lab_not_working, 3, 1, 1, 1)

        grid.attach(Gtk.Label(label="Com HDD:", xalign=0), 0, 2, 1, 1)
        grid.attach(self.spin_lab_with_hdd, 1, 2, 1, 1)
        grid.attach(Gtk.Label(label="Com SSD:", xalign=0), 2, 2, 1, 1)
        grid.attach(self.spin_lab_with_ssd, 3, 2, 1, 1)

        grid.attach(Gtk.Label(label="Sem HD/SSD:", xalign=0), 0, 3, 1, 1)
        grid.attach(self.spin_lab_no_storage, 1, 3, 1, 1)
        grid.attach(Gtk.Label(label="Com RAM:", xalign=0), 2, 3, 1, 1)
        grid.attach(self.spin_lab_with_ram, 3, 3, 1, 1)

        grid.attach(Gtk.Label(label="Sem RAM:", xalign=0), 0, 4, 1, 1)
        grid.attach(self.spin_lab_no_ram, 1, 4, 1, 1)
        btn_save_lab = Gtk.Button(label="Salvar Alterações do Lote")
        btn_save_lab.get_style_context().add_class("primary-btn")
        btn_save_lab.connect("clicked", self._on_save_lab_item)
        grid.attach(btn_save_lab, 2, 4, 2, 1)

        grid.attach(Gtk.Label(label="Observações:", xalign=0), 0, 5, 1, 1)
        grid.attach(self.entry_lab_notes, 1, 5, 3, 1)

        edit_card.pack_start(grid, False, False, 0)
        vbox.pack_start(edit_card, False, False, 0)
        return vbox

    # =========================================================================
    # ABA 5: HISTÓRICO DE OPERAÇÕES (AUDITORIA)
    # =========================================================================
    def _build_logs_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)

        lbl = Gtk.Label(label="HISTÓRICO DE DIAGNÓSTICOS, FORMATAÇÕES E INSTALAÇÕES", xalign=0)
        lbl.get_style_context().add_class("section-title")
        vbox.pack_start(lbl, False, False, 0)

        self.logs_store = Gtk.ListStore(int, str, str, str, str, str, str)
        tree = Gtk.TreeView(model=self.logs_store)
        cols = [
            ("ID", 0, 45),
            ("Data / Hora", 1, 145),
            ("Dispositivo", 2, 95),
            ("Serial", 3, 150),
            ("Operação", 4, 120),
            ("Resultado", 5, 95),
            ("Detalhes", 6, 400),
        ]
        for title, idx, width in cols:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=idx)
            col.set_resizable(True)
            col.set_min_width(width)
            tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.add(tree)
        vbox.pack_start(scroll, True, True, 0)
        return vbox

    # =========================================================================
    # ATUALIZAÇÃO DE DADOS E MONITORAMENTO USB
    # =========================================================================
    def _auto_poll_usb_drives(self):
        try:
            disks = DiskManager.list_disks(include_system_disks=self.chk_show_sys.get_active())
            sig = "|".join(f"{d['name']}:{d['serial']}:{len(d['partitions'])}" for d in disks)
            if sig != self._last_disk_signature:
                self._last_disk_signature = sig
                self.refresh_connected_disks()
                self.set_status("Alteração de discos detectada na porta USB/SATA! Lista atualizada.")
        except Exception:
            pass
        return True

    def refresh_all_data(self, notify: bool = False):
        self.refresh_kpis()
        self.refresh_connected_disks()
        self.refresh_drives_table()
        self.refresh_lab_table()
        self.refresh_logs_table()
        if notify:
            self.set_status("Todos os discos e tabelas foram sincronizados.")

    def refresh_kpis(self):
        stats = self.db.get_drive_stats()
        self.kpi_total_lbl.set_text(str(stats["total"]))
        self.kpi_working_lbl.set_text(str(stats["working"]))
        self.kpi_defective_lbl.set_text(str(stats["defective"]))
        self.kpi_testing_lbl.set_text(str(stats["testing"]))
        self.kpi_needed_lbl.set_text(str(stats["needed_for_pcs"]))

    def refresh_connected_disks(self):
        show_sys = self.chk_show_sys.get_active()
        self.connected_disks = DiskManager.list_disks(include_system_disks=show_sys)
        self.live_store.clear()

        # Atualizar também o combo de discos alvo na aba de Formatação (somente NÃO-sistema)
        prev_target = self.combo_target_disk.get_active_id() if hasattr(self, "combo_target_disk") else None
        if hasattr(self, "combo_target_disk"):
            self.combo_target_disk.remove_all()

        for d in self.connected_disks:
            db_rec = self.db.get_drive_by_serial(d["serial"])
            ctrl_status = db_rec["status"] if db_rec else "Não Registrado"
            port_badge = "🔌 USB" if d["is_external"] else ("🔒 SISTEMA" if d["is_system"] else f"SATA/Int ({d['drive_type']})")

            self.live_store.append(
                [
                    d["path"],
                    port_badge,
                    d["model"],
                    d["size_human"],
                    d["serial"] or "S/N Indisponível",
                    d["smart_status"],
                    ctrl_status,
                ]
            )

            if hasattr(self, "combo_target_disk") and not d["is_system"]:
                tag = "PORTA USB" if d["is_external"] else "DISCO SECUNDÁRIO"
                label = f"[{tag}] {d['path']} — {d['model']} ({d['size_human']}) | S/N: {d['serial'] or 'N/A'}"
                self.combo_target_disk.append(d["path"], label)

        if hasattr(self, "combo_target_disk"):
            if prev_target and self.combo_target_disk.set_active_id(prev_target):
                pass
            else:
                self.combo_target_disk.set_active(0)

    def refresh_drives_table(self):
        status_filter = self.filter_combo.get_active_text() if hasattr(self, "filter_combo") else "Todos"
        query = self.search_entry.get_text().strip() if hasattr(self, "search_entry") else ""
        rows = self.db.get_all_drives(filter_status=status_filter, search_query=query)
        self.drives_store.clear()
        for r in rows:
            self.drives_store.append(
                [
                    r["id"],
                    r["status"],
                    r["model"] or "",
                    r["serial"] or "",
                    r["capacity"] or "",
                    r["drive_type"] or "",
                    r["smart_status"] or "",
                    int(r["bad_sectors"] or 0),
                    int(r["power_on_hours"] or 0),
                    r["assigned_machine"] or "",
                    r["notes"] or "",
                    r["last_tested"] or "",
                ]
            )
        self.refresh_kpis()

    def refresh_lab_table(self):
        items = self.db.get_lab_inventory()
        self.lab_store.clear()
        for it in items:
            self.lab_store.append(
                [
                    it["id"],
                    it["category"],
                    it["brand_model"],
                    it["total"],
                    it["working"],
                    it["not_working"],
                    it["with_ram"],
                    it["without_ram"],
                    it["with_hdd"],
                    it["with_ssd"],
                    it["without_storage"],
                    it["notes"] or "",
                ]
            )
        self.refresh_kpis()

    def refresh_logs_table(self):
        logs = self.db.get_logs()
        self.logs_store.clear()
        for lg in logs:
            self.logs_store.append(
                [
                    lg["id"],
                    lg["timestamp"],
                    lg["device"] or "",
                    lg["serial"] or "",
                    lg["operation_type"] or "",
                    lg["status"] or "",
                    lg["details"] or "",
                ]
            )

    # =========================================================================
    # EVENTOS DA ABA 1 (DIAGNÓSTICO E CLASSIFICAÇÃO RÁPIDA)
    # =========================================================================
    def _on_live_disk_selected(self, selection):
        model, treeiter = selection.get_selected()
        if not treeiter:
            return
        dev_path = model[treeiter][0]
        disk = next((d for d in self.connected_disks if d["path"] == dev_path), None)
        if not disk:
            return
        self.selected_live_disk = disk

        sys_warn = " [DISCO DO SISTEMA ATUAL - PROTEGIDO]" if disk["is_system"] else ""
        self.lbl_sel_disk_title.set_text(f"{disk['model']} ({disk['size_human']}) — {disk['path']}{sys_warn}")

        meta_lines = [
            f"Serial (S/N):      {disk['serial'] or 'Não informado'}",
            f"Tipo / Barramento: {disk['drive_type']} | Barramento: {disk['tran'].upper()} | Tabela: {disk['ptype']}",
            f"Saúde SMART:       {disk['smart_status']} | Bad Sectors: {disk['bad_sectors']} | Horas Ligado: {disk['power_on_hours']} h",
        ]
        self.lbl_sel_disk_meta.set_text("\n".join(meta_lines))

        # Preencher campos se já existir no banco
        existing = self.db.get_drive_by_serial(disk["serial"])
        if existing:
            self.entry_quick_machine.set_text(existing.get("assigned_machine") or "")
            self.entry_quick_notes.set_text(existing.get("notes") or "")
        else:
            self.entry_quick_machine.set_text("")
            default_note = (
                f"SMART: {disk['smart_status']}, BadSectors: {disk['bad_sectors']}, Uso: {disk['power_on_hours']}h"
            )
            self.entry_quick_notes.set_text(default_note)

        # Mostrar partições e resumo SMART no textview
        part_lines = ["=== PARTIÇÕES DETECTADAS NO DISCO ==="]
        if not disk["partitions"]:
            part_lines.append("Nenhuma partição encontrada (Disco limpo / não alocado).")
        else:
            for p in disk["partitions"]:
                mp_str = ", ".join(p["mountpoints"]) if p["mountpoints"] else "Desmontada"
                part_lines.append(
                    f"• {p['path']} | Tam: {p['size']} | Formato: {p['fstype']} | Rótulo: {p['label'] or '-'} | Montagem: {mp_str}"
                )

        part_lines.append("\n=== RESUMO DE SAÚDE SMART (UDisks2) ===")
        part_lines.append(f"Status Geral:     {disk['smart_status']}")
        part_lines.append(f"Bad Sectors:      {disk['bad_sectors']}")
        part_lines.append(f"Horas de Uso:     {disk['power_on_hours']} horas (~{disk['power_on_hours']//24} dias)")
        part_lines.append(f"Último Self-Test: {disk['selftest_status'] or 'N/A'}")
        part_lines.append(
            "\nClique em 'Diagnóstico SMART Completo (smartctl)' acima para ler a tabela completa de atributos ATA/NVMe."
        )
        self._set_textview(self.smart_textview, "\n".join(part_lines))

    def _on_quick_classify(self, _btn, status_val: str):
        if not self.selected_live_disk:
            self._show_message("Selecione um disco conectado na lista à esquerda primeiro.")
            return
        d = self.selected_live_disk
        drive_data = {
            "serial": d["serial"] or f"DEV-{d['name']}-{d['model']}",
            "model": d["model"],
            "vendor": d["vendor"],
            "capacity": d["size_human"],
            "drive_type": d["drive_type"],
            "connection_bus": d["tran"],
            "device_node": d["path"],
            "smart_status": d["smart_status"],
            "bad_sectors": d["bad_sectors"],
            "power_on_hours": d["power_on_hours"],
            "temperature": d["temperature_c"],
            "status": status_val,
            "assigned_machine": self.entry_quick_machine.get_text().strip(),
            "notes": self.entry_quick_notes.get_text().strip(),
        }
        serial = self.db.upsert_drive(drive_data)
        self.db.add_log(
            d["path"],
            serial,
            "CLASSIFICACAO",
            "SUCCESS",
            f"HD classificado como '{status_val}' (Destino: {drive_data['assigned_machine'] or 'Estoque'})",
        )
        self.refresh_all_data()
        self.set_status(f"HD {d['model']} ({serial}) salvo no controle como: {status_val}!")

    def _on_run_deep_smart(self, _btn):
        if not self.selected_live_disk:
            self._show_message("Selecione um disco conectado primeiro.")
            return
        disk = self.selected_live_disk
        self.set_status(f"Executando diagnóstico smartctl completo em {disk['path']}...", busy=True)

        def worker():
            res = DiskManager.run_detailed_smart_check(disk["path"])
            GLib.idle_add(self._finish_deep_smart, disk, res)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_deep_smart(self, disk, res):
        self.set_status(f"Diagnóstico SMART concluído para {disk['path']}.", busy=False)
        self._set_textview(self.smart_textview, res.get("raw_report", ""))
        if res.get("smart_status") != "UNKNOWN":
            disk["smart_status"] = res["smart_status"]
            disk["bad_sectors"] = res.get("bad_sectors", disk["bad_sectors"])
            disk["power_on_hours"] = res.get("power_on_hours", disk["power_on_hours"])
        self.db.add_log(
            disk["path"],
            disk.get("serial", ""),
            "SMART_CHECK",
            "SUCCESS",
            f"SMART: {disk['smart_status']} | BadSectors: {disk['bad_sectors']} | Horas: {disk['power_on_hours']}",
        )
        self.refresh_logs_table()

    def _on_run_surface_test(self, _btn):
        if not self.selected_live_disk:
            self._show_message("Selecione um disco conectado primeiro.")
            return
        disk = self.selected_live_disk
        self.set_status(f"Testando leitura de superfície (I/O direto) em {disk['path']}...", busy=True)

        def worker():
            res = DiskManager.run_quick_surface_test(disk["path"])
            GLib.idle_add(self._finish_surface_test, disk, res)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_surface_test(self, disk, res):
        self.set_status(res["message"], busy=False)
        status_str = "SUCCESS" if res["success"] else "ERROR"
        self.db.add_log(disk["path"], disk.get("serial", ""), "SURFACE_READ_TEST", status_str, res["message"])
        self._append_textview(self.smart_textview, f"\n\n=== TESTE DE SUPERFÍCIE / LEITURA ===\n{res['message']}")
        self.refresh_logs_table()

    def _on_jump_to_format(self, _btn):
        if self.selected_live_disk:
            if self.selected_live_disk["is_system"]:
                self._show_message("O disco selecionado contém o seu Sistema Operacional atual e não pode ser formatado.")
                return
            self.combo_target_disk.set_active_id(self.selected_live_disk["path"])
        self._on_nav_clicked(None, "format_os")

    # =========================================================================
    # EVENTOS DA ABA 2 (TABELA DE CONTROLE DE HDs)
    # =========================================================================
    def _on_db_drive_selected(self, selection):
        model, treeiter = selection.get_selected()
        if not treeiter:
            return
        drive_id = model[treeiter][0]
        status = model[treeiter][1]
        serial = model[treeiter][3]
        machine = model[treeiter][9]
        notes = model[treeiter][10]

        self._selected_db_drive_id = drive_id
        self.lbl_edit_id.set_text(f"ID #{drive_id} ({serial}):")
        statuses = ["Funcionando", "Com Defeito", "Em Teste", "Formatado", "SO Instalado"]
        if status in statuses:
            self.combo_edit_status.set_active(statuses.index(status))
        self.entry_edit_machine.set_text(machine)
        self.entry_edit_notes.set_text(notes)

    def _on_save_db_drive_edit(self, _btn):
        drive_id = getattr(self, "_selected_db_drive_id", None)
        if not drive_id:
            self._show_message("Selecione um HD na tabela acima para editar.")
            return
        status = self.combo_edit_status.get_active_text()
        machine = self.entry_edit_machine.get_text().strip()
        notes = self.entry_edit_notes.get_text().strip()
        self.db.update_drive_by_id(drive_id, status, machine, notes)
        self.refresh_drives_table()
        self.refresh_connected_disks()
        self.set_status(f"Registro #{drive_id} atualizado para '{status}'.")

    def _on_delete_db_drive(self, _btn):
        drive_id = getattr(self, "_selected_db_drive_id", None)
        if not drive_id:
            return
        if self._confirm_dialog(
            "Excluir Registro",
            f"Deseja remover o registro #{drive_id} da lista de controle?\n\n"
            f"A numeração dos demais HDs será ajustada dinamicamente para ocupar este espaço (sem pular números)."
        ):
            self.db.delete_drive(drive_id)
            self._selected_db_drive_id = None
            self.refresh_drives_table()
            self.refresh_connected_disks()
            self.set_status(f"Registro #{drive_id} removido. Numeração reordenada dinamicamente.")

    def _on_add_manual_drive_dialog(self, _btn):
        dialog = Gtk.Dialog(title="Cadastrar HD / SSD Manualmente", transient_for=self, flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Salvar HD", Gtk.ResponseType.OK)
        dialog.set_default_size(440, 320)

        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(14)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        e_model = Gtk.Entry(placeholder_text="Ex: Seagate Barracuda / Kingston A400")
        e_serial = Gtk.Entry(placeholder_text="Ex: ST500DM002-1BD142")
        e_cap = Gtk.Entry(placeholder_text="Ex: 500 GB / 240 GB")
        c_type = Gtk.ComboBoxText()
        for t in ["HDD", "SSD", "NVMe", "HDD (USB)"]:
            c_type.append_text(t)
        c_type.set_active(0)

        c_status = Gtk.ComboBoxText()
        for s in ["Funcionando", "Com Defeito", "Em Teste", "Formatado", "SO Instalado"]:
            c_status.append_text(s)
        c_status.set_active(0)

        e_machine = Gtk.Entry(placeholder_text="Ex: Dell #02 / Estoque")
        e_notes = Gtk.Entry(placeholder_text="Observações do teste...")
        e_notes.set_hexpand(True)

        fields = [
            ("Modelo:", e_model),
            ("Nº de Série:", e_serial),
            ("Capacidade:", e_cap),
            ("Tipo:", c_type),
            ("Status:", c_status),
            ("Máquina/Destino:", e_machine),
            ("Observações:", e_notes),
        ]
        for idx, (lbl_txt, widget) in enumerate(fields):
            grid.attach(Gtk.Label(label=lbl_txt, xalign=0), 0, idx, 1, 1)
            grid.attach(widget, 1, idx, 1, 1)

        box.add(grid)
        dialog.show_all()
        resp = dialog.run()
        if resp == Gtk.ResponseType.OK:
            self.db.upsert_drive(
                {
                    "serial": e_serial.get_text().strip(),
                    "model": e_model.get_text().strip() or "HD Manual",
                    "capacity": e_cap.get_text().strip() or "—",
                    "drive_type": c_type.get_active_text(),
                    "connection_bus": "manual",
                    "smart_status": "MANUAL",
                    "status": c_status.get_active_text(),
                    "assigned_machine": e_machine.get_text().strip(),
                    "notes": e_notes.get_text().strip(),
                }
            )
            self.refresh_drives_table()
        dialog.destroy()

    # =========================================================================
    # EVENTOS DA ABA 3 (FORMATAR, GRAVAR SO E COPIAR ARQUIVOS)
    # =========================================================================
    def _get_selected_target_disk(self):
        dev_path = self.combo_target_disk.get_active_id()
        if not dev_path:
            self._show_message("Nenhum disco externo/secundário selecionado.")
            return None
        disk = next((d for d in self.connected_disks if d["path"] == dev_path), None)
        if not disk:
            self._show_message("Disco não encontrado. Clique em Atualizar Discos.")
            return None
        if disk["is_system"]:
            self._show_message("Operação bloqueada: Este é o disco do sistema operacional!")
            return None
        return disk

    def _on_execute_format(self, _btn):
        disk = self._get_selected_target_disk()
        if not disk:
            return
        ptable = "gpt" if "GPT" in self.combo_ptable.get_active_text() else "msdos"
        fs_raw = self.combo_fstype.get_active_text()
        fs_type = fs_raw.split()[0].lower()
        label = self.entry_fs_label.get_text().strip() or "HD_DADOS"

        msg = (
            f"ATENÇÃO: Todos os dados no disco {disk['path']} ({disk['model']} - {disk['size_human']}) "
            f"serão apagados!\n\nTabela: {ptable.upper()}\nFormato: {fs_type.upper()}\nRótulo: {label}\n\n"
            f"Confirmar formatação?"
        )
        if not self._confirm_dialog("Confirmar Formatação de HD", msg):
            return

        self.set_status(f"Formatando {disk['path']} em {fs_type.upper()}...", busy=True)
        self._append_textview(
            self.provision_textview,
            f"Iniciando formatação de {disk['path']} ({disk['model']}) em {fs_type.upper()}...\n",
        )

        def worker():
            res = DiskManager.format_disk(
                device_path=disk["path"],
                fs_type=fs_type,
                label=label,
                partition_table=ptable,
                is_system=disk["is_system"],
            )
            GLib.idle_add(self._finish_format, disk, fs_type, res)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_format(self, disk, fs_type, res):
        self.set_status(res["message"], busy=False)
        self._append_textview(self.provision_textview, res["message"] + "\n")
        status_log = "SUCCESS" if res["success"] else "ERROR"
        self.db.add_log(disk["path"], disk.get("serial", ""), f"FORMAT_{fs_type.upper()}", status_log, res["message"])
        if res["success"]:
            self.db.upsert_drive(
                {
                    "serial": disk["serial"],
                    "model": disk["model"],
                    "capacity": disk["size_human"],
                    "drive_type": disk["drive_type"],
                    "connection_bus": disk["tran"],
                    "device_node": disk["path"],
                    "smart_status": disk["smart_status"],
                    "status": "Formatado",
                    "notes": f"Formatado em {fs_type.upper()} com sucesso.",
                }
            )
        self.refresh_all_data()

    def _on_browse_iso(self, _btn):
        dlg = Gtk.FileChooserDialog(
            title="Selecionar Imagem ISO ou IMG de Sistema Operacional",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        flt = Gtk.FileFilter()
        flt.set_name("Imagens de Disco / SO (*.iso, *.img, *.raw)")
        flt.add_pattern("*.iso")
        flt.add_pattern("*.ISO")
        flt.add_pattern("*.img")
        flt.add_pattern("*.raw")
        dlg.add_filter(flt)
        if dlg.run() == Gtk.ResponseType.OK:
            self.entry_iso_path.set_text(dlg.get_filename())
        dlg.destroy()

    def _on_execute_flash_iso(self, _btn):
        disk = self._get_selected_target_disk()
        if not disk:
            return
        iso_path = self.entry_iso_path.get_text().strip()
        if not iso_path or not os.path.exists(iso_path):
            self._show_message("Selecione um arquivo .iso ou .img válido.")
            return

        msg = (
            f"Deseja gravar a imagem de SO:\n'{os.path.basename(iso_path)}'\n\n"
            f"Diretamente no disco {disk['path']} ({disk['model']} - {disk['size_human']})?\n"
            f"Isso substituirá todas as partições atuais do HD."
        )
        if not self._confirm_dialog("Confirmar Gravação de SO / Imagem", msg):
            return

        self.set_status(f"Gravando imagem {os.path.basename(iso_path)} em {disk['path']}...", busy=True)
        self._append_textview(
            self.provision_textview,
            f"Iniciando gravação de '{iso_path}' para {disk['path']} (pode levar alguns minutos)...\n",
        )

        def worker():
            res = DiskManager.flash_iso_or_image(
                source_image=iso_path,
                target_device=disk["path"],
                is_system=disk["is_system"],
            )
            GLib.idle_add(self._finish_flash_iso, disk, iso_path, res)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_flash_iso(self, disk, iso_path, res):
        self.set_status(res["message"], busy=False)
        self._append_textview(self.provision_textview, res["message"] + "\n")
        status_log = "SUCCESS" if res["success"] else "ERROR"
        self.db.add_log(disk["path"], disk.get("serial", ""), "ISO_FLASH", status_log, res["message"])
        if res["success"]:
            self.db.upsert_drive(
                {
                    "serial": disk["serial"],
                    "model": disk["model"],
                    "capacity": disk["size_human"],
                    "drive_type": disk["drive_type"],
                    "connection_bus": disk["tran"],
                    "device_node": disk["path"],
                    "smart_status": disk["smart_status"],
                    "status": "SO Instalado",
                    "notes": f"Imagem gravada: {os.path.basename(iso_path)}",
                }
            )
        self.refresh_all_data()

    def _on_add_copy_files(self, _btn):
        dlg = Gtk.FileChooserDialog(
            title="Selecionar Arquivos para Copiar para o HD",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dlg.set_select_multiple(True)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dlg.run() == Gtk.ResponseType.OK:
            for f in dlg.get_filenames():
                if f not in self.selected_copy_items:
                    self.selected_copy_items.append(f)
            self._update_copy_list_label()
        dlg.destroy()

    def _on_add_copy_folder(self, _btn):
        dlg = Gtk.FileChooserDialog(
            title="Selecionar Pasta para Copiar para o HD",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dlg.run() == Gtk.ResponseType.OK:
            folder = dlg.get_filename()
            if folder and folder not in self.selected_copy_items:
                self.selected_copy_items.append(folder)
            self._update_copy_list_label()
        dlg.destroy()

    def _on_clear_copy_list(self, _btn):
        self.selected_copy_items.clear()
        self._update_copy_list_label()

    def _update_copy_list_label(self):
        if not self.selected_copy_items:
            self.lbl_copy_list.set_text("Nenhum item selecionado.")
        else:
            names = [os.path.basename(p.rstrip("/")) for p in self.selected_copy_items]
            self.lbl_copy_list.set_text(f"{len(names)} item(ns): " + ", ".join(names))

    def _on_execute_copy_files(self, _btn):
        disk = self._get_selected_target_disk()
        if not disk:
            return
        if not self.selected_copy_items:
            self._show_message("Adicione pelo menos um arquivo ou pasta para copiar.")
            return
        if not disk["partitions"]:
            self._show_message(
                f"O disco {disk['path']} ainda não possui partições! Formate-o primeiro no painel '1. Formatar HD / SSD'."
            )
            return

        target_part = disk["partitions"][0]["path"]
        subf = self.entry_dest_subfolder.get_text().strip()
        items_copy = list(self.selected_copy_items)

        self.set_status(f"Montando {target_part} e copiando arquivos...", busy=True)
        self._append_textview(
            self.provision_textview,
            f"Copiando {len(items_copy)} item(ns) para a partição {target_part}...\n",
        )

        def worker():
            res = DiskManager.mount_and_copy_files(
                partition_path=target_part,
                source_paths=items_copy,
                dest_subfolder=subf,
            )
            GLib.idle_add(self._finish_copy_files, disk, target_part, res)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_copy_files(self, disk, target_part, res):
        self.set_status(res["message"], busy=False)
        self._append_textview(self.provision_textview, res["message"] + "\n")
        status_log = "SUCCESS" if res["success"] else "ERROR"
        self.db.add_log(target_part, disk.get("serial", ""), "FILE_COPY", status_log, res["message"])
        self.refresh_logs_table()

    # =========================================================================
    # EVENTOS DA ABA 4 (COMPUTADORES & BANCADA)
    # =========================================================================
    def _on_lab_item_selected(self, selection):
        model, treeiter = selection.get_selected()
        if not treeiter:
            return
        row = model[treeiter]
        self._selected_lab_id = row[0]
        self.entry_lab_brand.set_text(row[2])
        self.spin_lab_total.set_value(row[3])
        self.spin_lab_working.set_value(row[4])
        self.spin_lab_not_working.set_value(row[5])
        self.spin_lab_with_ram.set_value(row[6])
        self.spin_lab_no_ram.set_value(row[7])
        self.spin_lab_with_hdd.set_value(row[8])
        self.spin_lab_with_ssd.set_value(row[9])
        self.spin_lab_no_storage.set_value(row[10])
        self.entry_lab_notes.set_text(row[11])

    def _on_save_lab_item(self, _btn):
        item_id = getattr(self, "_selected_lab_id", None)
        if not item_id:
            self._show_message("Selecione uma linha na tabela de computadores acima primeiro.")
            return
        data = {
            "brand_model": self.entry_lab_brand.get_text().strip(),
            "total": self.spin_lab_total.get_value_as_int(),
            "working": self.spin_lab_working.get_value_as_int(),
            "not_working": self.spin_lab_not_working.get_value_as_int(),
            "with_ram": self.spin_lab_with_ram.get_value_as_int(),
            "without_ram": self.spin_lab_no_ram.get_value_as_int(),
            "with_hdd": self.spin_lab_with_hdd.get_value_as_int(),
            "with_ssd": self.spin_lab_with_ssd.get_value_as_int(),
            "without_storage": self.spin_lab_no_storage.get_value_as_int(),
            "notes": self.entry_lab_notes.get_text().strip(),
        }
        self.db.update_lab_item(item_id, data)
        self.refresh_lab_table()
        self.set_status(f"Inventário '{data['brand_model']}' atualizado!")

    def _on_add_lab_item_dialog(self, _btn):
        dialog = Gtk.Dialog(title="Adicionar Lote de Computadores / Periféricos", transient_for=self, flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Adicionar", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(14)

        e_cat = Gtk.ComboBoxText()
        e_cat.append_text("Computador")
        e_cat.append_text("Periférico")
        e_cat.set_active(0)
        e_brand = Gtk.Entry(placeholder_text="Ex: Lenovo ThinkCentre / Monitores")
        e_total = Gtk.SpinButton.new_with_range(0, 999, 1)
        e_notes = Gtk.Entry(placeholder_text="Observações...")

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.attach(Gtk.Label(label="Categoria:", xalign=0), 0, 0, 1, 1)
        grid.attach(e_cat, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Marca/Modelo:", xalign=0), 0, 1, 1, 1)
        grid.attach(e_brand, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="Quantidade Total:", xalign=0), 0, 2, 1, 1)
        grid.attach(e_total, 1, 2, 1, 1)
        grid.attach(Gtk.Label(label="Observações:", xalign=0), 0, 3, 1, 1)
        grid.attach(e_notes, 1, 3, 1, 1)

        box.add(grid)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK and e_brand.get_text().strip():
            self.db.add_lab_item(
                {
                    "category": e_cat.get_active_text(),
                    "brand_model": e_brand.get_text().strip(),
                    "total": e_total.get_value_as_int(),
                    "notes": e_notes.get_text().strip(),
                }
            )
            self.refresh_lab_table()
        dialog.destroy()

    # =========================================================================
    # UTILITÁRIOS DE UI E ATALHOS EXTERNOS
    # =========================================================================
    def _open_gsmartcontrol(self, _btn):
        try:
            if sys.platform == "win32":
                gsmart_path = shutil.which("gsmartcontrol") or r"C:\Program Files\GSmartControl\gsmartcontrol.exe"
                if os.path.exists(gsmart_path) or shutil.which("gsmartcontrol"):
                    subprocess.Popen([gsmart_path])
                    self.set_status("Abrindo GSmartControl no Windows...")
                else:
                    self._show_message("GSmartControl não encontrado no Windows.\nInstale via: winget install gsmartcontrol")
            else:
                # Tenta abrir direto sem pkexec se possível
                if shutil.which("gsmartcontrol"):
                    try:
                        subprocess.Popen(["gsmartcontrol"])
                    except Exception:
                        subprocess.Popen(["pkexec", "gsmartcontrol"])
                    self.set_status("Abrindo GSmartControl...")
                else:
                    self._show_message("GSmartControl não encontrado no sistema Linux.\nInstale via seu gerenciador de pacotes (ex: pacman -S gsmartcontrol).")
        except Exception as e:
            self._show_message(f"Não foi possível iniciar o GSmartControl: {e}")

    def _export_csv_dialog(self, _btn):
        dlg = Gtk.FileChooserDialog(
            title="Exportar Relatório Dinâmico de HDs (CSV)",
            parent=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dlg.set_do_overwrite_confirmation(True)
        dlg.set_current_name("relatorio_hds_verificados.csv")
        if dlg.run() == Gtk.ResponseType.OK:
            path = dlg.get_filename()
            if not path.lower().endswith(".csv"):
                path += ".csv"
            
            filter_status = self.filter_combo.get_active_text() if hasattr(self, "filter_combo") else None
            search_query = self.search_entry.get_text().strip() if hasattr(self, "search_entry") else None
            count = self.db.export_to_csv(path, filter_status=filter_status, search_query=search_query)
            
            self.set_status(f"Relatório CSV exportado com sucesso ({count} HDs): {path}")
            self._show_message(
                f"Exportação concluída com sucesso!\n\n"
                f"Arquivo: {path}\n"
                f"Total de HDs contabilizados: {count}\n\n"
                f"A numeração (#1 até #{count}) é contínua e dinâmica, sem saltos ou inclusão de HDs excluídos."
            )
        dlg.destroy()

    def _set_textview(self, tv: Gtk.TextView, text: str):
        buf = tv.get_buffer()
        buf.set_text(text)

    def _append_textview(self, tv: Gtk.TextView, text: str):
        buf = tv.get_buffer()
        end_iter = buf.get_end_iter()
        buf.insert(end_iter, text)

    def _show_message(self, message: str):
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        dlg.run()
        dlg.destroy()

    def _confirm_dialog(self, title: str, message: str) -> bool:
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=title,
        )
        dlg.format_secondary_text(message)
        resp = dlg.run()
        dlg.destroy()
        return resp == Gtk.ResponseType.YES


def main():
    win = HDControlApp()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
