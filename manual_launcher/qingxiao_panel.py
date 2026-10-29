"""Personal Qingxiao console, reusing the verified local-task controller."""
from __future__ import annotations
from collections import deque
import html
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
import uuid
from PySide6.QtCore import Qt,QTimer,QUrl,QObject,Signal,QSharedMemory
from PySide6.QtGui import QDesktopServices,QFont,QFontDatabase,QIcon,QPixmap,QKeySequence,QShortcut
from PySide6.QtWidgets import (QApplication,QCheckBox,QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,
    QFileDialog,QFormLayout,QFrame,QGridLayout,QHBoxLayout,QHeaderView,QLabel,QLineEdit,QMenu,
    QMessageBox,QPlainTextEdit,QPushButton,QScrollArea,QSpinBox,QStackedWidget,QSystemTrayIcon,
    QTableWidget,QTableWidgetItem,QTextBrowser,QVBoxLayout,QWidget)
from legacy_panel import Panel as LegacyPanel,TaskScroll
from model import ROOT,RUNS,JOBS,STATES,atomic_json,make_request,read_json,normalize_enhance_rules,enhancement_summary,normalize_helper_options,MAIN_STATS
from catalog import CATALOG,TOOL_LINKS
from history import RunHistory,IncrementalTail
from assistant import llm_plan,load_settings,save_settings,validate_plan
from widgets import Hero,ProgressRing,RunChart
from accounts import load_accounts,retry_accounts
from account_ui import AccountsPage
from runtime_settings import game_executable,save_game_executable,panel_instance_key,asset_path

ASSETS=ROOT/'manual_launcher/assets'
STYLE='''
QMainWindow,QWidget#surface{background:#f0f6f4;color:#163f42} QLabel{color:#163f42;background:transparent}
QLabel#muted,QLabel#subtle{color:#688580;font-size:12px} QLabel#heading{font-size:25px;font-weight:650}
QLabel#section{font-size:19px;font-weight:650} QLabel#cardTitle{font-size:16px;font-weight:650} QLabel#heroTitle{font-family:KaiTi;font-size:36px}
QLabel#badge{background:#e1efe9;color:#247d70;border-radius:11px;padding:6px 11px}
QFrame#rail{background:#e7f0ed;border:1px solid #d9e8e1;border-radius:22px}
QFrame#card,QFrame#status{background:#fbfdfc;border:1px solid #d6e6df;border-radius:19px}
QPushButton{background:#2e8478;color:white;border:0;border-radius:10px;padding:10px 16px;font-weight:600}
QPushButton:hover{background:#236e64} QPushButton:disabled{background:#d8e4df;color:#849b92}
QPushButton#nav{text-align:left;background:transparent;color:#51766c;padding:13px 18px;font-weight:500}
QPushButton#nav:checked{background:#f8fcf9;color:#1e776a;border-left:3px solid #69b9a9}
QPushButton#secondary{background:#e5efea;color:#285f53} QPushButton#secondary:hover{background:#d4e6dc}
QPushButton#secondary:disabled{background:#e9efec;color:#92a59d}
QPushButton#stop{background:#a75952} QPushButton#stop:disabled{background:#e4dad6;color:#a58f87}
QLineEdit,QPlainTextEdit,QTextBrowser,QComboBox,QSpinBox,QDoubleSpinBox{background:#f9fcfa;color:#234d43;border:1px solid #d0e1d8;border-radius:8px;padding:7px;selection-background-color:#b8dfce}
QTextBrowser#conversation{background:#f8fcfa;border:0;padding:12px}
QTableWidget{background:#fbfdfc;border:0;gridline-color:#e2ece7;alternate-background-color:#f0f7f3;color:#234d43}
QHeaderView::section{background:#e8f1ec;padding:11px;border:0;color:#52756a}
QTableWidget::item{padding:9px} QTableWidget::item:selected{background:#d6ecdf;color:#214a3d}
QScrollArea{background:transparent;border:0}
QScrollBar:vertical{width:9px;background:#e7efeb;margin:0;border-radius:4px}
QScrollBar::handle:vertical{background:#a8c8bc;min-height:32px;border-radius:4px}
QScrollBar::handle:vertical:hover{background:#76ab98}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent}
QSpinBox,QDoubleSpinBox{padding-right:24px}
QSpinBox::up-button,QDoubleSpinBox::up-button{subcontrol-origin:border;subcontrol-position:top right;width:20px;border:0;border-left:1px solid #d0e1d8}
QSpinBox::down-button,QDoubleSpinBox::down-button{subcontrol-origin:border;subcontrol-position:bottom right;width:20px;border:0;border-left:1px solid #d0e1d8}
QCheckBox{color:#3e675c;spacing:8px} QDialog{background:#f1f7f3}
'''
STYLE += f'''
QSpinBox::up-arrow,QDoubleSpinBox::up-arrow{{image:url("{ASSETS.as_posix()}/chevron-up.svg");width:8px;height:5px}}
QSpinBox::down-arrow,QDoubleSpinBox::down-arrow{{image:url("{ASSETS.as_posix()}/chevron-down.svg");width:8px;height:5px}}
'''

def card(title):
    frame=QFrame(objectName='card');box=QVBoxLayout(frame);box.setContentsMargins(20,18,20,18);box.setSpacing(12)
    box.addWidget(QLabel(title,objectName='section'));return frame,box

class Worker(QObject):
    done=Signal(object);failed=Signal(str)
    def start(self,function):
        def run():
            try:result=function()
            except Exception as exc:
                try:self.failed.emit(str(exc)[:700])
                except RuntimeError:pass
            else:
                try:self.done.emit(result)
                except RuntimeError:pass
        threading.Thread(target=run,name='MCConversation',daemon=True).start()

class ModelDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('对话模型');self.resize(570,430);settings=load_settings()
        outer=QVBoxLayout(self);form=QFormLayout();outer.addLayout(form)
        self.enabled=QCheckBox('启用外部模型');self.enabled.setChecked(settings['enabled']);form.addRow(self.enabled)
        self.base=QLineEdit(settings['base_url']);form.addRow('Base URL',self.base)
        self.model=QLineEdit(settings['model']);self.model.setPlaceholderText('填写服务商提供的模型 ID');form.addRow('模型',self.model)
        self.protocol=QComboBox();self.protocol.addItem('OpenAI Responses','responses');self.protocol.addItem('兼容 Chat Completions','chat');self.protocol.setCurrentIndex(max(0,self.protocol.findData(settings['protocol'])));form.addRow('协议',self.protocol)
        self.key=QLineEdit();self.key.setEchoMode(QLineEdit.Password);self.key.setPlaceholderText('已有加密密钥，留空保留' if settings['key_saved'] else '只在本机输入');form.addRow('API Key',self.key)
        self.remember=QCheckBox('用 Windows 本机加密保存');self.remember.setChecked(True);form.addRow(self.remember)
        self.auto=QCheckBox('发送指令后自动执行常规任务；材料消耗任务仍先核对');self.auto.setChecked(settings['auto_execute']);form.addRow(self.auto)
        note=QLabel('仅发送最近几轮对话、任务目录与已核实进度摘要。不发送游戏截图、UID、账号凭据或运行日志。未配置时使用本地指令模式。',objectName='muted');note.setWordWrap(True);outer.addWidget(note)
        self.error=QLabel();self.error.setWordWrap(True);outer.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);outer.addWidget(buttons)
    def save(self):
        try:save_settings({'enabled':self.enabled.isChecked(),'base_url':self.base.text(),'model':self.model.text(),'protocol':self.protocol.currentData(),'auto_execute':self.auto.isChecked()},key=self.key.text() or None,remember=self.remember.isChecked())
        except Exception as exc:self.error.setText(str(exc));return
        self.parent().session_key=self.key.text() or None;self.accept()

class Panel(LegacyPanel):
    def __init__(self):
        self.queue=deque();self.queue_autorun=False;self.history=RunHistory();self.chat_messages=[];self.session_key=None
        self.pending_plan=None;self.chat_busy=False;self.chat_generation=0;self.workers=[];self.last_refresh=0;self.last_signature=None;self.last_metrics={}
        super().__init__();tasks_page=self.takeCentralWidget();self.setWindowTitle('鸣潮手动助手 · 清宵');self.setWindowIcon(QIcon(str(asset_path('qingxiao.ico','app.ico'))));self.resize(1440,960);self.setMinimumSize(1120,760)
        for redundant in tasks_page.findChildren(QLabel):
            if redundant.objectName() in ('heading','badge'):redundant.hide()
        shell=QWidget(objectName='surface');self.setCentralWidget(shell);row=QHBoxLayout(shell);row.setContentsMargins(16,16,16,16);row.setSpacing(20)
        rail=QFrame(objectName='rail');rail.setFixedWidth(205);nav_layout=QVBoxLayout(rail);nav_layout.setContentsMargins(15,24,15,20)
        portrait=QLabel();portrait.setPixmap(QPixmap(str(asset_path('qingxiao-icon.png','app-icon.png'))).scaled(68,68,Qt.KeepAspectRatio,Qt.SmoothTransformation));nav_layout.addWidget(portrait)
        nav_layout.addWidget(QLabel('清 宵',objectName='heading'));nav_layout.addWidget(QLabel('鸣潮 · 个人助手',objectName='muted'));nav_layout.addSpacing(25)
        self.pages=QStackedWidget();self.nav=[]
        for i,label in enumerate(('总览','自动任务','游玩与声骸','对话助手','运行记录','实用工具','偏好设置','多账号','功能对照')):
            button=QPushButton(label,objectName='nav');button.setCheckable(True);button.clicked.connect(lambda _=False,n=i:self.switch_page(n));nav_layout.addWidget(button);self.nav.append(button)
        nav_layout.addStretch();nav_layout.addWidget(QLabel('纯手动 · 无定时',objectName='badge'));nav_layout.addWidget(QLabel('个人同人界面 · 非官方产品',objectName='muted'));row.addWidget(rail)
        main=QVBoxLayout();row.addLayout(main,1);top=QHBoxLayout();self.page_title=QLabel('总览',objectName='heading');top.addWidget(self.page_title);top.addStretch()
        self.model_badge=QLabel('本地指令模式',objectName='badge');top.addWidget(self.model_badge)
        self.window_mode=QComboBox()
        for label,value in (('后台运行','background'),('隐藏运行（实验）','hidden'),('前台运行','foreground')):self.window_mode.addItem(label,value)
        self.window_mode.setCurrentIndex(max(0,self.window_mode.findData(self.prefs.get('background','hidden'))));top.addWidget(self.window_mode)
        self.show_game_button=QPushButton('显示游戏',objectName='secondary');self.show_game_button.setEnabled(False);self.show_game_button.clicked.connect(lambda:self.game_window_command('show'));top.addWidget(self.show_game_button)
        self.top_stop=QPushButton('停止任务',objectName='stop');self.top_stop.clicked.connect(self.stop_job);self.top_stop.setEnabled(False);top.addWidget(self.top_stop);main.addLayout(top);main.addWidget(self.pages,1)
        self.pages.addWidget(self.wrap(self.build_home()));self.pages.addWidget(self.wrap(tasks_page));self.pages.addWidget(self.wrap(self.build_extensions()));self.pages.addWidget(self.build_chat());self.pages.addWidget(self.build_records());self.pages.addWidget(self.wrap(self.build_tools()));self.pages.addWidget(self.wrap(self.build_preferences()))
        self.accounts_page=AccountsPage(RUNS/'accounts.json',self.start_job,self)
        self.pages.addWidget(self.accounts_page);self.buttons.append(self.accounts_page.start_button)
        self.pages.addWidget(self.build_comparison());self.add_task_parameters(tasks_page)
        self.switch_page(0);self.update_model_badge();self.refresh_dashboard(True)
        for item in read_json(RUNS/'manual-queue.json',{}).get('steps',[]):
            if isinstance(item,dict) and item.get('action') in CATALOG:self.queue.append(item)
        self.persist_queue()
        self.tray=QSystemTrayIcon(self.windowIcon(),self);self.tray.setToolTip('鸣潮手动助手 · 清宵');menu=QMenu()
        menu.addAction('打开助手').triggered.connect(self.show_panel);menu.addAction('停止任务与队列').triggered.connect(self.stop_job);menu.addAction('收起到托盘').triggered.connect(self.hide);menu.addAction('退出助手').triggered.connect(self.close)
        self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.show_panel() if reason==QSystemTrayIcon.DoubleClick else None);self.tray.show()
        self.shortcut=QShortcut(QKeySequence('Ctrl+Return'),self);self.shortcut.activated.connect(self.send_chat)

    def show_panel(self):self.showNormal();self.raise_();self.activateWindow()
    def switch_page(self,index):
        self.pages.setCurrentIndex(index);self.page_title.setText(self.nav[index].text())
        for n,button in enumerate(self.nav):button.setChecked(n==index)
        if index==4 and hasattr(self,'table'):self.refresh_dashboard(True)
    def wrap(self,widget):
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget);return scroll
    def build_home(self):
        page=QWidget(objectName='surface');box=QVBoxLayout(page);box.setContentsMargins(0,0,0,10);box.setSpacing(17)
        hero=Hero(asset_path('qingxiao-wallpaper.png','app-background.png'));inside=QVBoxLayout(hero);inside.setContentsMargins(30,30,30,25)
        inside.addWidget(QLabel('云静，事亦有序。',objectName='heroTitle'));inside.addWidget(QLabel('选一项任务，或直接告诉我你想做什么。\n游戏进度与每次结果，都留在这里。'));inside.addStretch();buttons=QHBoxLayout()
        for label,callback in (('日常 ＋ 乐园周常',lambda:self.enqueue([{'action':'daily'},{'action':'weekly'}])),('只检查进度',lambda:self.start_job('probe')),('和我说一句',lambda:self.switch_page(3))):
            button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
        buttons.addStretch();inside.addLayout(buttons);box.addWidget(hero)
        line=QHBoxLayout();frame,metrics=card('最近有效读数');rings=QHBoxLayout();self.activity_ring=ProgressRing('活跃度 / 100',100);self.weekly_ring=ProgressRing('周游历 / 6000',6000);rings.addWidget(self.activity_ring);rings.addWidget(self.weekly_ring);metrics.addLayout(rings);self.metric_note=QLabel(objectName='muted');metrics.addWidget(self.metric_note);line.addWidget(frame,1)
        frame,state=card('当前任务');self.home_status=QLabel('准备就绪',objectName='section');self.home_details=QLabel('打开助手不会开始游戏任务。');self.home_details.setWordWrap(True);state.addWidget(self.home_status);state.addWidget(self.home_details);state.addStretch();self.elapsed_label=QLabel('尚未开始',objectName='muted');state.addWidget(self.elapsed_label)
        self.home_report=QPushButton('查看本次结果',objectName='secondary');self.home_report.setEnabled(False);self.home_report.clicked.connect(self.open_report);state.addWidget(self.home_report);line.addWidget(frame,1);box.addLayout(line)
        frame,queue_box=card('任务队列');queue_line=QHBoxLayout();self.queue_label=QLabel('等待队列为空');self.queue_label.setWordWrap(True);queue_line.addWidget(self.queue_label,1)
        self.resume_button=QPushButton('继续队列',objectName='secondary');self.resume_button.clicked.connect(self.resume_queue);queue_line.addWidget(self.resume_button);self.clear_queue_button=QPushButton('清空',objectName='secondary');self.clear_queue_button.clicked.connect(self.clear_queue);queue_line.addWidget(self.clear_queue_button);queue_box.addLayout(queue_line);box.addWidget(frame)
        frame,chart_box=card('最近任务 · 真实耗时');self.chart=RunChart();chart_box.addWidget(self.chart);chart_box.addWidget(QLabel('玉色：完成　金色：主动停止　浅红：中断或待核对。',objectName='muted'));box.addWidget(frame);return page
    def build_extensions(self):
        page=QWidget(objectName='surface');grid=QGridLayout(page);grid.setContentsMargins(0,0,0,0);grid.setSpacing(15)
        self.extra_controls={}
        self.assist_status=QLabel('准备就绪 · 游玩辅助始终前台运行',objectName='badge');self.assist_status.setWordWrap(True)
        grid.addWidget(self.assist_status,0,0,1,2)
        columns=[QVBoxLayout(),QVBoxLayout()]
        for column,layout in enumerate(columns):
            layout.setSpacing(15);grid.addLayout(layout,1,column)
        for n,action in enumerate(('pickup','dialog','combat','enhance','merge','quest','fasttravel','reconstruct','elimination')):
            job=CATALOG[action];frame,box=card(job.label);box.setAlignment(Qt.AlignTop);note=QLabel(job.description,objectName='muted');note.setWordWrap(True);box.addWidget(note)
            timed=job.continuous or action=='elimination'
            limit=QSpinBox();limit.setRange(1,180 if timed else 20);limit.setValue(10 if action=='elimination' else 30 if timed else 1);limit.setSuffix(' 分钟上限' if timed else ' 个候选上限' if action in ('enhance','reconstruct') else ' 批上限，每批100个');self.extra_controls[action]=limit;box.addWidget(limit)
            if action in ('pickup','combat','quest'):
                setup=QPushButton('辅助开关与拾取名单',objectName='secondary');setup.clicked.connect(self.edit_helper_settings);box.addWidget(setup)
            if action=='reconstruct':
                self.reconstruct_target=QComboBox();self.reconstruct_target.addItems(MAIN_STATS);self.reconstruct_target.setCurrentText(self.prefs.get('main_stat','攻击'));box.addWidget(self.reconstruct_target)
                inspect=QPushButton('检查候选页面（不消耗）',objectName='secondary');inspect.clicked.connect(lambda:self.start_job('reconstruct',{'check_only':True}));box.addWidget(inspect)
                note=QLabel('仅简中；先筛选0级候选，并排除已是目标主属性的声骸。新接入，材料实跑待验收。',objectName='muted');note.setWordWrap(True);box.addWidget(note)
            if action=='elimination':
                inspect=QPushButton('检查活动页面（不挑战）',objectName='secondary');inspect.clicked.connect(lambda:self.start_job('elimination',{'check_only':True}));box.addWidget(inspect)
                note=QLabel('先在游戏打开无音消除活动。采用官方3.7.13终局流程；新接入，实跑待验收。',objectName='muted');note.setWordWrap(True);box.addWidget(note)
            if action=='enhance':
                inspect=QPushButton('检查当前声骸页（不消耗）',objectName='secondary');inspect.clicked.connect(lambda:self.start_job('enhance',{'check_only':True}));box.addWidget(inspect)
                rules=QPushButton('修改词条规则',objectName='secondary');rules.clicked.connect(self.edit_rules);box.addWidget(rules);note=QLabel('先在游戏背包筛选声骸，按等级从0排序；开启阶段放入与同步调谐。',objectName='muted');note.setWordWrap(True);box.addWidget(note)
            if action=='merge':
                inspect=QPushButton('检查合成筛选（不消耗）',objectName='secondary');inspect.clicked.connect(lambda:self.start_job('merge',{'check_only':True}));box.addWidget(inspect)
                box.addWidget(QLabel('自动核对弃置筛选；预检只选中材料，不提交融合。',objectName='muted'))
            button=QPushButton('核对并开始' if job.spends_materials else '开始活动' if action=='elimination' else '开始辅助');button.setObjectName('start_'+action);button.clicked.connect(lambda _=False,key=action:self.start_job(key));box.addWidget(button);self.buttons.append(button);columns[n%2].addWidget(frame)
        for layout in columns:layout.addStretch()
        grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);grid.setRowStretch(1,1);return page

    def add_task_parameters(self,tasks_page):
        for frame in tasks_page.findChild(TaskScroll).cards:
            frame.layout().setSpacing(4);frame.layout().setContentsMargins(15,9,15,9)
        daily=tasks_page.findChild(QPushButton,'start_daily').parentWidget()
        button=QPushButton('选择日常刷取目标',objectName='secondary');button.clicked.connect(self.edit_daily_settings);daily.layout().insertWidget(daily.layout().indexOf(tasks_page.findChild(QPushButton,'start_daily')),button)
        for action,cost in (('tacet',60),('forgery',40),('simulation',40),('nightmare',1)):
            frame=tasks_page.findChild(QPushButton,'start_'+action).parentWidget();line=QHBoxLayout()
            line.addWidget(QLabel('目标上限' if action=='nightmare' else '体力上限',objectName='muted'))
            spin=QSpinBox();spin.setRange(0,100 if action=='nightmare' else 240);spin.setSingleStep(cost)
            spin.setSpecialValueText('全部目标' if action=='nightmare' else '全部自然体力')
            key=action+'_limit';spin.setValue(int(self.prefs.get(key,0)));self.controls[key]=spin;line.addWidget(spin);frame.layout().insertLayout(frame.layout().indexOf(tasks_page.findChild(QPushButton,'start_'+action)),line)

    def edit_daily_settings(self):
        dialog=QDialog(self);dialog.setWindowTitle('日常刷取目标');form=QFormLayout(dialog)
        saved=self.prefs.get('daily_options',{});farm=QComboBox()
        for key,label in (('tacet','无音区'),('forgery','凝素领域'),('simulation','模拟训练')):farm.addItem(label,key)
        farm.setCurrentIndex(max(0,farm.findData(saved.get('daily_farm','tacet'))));form.addRow('刷取类型',farm)
        index=QSpinBox();index.setRange(1,21);index.setValue(saved.get('index',1));form.addRow('指南序号',index)
        material=QComboBox()
        for key,label in (('Shell Credit','贝币'),('Resonator EXP','共鸣者经验'),('Weapon EXP','武器经验')):material.addItem(label,key)
        material.setCurrentIndex(max(0,material.findData(saved.get('material','Shell Credit'))));form.addRow('训练材料',material)
        def update():
            index.setMaximum(21 if farm.currentData()=='tacet' else 20 if farm.currentData()=='forgery' else 1)
            index.setEnabled(farm.currentData()!='simulation');material.setEnabled(farm.currentData()=='simulation')
        farm.currentIndexChanged.connect(update);update()
        note=QLabel('已满活跃时跳过；只用自然体力，不自动补充。');form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Save).setText('保存');buttons.button(QDialogButtonBox.Cancel).setText('取消');buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec():
            self.prefs['daily_options']=dict(daily_farm=farm.currentData(),index=index.value(),material=material.currentData())
            atomic_json(RUNS/'manual-settings.json',self.settings())

    def edit_helper_settings(self):
        values=normalize_helper_options(self.prefs.get('helper_options'));dialog=QDialog(self);dialog.setWindowTitle('辅助设置');dialog.resize(620,600);form=QFormLayout(dialog);checks={}
        for key,label in (('auto_target','自动锁定敌人'),('use_liberation','使用共鸣解放'),('switch_healer','战斗前后切治疗'),
            ('quest_dialog','剧情组合：跳过对话'),('quest_combat','剧情组合：自动战斗'),('quest_pickup','剧情组合：拾取'),('quest_fasttravel','剧情组合：点击地图快捷传送')):
            box=QCheckBox(label);box.setChecked(values[key]);checks[key]=box;form.addRow(box)
        lists={}
        for key,label in (('pickup_whitelist','交互白名单（每行一项）'),('pickup_blacklist','拾取黑名单（每行一项）')):
            box=QPlainTextEdit('\n'.join(values[key]));box.setMaximumHeight(70);lists[key]=box;form.addRow(label,box)
        note=QLabel('这些开关用于游玩辅助。剧情组合需要手动跑图，不自动接任务、导航或解谜。');note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Save).setText('保存');buttons.button(QDialogButtonBox.Cancel).setText('取消');buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec():
            try:self.prefs['helper_options']=normalize_helper_options({**{k:v.isChecked() for k,v in checks.items()},**{k:v.toPlainText().splitlines() for k,v in lists.items()}})
            except ValueError as exc:QMessageBox.warning(self,'设置无效',str(exc));return
            atomic_json(RUNS/'manual-settings.json',self.settings())

    def build_comparison(self):
        from comparison import render_comparison
        page=QWidget(objectName='surface');box=QVBoxLayout(page);view=QTextBrowser();view.setOpenExternalLinks(True);view.setHtml(render_comparison());box.addWidget(view)
        button=QPushButton('刷新功能对照',objectName='secondary');button.clicked.connect(lambda:view.setHtml(render_comparison()));box.addWidget(button);return page
    def build_chat(self):
        page=QWidget(objectName='surface');box=QVBoxLayout(page);line=QHBoxLayout();line.addWidget(QLabel('说一句，安排好。',objectName='section'));line.addStretch();configure=QPushButton('连接模型',objectName='secondary');configure.clicked.connect(self.configure_model);line.addWidget(configure);box.addLayout(line)
        self.conversation=QTextBrowser(objectName='conversation');box.addWidget(self.conversation,1);self.add_chat('assistant','可以告诉我“检查今天进度”“刷模拟贝币”“打开自动拾取”。连接模型后，也可以自由对话、安排多步任务。')
        self.plan_label=QLabel();self.plan_label.setWordWrap(True);box.addWidget(self.plan_label);self.plan_button=QPushButton('执行这份计划');self.plan_button.clicked.connect(self.execute_plan);self.plan_button.hide();box.addWidget(self.plan_button)
        line=QHBoxLayout();self.chat_input=QPlainTextEdit();self.chat_input.setMaximumHeight(110);self.chat_input.setPlaceholderText('例如：先检查今天，再看看乐园周常。Ctrl+Enter 发送。');line.addWidget(self.chat_input,1);self.send_button=QPushButton('发送');self.send_button.clicked.connect(self.send_chat);line.addWidget(self.send_button);box.addLayout(line);return page
    def build_records(self):
        page=QWidget(objectName='surface');box=QVBoxLayout(page);self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['时间','任务','结果','活跃 / 周游历','核对体力']);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.setAlternatingRowColors(True);self.table.verticalHeader().hide();self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.table.itemSelectionChanged.connect(self.select_record);box.addWidget(self.table,1)
        self.record_note=QLabel('选择记录查看截图与报告。',objectName='muted');self.record_note.setWordWrap(True);box.addWidget(self.record_note);self.preview=QLabel();self.preview.setFixedSize(340,190);box.addWidget(self.preview)
        actions=QHBoxLayout();self.open_record_button=QPushButton('打开选中报告');self.open_record_button.setEnabled(False);self.open_record_button.clicked.connect(self.open_selected);actions.addWidget(self.open_record_button)
        self.retry_button=QPushButton('按原参数重试',objectName='secondary');self.retry_button.setEnabled(False);self.retry_button.clicked.connect(self.retry_selected);actions.addWidget(self.retry_button);box.addLayout(actions);return page
    def build_tools(self):
        page=QWidget(objectName='surface');box=QVBoxLayout(page)
        for key,(title,url,description) in TOOL_LINKS.items():
            frame,layout=card(title);note=QLabel(description,objectName='muted');note.setWordWrap(True);layout.addWidget(note);button=QPushButton('打开本机工具 / 项目发布入口' if key=='community' else '打开工具');button.clicked.connect(lambda _=False,k=key:self.open_tool(k));layout.addWidget(button);box.addWidget(frame)
        frame,layout=card('本机账号工具');self.community_path=QLineEdit(self.prefs.get('community_exe',''));self.community_path.setPlaceholderText('选择已安装的 WutheringWavesTool EXE');layout.addWidget(self.community_path);choose=QPushButton('选择 EXE',objectName='secondary');choose.clicked.connect(self.choose_tool);layout.addWidget(choose);layout.addWidget(QLabel('账号登录在工具内完成，本助手不读取它的凭据。',objectName='muted'));box.addWidget(frame);box.addStretch();return page
    def build_preferences(self):
        page=QWidget(objectName='surface');box=QVBoxLayout(page);frame,layout=card('对话模型');self.model_description=QLabel();self.model_description.setWordWrap(True);layout.addWidget(self.model_description);button=QPushButton('配置端点、模型与密钥');button.clicked.connect(self.configure_model);layout.addWidget(button);box.addWidget(frame)
        frame,layout=card('本机游戏路径');self.game_path_label=QLabel();self.game_path_label.setWordWrap(True)
        try:self.game_path_label.setText(str(game_executable() or '尚未配置；选择官方游戏启动器 EXE。'))
        except ValueError as exc:self.game_path_label.setText(str(exc))
        layout.addWidget(self.game_path_label);button=QPushButton('选择游戏启动器 EXE',objectName='secondary');button.clicked.connect(self.choose_game_executable);layout.addWidget(button);box.addWidget(frame)
        frame,layout=card('后台与性能');note=QLabel('后台使用窗口消息与 WGC 捕获。隐藏检测与显示恢复已实测；若任务栏唤回无效，请点助手上方“显示游戏”。界面无循环粒子、无常驻浏览器；历史每5秒更新，游戏识别只在任务启动后加载。',objectName='muted');note.setWordWrap(True);layout.addWidget(note);self.performance=QLabel(objectName='muted');layout.addWidget(self.performance);button=QPushButton('查看资源占用',objectName='secondary');button.clicked.connect(self.sample_resources);layout.addWidget(button);box.addWidget(frame)
        frame,layout=card('使用与数据');note=QLabel('纯手动，无定时或开机触发。刷本不补充体力。任务记录与配置保存在本机。模型密钥由 Windows 当前用户加密；程序升级时请保留整个项目目录。',objectName='muted');note.setWordWrap(True);layout.addWidget(note);button=QPushButton('使用说明',objectName='secondary');button.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'manual_launcher/使用说明.html'))));layout.addWidget(button);box.addWidget(frame);box.addStretch();return page

    def choose_game_executable(self):
        path,_=QFileDialog.getOpenFileName(self,'选择官方游戏启动器 EXE','','Windows EXE (*.exe)')
        if not path:return
        try:save_game_executable(path);self.game_path_label.setText(str(game_executable()))
        except ValueError as exc:QMessageBox.warning(self,'游戏路径无效',str(exc))

    def settings(self):
        prefs=super().settings()
        if hasattr(self,'window_mode'):prefs['background']=self.window_mode.currentData()
        if hasattr(self,'community_path'):prefs['community_exe']=self.community_path.text()
        prefs['enhance_rules']=self.prefs.get('enhance_rules')
        prefs['daily_options']=self.prefs.get('daily_options',{})
        prefs['helper_options']=self.prefs.get('helper_options',normalize_helper_options())
        if hasattr(self,'reconstruct_target'):prefs['main_stat']=self.reconstruct_target.currentText()
        return prefs
    def start_job(self,action,options=None,confirmed=False):
        if action not in CATALOG:return
        prefs=self.settings()
        try:
            params=self.job_parameters(action,options);params['confirmed_materials']=confirmed
            request=make_request(action,**params)
        except Exception as exc:QMessageBox.warning(self,'参数需要调整',str(exc));return
        params['enhance_rules']=request['EnhanceRules']
        if 'HelperOptions' in request:params['helper_options']=request['HelperOptions']
        if self.active_id:
            if len(self.queue)>=8:QMessageBox.information(self,'队列已满','最多等待8项任务。');return
            # Materials are confirmed when this queued task actually starts,
            # since another task may change the bag/filter before then.
            params['confirmed_materials']=False
            self.queue.append({'action':action,'options':params,'confirmed':False});self.queue_autorun=True;self.persist_queue();return
        if CATALOG[action].spends_materials and not request.get('CheckOnly'):
            if not self.confirm_materials(action,params):
                self.queue_autorun=False
                return
            request['ConfirmedMaterials']=True
        atomic_json(RUNS/'manual-settings.json',prefs);atomic_json(RUNS/'pending-manual.json',request)
        self.active_id=request['RequestId'];self.active_task=JOBS[action][2];self.active_since=time.monotonic();self.stopping=False;self.run_directory=self.report_path=None;self.log.clear();self.last_log='';self.tail=IncrementalTail()
        self.status.setText('正在启动：'+JOBS[action][0]);self.details.setText('连接现有游戏；未启动时自动启动官方版。');self.report_button.setEnabled(False);self.set_busy(True)
        self.assist_status.setText(self.status.text()+' · '+self.details.text())
        def started(result):
            if not result.get('Ok'):
                self.cancel_pending();self.status.setText('未能开始');self.details.setText(result.get('Error','请查看记录'));self.active_id=self.active_task=None;self.queue_autorun=False;self.set_busy(False)
        self.bridge('start',started)
    def confirm_materials(self,action,params):
        if action=='enhance':
            message=('按背包中已筛选的0级声骸培养，消耗经验、贝币与调谐器。\n'
                     '合格后锁定，不合格标记弃置；识别不确定则停止。\n'
                     f'本次最多选择{params["count"]}个候选。\n\n'+enhancement_summary(params['enhance_rules']))
        elif action=='reconstruct':
            message=(f'对已筛选的0级声骸使用游戏内数据重构，消耗对应材料。\n目标主属性：{params["main_stat"]}。'
                     f'\n本次最多{params["count"]}个候选。请先排除已经是目标主属性的声骸。\n识别不确定则停止；新功能尚未完成材料实跑验收。')
        else:
            message=(f'只合成已标记弃置的声骸，无法恢复原声骸。\n本次上限：{params["count"]}批，'
                     f'每批100个，最多消耗{params["count"]*100}个。\n不会自动标记弃置；不足满批时停止。')
        dialog=QMessageBox(QMessageBox.Question,'核对并开始',message,parent=self)
        start=dialog.addButton('确认并开始',QMessageBox.AcceptRole)
        cancel=dialog.addButton('取消',QMessageBox.RejectRole)
        dialog.setDefaultButton(cancel);dialog.setEscapeButton(cancel);dialog.exec()
        return dialog.clickedButton() is start
    def job_parameters(self,action,options=None):
        prefs=self.settings();index=prefs.get(action+'_index',1)
        if action=='echo':index=prefs['echo_index']
        params=dict(index=index,material=prefs['material'],count=prefs['count'],scope=prefs['scope'],kind=prefs['kind'],background=prefs.get('background','background'),enhance_rules=prefs.get('enhance_rules'))
        if action in self.extra_controls:
            params['duration' if CATALOG[action].continuous or action=='elimination' else 'count']=self.extra_controls[action].value()
        if action=='daily':params.update(prefs.get('daily_options',{}))
        if action in ('tacet','forgery','simulation') and prefs.get(action+'_limit'):params['stamina_limit']=prefs[action+'_limit']
        if action=='nightmare' and prefs.get('nightmare_limit'):params['target_limit']=prefs['nightmare_limit']
        if action=='reconstruct':params['main_stat']=self.reconstruct_target.currentText()
        if action in ('pickup','dialog','combat','fasttravel','quest'):params['helper_options']=prefs.get('helper_options')
        params.update(options or {})
        if action=='multiaccount' and 'accounts' not in params:params['accounts']=load_accounts(RUNS/'accounts.json')
        if CATALOG[action].continuous:params['background']='foreground'
        return params
    def set_busy(self,busy):
        for button in self.buttons:button.setEnabled(True)
        self.stop_button.setEnabled(busy and not self.stopping)
        if hasattr(self,'top_stop'):self.top_stop.setEnabled((busy or bool(self.queue)) and not self.stopping)
        self.update_queue_controls()
    def enqueue(self,steps):
        if len(self.queue)+len(steps)>8:QMessageBox.information(self,'队列已满','最多安排8项等待任务。');return
        for step in steps:self.queue.append({'action':step['action'],'options':self.job_parameters(step['action'],step.get('options',{})),'confirmed':False})
        self.queue_autorun=True;self.persist_queue();self.run_next()
    def persist_queue(self):
        atomic_json(RUNS/'manual-queue.json',{'steps':list(self.queue),'automatic_on_open':False})
        if hasattr(self,'queue_label'):self.queue_label.setText('等待：'+' → '.join(CATALOG[s['action']].label for s in self.queue) if self.queue else '等待队列为空')
        self.update_queue_controls()
    def update_queue_controls(self):
        if hasattr(self,'resume_button'):
            self.resume_button.setEnabled(bool(self.queue) and not self.active_id)
            self.clear_queue_button.setEnabled(bool(self.queue))
    def run_next(self):
        if self.active_id or not self.queue or not self.queue_autorun:return
        item=self.queue.popleft();self.persist_queue();self.start_job(item['action'],item.get('options'),item.get('confirmed',False))
    def resume_queue(self):self.queue_autorun=True;self.run_next()
    def clear_queue(self):self.queue.clear();self.queue_autorun=False;self.persist_queue()
    def stop_job(self):
        self.clear_queue();self.chat_generation+=1
        self.pending_plan=None;self.plan_button.hide();self.plan_label.clear()
        if self.active_id:super().stop_job()
        else:self.set_busy(False)
    def poll(self):
        before=self.active_id;super().poll()
        if self.active_id and self.report_path:
            live=read_json(self.report_path,{})
            if live.get('mode')=='multiaccount':
                rows=live.get('account_results',[])
                self.details.setText(f'当前账号：{live.get("current_account") or "准备中"} · 已完成 {sum(r.get("status")=="completed" for r in rows)}/{len(rows)}；失败即停')
        if hasattr(self,'assist_status'):
            self.assist_status.setText(self.status.text()+' · '+self.details.text())
        if hasattr(self,'home_status'):
            self.home_status.setText(self.status.text());self.home_details.setText(self.details.text())
            self.home_report.setEnabled(self.report_button.isEnabled())
            if self.active_id:
                elapsed=int(time.monotonic()-self.active_since);self.elapsed_label.setText(f'已运行 {elapsed//60:02d}:{elapsed%60:02d} · 可随时停止')
            elif before:
                self.elapsed_label.setText('本次已结束，结果已保存');state=read_json(RUNS/'manual-state.json',{})
                if state.get('RequestId')==before:self.announce_result(state)
                if state.get('State')=='completed' and self.queue_autorun:QTimer.singleShot(500,self.run_next)
                else:self.queue_autorun=False
                self.refresh_dashboard(True)
            self.top_stop.setEnabled((bool(self.active_id) or bool(self.queue)) and not self.stopping)
            self.show_game_button.setEnabled(bool(self.active_id and self.run_directory))
        if time.monotonic()-self.last_refresh>5 and hasattr(self,'chart'):self.refresh_dashboard()
    def announce_result(self,state):
        report=read_json(Path(state['Report']),{}) if state.get('Report') else {}
        action=state.get('Action');label=CATALOG[action].label if action in CATALOG else '本次任务'
        result=STATES.get(report.get('status'),state.get('State','已结束'))
        details=[]
        if report.get('selected_echo_level') is not None:
            details.append(f'当前声骸等级 +{report["selected_echo_level"]}；仅检查，未消耗材料')
        if report.get('check_only') and report.get('discard_filter_verified'):
            details.append(f'弃置筛选已核对，已选{report["merge_selected_materials"]}/100个；未提交融合')
        if report.get('activity_points') is not None:details.append(f'活跃度 {report["activity_points"]}/100')
        if report.get('account_results') is not None:
            rows=report['account_results'];details.append(f'账号完成 {sum(r.get("status")=="completed" for r in rows)}/{len(rows)}')
        if report.get('weekly_progress_points') is not None:details.append(f'周游历 {report["weekly_progress_points"]}/6000')
        if report.get('echo_count') is not None:details.append(f'声骸拾取读数 {report["echo_count"]}')
        if report.get('reconstruct_completed') is not None:details.append(f'重构完成 {report["reconstruct_completed"]} 个；目标 {report.get("reconstruct_target","")}')
        if report.get('event_stages') is not None:details.append(f'活动本轮完成 {report["event_stages"]} 关'+('；时限已到，进度保留' if report.get('event_end_reason')=='time_limit' else ''))
        if report.get('recovered_log_errors'):details.append('战斗结束时出现过已恢复提示，原日志已保留')
        if report.get('detection_only'):details.append('本次只检测，未消耗体力')
        if report.get('enhance_selected') is not None:
            details.append(f'候选 {report["enhance_selected"]} 个，合格锁定 {report.get("enhance_success",0)} 个，不合格弃置 {report.get("enhance_rejected",0)} 个')
        if report.get('merge_batches') is not None:details.append(f'完成合成 {report["merge_batches"]} 批')
        for key,label in (('pickup_interactions','拾取交互'),('combat_sessions','战斗处理'),('dialog_actions','对话操作')):
            if report.get(key) is not None:details.append(f'{label} {report[key]} 次')
        if report.get('stop_reason'):details.append(report['stop_reason'])
        if action in ('enhance','merge') and report.get('material_consumption_independently_verified') is False:
            details.append('材料消耗未独立核验')
        if report.get('errors'):details.append('存在异常，请在运行记录中核对')
        self.add_chat('assistant',f'{label}：{result}。'+('；'.join(details)+'。' if details else '')+'详细报告已保存到运行记录。')
    def refresh_dashboard(self,force=False):
        self.last_refresh=time.monotonic();records=self.history.refresh(force);summary=self.history.summary();self.last_metrics=summary
        self.activity_ring.setValue(summary['activity']);self.weekly_ring.setValue(summary['weekly']);self.chart.setRecords(records)
        stamp=(summary.get('activity_observed_at') or '本日尚未检查')[:19].replace('T',' ')
        weekly_stamp=(summary.get('weekly_observed_at') or '本周尚未检查')[:19].replace('T',' ')
        self.metric_note.setText(f'已记录 {summary["runs"]} 次结束任务\n日常读取：{stamp}\n周常读取：{weekly_stamp}')
        if not hasattr(self,'table'):return
        signature=[(r.get('_run'),r.get('status'),r.get('updated_at')) for r in records]
        if signature==self.last_signature:return
        selected=self.selected_record();selected_path=selected.get('_path') if selected else None
        scroll_position=self.table.verticalScrollBar().value()
        self.table.blockSignals(True);self.table.setUpdatesEnabled(False)
        self.last_signature=signature;self.record_rows=list(records);self.table.setRowCount(len(records));labels={j.mode:j.label for j in CATALOG.values()};labels.update(farm='体力刷取',assist='游玩辅助')
        for row,r in enumerate(records):
            progress=f'{r["activity_points"]}/100' if r.get('activity_points') is not None else f'{r["weekly_progress_points"]}/6000' if r.get('weekly_progress_points') is not None else '—'
            spent=str(r['_verified_stamina_spent'])+'（回查）' if r.get('_verified_stamina_spent') is not None else str(r['stamina_spent']) if r.get('status') in ('FARM_PASSED','FARM_READBACK_PASSED') and r.get('stamina_spent') is not None else '—'
            values=[r.get('started_at','')[:19].replace('T',' '),labels.get(r.get('mode'),r.get('mode','')),STATES.get(r.get('status'),r.get('status','')),progress,spent]
            for column,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(value);self.table.setItem(row,column,item)
        selected_row=next((n for n,r in enumerate(records) if r.get('_path')==selected_path),None) if selected_path else None
        if selected_row is None:self.table.clearSelection();self.table.setCurrentCell(-1,-1)
        else:self.table.selectRow(selected_row)
        self.table.verticalScrollBar().setValue(scroll_position)
        self.table.setUpdatesEnabled(True);self.table.blockSignals(False);self.select_record()
    def selected_record(self):
        row=self.table.currentRow();return self.record_rows[row] if 0<=row<len(getattr(self,'record_rows',[])) else None
    def select_record(self):
        record=self.selected_record()
        self.open_record_button.setEnabled(bool(record and Path(record['_path']).with_suffix('.html').is_file()))
        if not record:
            self.retry_button.setEnabled(False);self.preview.clear();self.record_note.setText('选择记录查看截图与报告。');return
        self.retry_button.setEnabled(bool(self.original_request(record)))
        self.record_note.setText(record.get('_run','')+('\n'+record['_verification_note'] if record.get('_verification_note') else '')+('\n'+str(record['errors'][-1])[:400] if record.get('errors') else ''));images=self.history.screenshots(record)
        self.preview.setPixmap(QPixmap(str(images[0])).scaled(340,190,Qt.KeepAspectRatio,Qt.SmoothTransformation) if images else QPixmap())
    def open_selected(self):
        record=self.selected_record()
        if record:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(record['_path']).with_suffix('.html'))))
    def original_request(self,record):
        try:
            folder=Path(record['_path']).resolve().parent;folder.relative_to(RUNS.resolve())
            request=read_json(folder/'manual-request.json',{})
            if request.get('Action') not in CATALOG:return None
            options={target:request[source] for source,target in (
                ('Index','index'),('Material','material'),('Count','count'),('Scope','scope'),('Kind','kind'),
                ('Duration','duration'),('Background','background'),('EnhanceRules','enhance_rules'),('CheckOnly','check_only'),('StaminaLimit','stamina_limit'),('TargetLimit','target_limit'),('Accounts','accounts'),('MainStat','main_stat'),('DailyFarm','daily_farm'),('HelperOptions','helper_options')) if source in request}
            if request['Action']=='reconstruct' and read_json(folder/'report.json',{}).get('pending_reconstruct'):return None
            if request['Action']=='multiaccount':options['accounts']=retry_accounts(options['accounts'],read_json(folder/'report.json',{}))
            make_request(request['Action'],**options)
            return {'action':request['Action'],'options':options}
        except (KeyError,TypeError,ValueError,OSError):return None
    def retry_selected(self):
        record=self.selected_record();request=self.original_request(record) if record else None
        if not request:return
        # A previous confirmation is not permission to spend materials again.
        self.start_job(request['action'],request['options'],confirmed=False)
    def add_chat(self,role,text):
        self.chat_messages.append({'role':role,'content':text});self.chat_messages=self.chat_messages[-60:]
        fragments=[]
        for message in self.chat_messages:
            name='你' if message['role']=='user' else '清宵 · 助手';background='#e3f0e8' if message['role']=='user' else '#ffffff';body=html.escape(message['content']).replace('\n','<br>')
            fragments.append(f'<div style="background:{background};padding:16px;margin:10px"><p style="color:#588579">{name}</p><p style="line-height:1.7">{body}</p></div>')
        self.conversation.setHtml(''.join(fragments));self.conversation.verticalScrollBar().setValue(self.conversation.verticalScrollBar().maximum())
    def send_chat(self):
        if self.chat_busy:return
        text=self.chat_input.toPlainText().strip()
        if not text:return
        if len(text)>6000:self.add_chat('assistant','本次请控制在6000字以内。');return
        previous=list(self.chat_messages);self.add_chat('user',text);self.chat_input.clear();self.chat_busy=True;self.send_button.setEnabled(False);self.model_badge.setText('正在理解…');generation=self.chat_generation
        worker=Worker(self);self.workers.append(worker)
        def cleanup():
            if worker in self.workers:self.workers.remove(worker)
            worker.deleteLater()
        def done(plan):
            cleanup()
            self.chat_busy=False;self.send_button.setEnabled(True);self.update_model_badge()
            if generation!=self.chat_generation:return
            self.add_chat('assistant',plan['reply']);self.pending_plan=plan;steps=plan.get('steps',[])
            self.plan_label.setText('计划：'+' → '.join(CATALOG[s['action']].label if s['action'] in CATALOG else TOOL_LINKS[s['action']][0] if s['action'] in TOOL_LINKS else s['action'] for s in steps) if steps else '')
            material=any(CATALOG[s['action']].spends_materials for s in steps if s['action'] in CATALOG);self.plan_button.setVisible(bool(steps))
            if steps and load_settings()['auto_execute'] and not material:self.execute_plan()
        def failed(message):cleanup();self.chat_busy=False;self.send_button.setEnabled(True);self.update_model_badge();self.add_chat('assistant',message)
        worker.done.connect(done);worker.failed.connect(failed);worker.start(lambda:llm_plan(text,previous,self.last_metrics,self.session_key))
    def execute_plan(self):
        if not self.pending_plan:return
        try:plan=validate_plan(self.pending_plan)
        except ValueError as exc:self.add_chat('assistant',str(exc));return
        self.pending_plan=None;self.plan_button.hide();self.plan_label.clear();jobs=[]
        for step in plan['steps']:
            action=step['action']
            if action=='stop':self.stop_job()
            elif action=='status':self.add_chat('assistant',self.describe_status())
            elif action in TOOL_LINKS:self.open_tool(action)
            else:jobs.append(step)
        self.enqueue(jobs)
    def describe_status(self):
        summary=self.last_metrics;lines=['当前任务：'+self.status.text()+'。' if self.active_id else '当前没有运行中的助手任务。']
        lines.append('今日活跃度：'+(str(summary['activity'])+'/100' if summary.get('activity') is not None else '本日尚未核实')+'；周游历：'+(str(summary['weekly'])+'/6000' if summary.get('weekly') is not None else '本周尚未核实')+'。')
        labels={'probe':'今日检查','daily':'日常','weekly':'乐园周常','farm':'体力刷取','echo':'Boss声骸','nightmare':'梦魇／聚落','assist':'游玩辅助','enhance':'声骸培养','merge':'弃置合成'}
        for record in summary.get('recent_tasks',[])[:6]:
            text=labels.get(record.get('mode'),'任务')+'：'+STATES.get(record.get('status'),record.get('status','未知'))
            if record.get('echo_count') is not None:text+='，声骸拾取读数 '+str(record['echo_count'])
            lines.append(text+'。')
        return '\n'.join(lines)
    def configure_model(self):
        if ModelDialog(self).exec():self.update_model_badge()
    def update_model_badge(self):
        settings=load_settings();configured=settings['enabled'] and settings['model'] and (settings['key_saved'] or self.session_key)
        self.model_badge.setText('模型已配置 · '+settings['model'] if configured else '本地指令模式')
        if hasattr(self,'model_description'):self.model_description.setText('已配置模型：'+settings['model']+'，仅在发送对话时联网。' if configured else '按钮与常用本地指令可直接运行；连接模型后启用自由对话与多步规划。')
    def edit_rules(self):
        dialog=QDialog(self);dialog.setWindowTitle('声骸强化规则');form=QFormLayout(dialog);rules=normalize_enhance_rules(self.prefs.get('enhance_rules'))
        double=QCheckBox('要求双爆');double.setChecked(rules['require_double_crit']);form.addRow(double);stats=QLineEdit('、'.join(rules['valid_stats']));form.addRow('有效词条（顿号分隔）',stats)
        minimum=QSpinBox();minimum.setRange(1,5);minimum.setValue(rules['minimum_valid']);form.addRow('至少有效词条',minimum)
        score=QDoubleSpinBox();score.setRange(0,50);score.setValue(rules['crit_score']);form.addRow('暴击＋爆伤/2 至少',score)
        first=QDoubleSpinBox();first.setRange(0,50);first.setValue(rules['first_crit']);form.addRow('首条双爆分值至少',first)
        before=QCheckBox('首条暴击/爆伤出现前必须全有效');before.setChecked(rules['require_valid_before_crit']);form.addRow(before)
        first_valid=QCheckBox('第一条必须是有效词条');first_valid.setChecked(rules['require_first_valid']);form.addRow(first_valid)
        note=QLabel('以上规则独立生效。合格锁定，不合格标记弃置；识别不完整时停止。');note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec():
            import re
            value={'require_double_crit':double.isChecked(),'valid_stats':[s.strip() for s in re.split('[、,，]',stats.text()) if s.strip()],'minimum_valid':minimum.value(),'crit_score':score.value(),'first_crit':first.value(), 'require_valid_before_crit':before.isChecked(),'require_first_valid':first_valid.isChecked()}
            try:make_request('enhance',enhance_rules=value)
            except ValueError as exc:QMessageBox.warning(self,'规则无效',str(exc));return
            self.prefs['enhance_rules']=value;atomic_json(RUNS/'manual-settings.json',self.settings())
    def choose_tool(self):
        path,_=QFileDialog.getOpenFileName(self,'选择账号工具','','Windows 程序 (*.exe)')
        if path:self.community_path.setText(path);atomic_json(RUNS/'manual-settings.json',self.settings())
    def game_window_command(self,action):
        if not self.active_id or not self.run_directory:return
        atomic_json(self.run_directory/'window-command.json',{'RequestId':self.active_id,'Id':str(uuid.uuid4()),'Action':action})
    def open_tool(self,key):
        if key=='community' and not self.community_path.text().strip():
            installed=read_json(ROOT/'tools/wwt-installation.json',{}).get('Executable')
            if installed and Path(installed).is_file():self.community_path.setText(installed)
        if key=='community' and self.community_path.text().strip():
            path=Path(self.community_path.text().strip())
            if path.is_file() and path.suffix.lower()=='.exe':QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)));return
            QMessageBox.warning(self,'程序路径不可用','请重新选择本机账号工具。');return
        QDesktopServices.openUrl(QUrl(TOOL_LINKS[key][1]))
    def sample_resources(self):
        import psutil
        process=psutil.Process();self.performance.setText(f'助手当前内存 {process.memory_info().rss/1024**2:.0f} MB，历史缓存 {len(self.history.cache)} 条。识别模型只在任务工作进程中加载。')

def configure_fonts(app):
    font_folder=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'Fonts'
    # The native Windows font database already resolves these families. Explicit
    # font registration is only needed by the offscreen QA platform; registering
    # full CJK collections in the live app unnecessarily duplicates font memory.
    if app.platformName()=='offscreen':
        for filename in ('msyh.ttc','msyhbd.ttc','simkai.ttf'):
            font=font_folder/filename
            if font.is_file():QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Microsoft YaHei UI',10))

def main():
    app=QApplication(sys.argv);configure_fonts(app);app.setStyleSheet(STYLE);app.setWindowIcon(QIcon(str(asset_path('qingxiao.ico','app.ico'))))
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('MC.Qingxiao.ManualAssistant')
    except Exception:pass
    lock=QSharedMemory(panel_instance_key())
    if not lock.create(1):QMessageBox.information(None,'鸣潮手动助手','助手已经打开，请从任务栏或托盘切回。');return 0
    window=Panel();window.show();return app.exec()

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        RUNS.mkdir(parents=True,exist_ok=True);(RUNS/'panel-error.log').write_text(traceback.format_exc(),encoding='utf-8');raise
