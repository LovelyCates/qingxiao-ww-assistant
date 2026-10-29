"""Saved-account management for the personal launcher."""
from copy import deepcopy
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QDialog,QDialogButtonBox,QVBoxLayout,QHBoxLayout,
    QFormLayout,QLabel,QLineEdit,QCheckBox,QComboBox,QSpinBox,QPushButton,QListWidget,
    QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox)
from accounts import TASKS,normalize_accounts,normalize_step,load_accounts,save_accounts
from model import read_json


def step_text(step):
    options=step.get('options',{});details=[]
    if step['action']=='daily':details.append({'tacet':'无音区','forgery':'凝素领域','simulation':'模拟训练'}[options.get('daily_farm','tacet')])
    if 'index' in options:details.append('指南第'+str(options['index'])+'项')
    if 'material' in options:details.append({'Shell Credit':'贝币','Resonator EXP':'共鸣者经验','Weapon EXP':'武器经验'}[options['material']])
    if 'count' in options:details.append(str(options['count'])+'轮')
    if 'stamina_limit' in options:details.append('最多'+str(options['stamina_limit'])+'体力')
    if 'target_limit' in options:details.append('最多'+str(options['target_limit'])+'个目标')
    return TASKS[step['action']]+(' · '+'，'.join(details) if details else '')


class StepDialog(QDialog):
    def __init__(self,parent,step=None):
        super().__init__(parent);self.setWindowTitle('账号任务');self.resize(480,330)
        form=QFormLayout(self);self.action=QComboBox()
        for key,label in TASKS.items():self.action.addItem(label,key)
        form.addRow('任务',self.action)
        self.farm=QComboBox()
        for key,label in (('tacet','无音区'),('forgery','凝素领域'),('simulation','模拟训练')):self.farm.addItem(label,key)
        form.addRow('日常刷取类型',self.farm)
        self.index=QSpinBox();self.index.setRange(1,21);form.addRow('指南列表序号',self.index)
        self.material=QComboBox()
        for key,label in (('Shell Credit','贝币'),('Resonator EXP','共鸣者经验'),('Weapon EXP','武器经验')):self.material.addItem(label,key)
        form.addRow('训练材料',self.material)
        self.scope=QComboBox()
        for key,label in (('boss','普通Boss'),('weekly','周本Boss'),('nightmare','特殊梦魇')):self.scope.addItem(label,key)
        form.addRow('Boss 类型',self.scope)
        self.kind=QComboBox()
        for key,label in (('all','全部'),('purification','梦魇净化'),('nest','残象聚落')):self.kind.addItem(label,key)
        form.addRow('聚落范围',self.kind)
        self.count=QSpinBox();self.count.setRange(1,100);form.addRow('Boss轮数／聚落目标数',self.count)
        self.limit=QSpinBox();self.limit.setRange(0,240);self.limit.setSpecialValueText('用完自然体力');form.addRow('体力消耗上限',self.limit)
        self.error=QLabel();self.error.setWordWrap(True);form.addRow(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept_step);buttons.rejected.connect(self.reject);form.addRow(buttons)
        buttons.button(QDialogButtonBox.Save).setText('保存');buttons.button(QDialogButtonBox.Cancel).setText('取消')
        self.action.currentIndexChanged.connect(self.refresh);self.farm.currentIndexChanged.connect(self.refresh);self.scope.currentIndexChanged.connect(self.refresh)
        step=step or {'action':'daily','options':{}};opts=step.get('options',{})
        self.action.setCurrentIndex(self.action.findData(step['action']))
        for widget,key,default in ((self.farm,'daily_farm','tacet'),(self.material,'material','Shell Credit'),(self.scope,'scope','boss'),(self.kind,'kind','all')):widget.setCurrentIndex(widget.findData(opts.get(key,default)))
        self.refresh();self.index.setValue(opts.get('index',1));self.count.setValue(opts.get('count',opts.get('target_limit',1)));self.limit.setValue(opts.get('stamina_limit',0))

    def refresh(self):
        action=self.action.currentData();target=self.farm.currentData() if action=='daily' else action
        self.farm.setEnabled(action=='daily');self.index.setEnabled(target in ('tacet','forgery','echo'))
        maximum=21 if target=='tacet' else 20
        if target=='echo':maximum={'boss':20,'weekly':9,'nightmare':10}[self.scope.currentData()]
        self.index.setMaximum(maximum);self.material.setEnabled(target=='simulation')
        self.scope.setEnabled(action=='echo');self.kind.setEnabled(action=='nightmare');self.count.setEnabled(action in ('echo','nightmare'))
        cost=60 if action=='tacet' else 40
        self.limit.setSingleStep(cost);self.limit.setEnabled(action in ('tacet','forgery','simulation'))

    def accept_step(self):
        action=self.action.currentData();opts={}
        target=self.farm.currentData() if action=='daily' else action
        if action=='daily':opts['daily_farm']=target
        if target in ('tacet','forgery','echo'):opts['index']=self.index.value()
        if target=='simulation':opts['material']=self.material.currentData()
        if action=='echo':opts.update(count=self.count.value(),scope=self.scope.currentData())
        if action=='nightmare':opts.update(kind=self.kind.currentData(),target_limit=self.count.value())
        if action in ('tacet','forgery','simulation') and self.limit.value():opts['stamina_limit']=self.limit.value()
        try:self.value=normalize_step({'action':action,'options':opts})
        except ValueError as exc:self.error.setText(str(exc));return
        self.accept()


class AccountDialog(QDialog):
    def __init__(self,parent,profile=None):
        super().__init__(parent);self.setWindowTitle('账号与任务顺序');self.resize(650,590)
        self.profile=deepcopy(profile or dict(id=str(uuid.uuid4()),label='',account_key='',enabled=True,steps=[{'action':'daily','options':{'daily_farm':'tacet','index':1}}]))
        box=QVBoxLayout(self);form=QFormLayout();box.addLayout(form)
        self.label=QLineEdit(self.profile['label']);self.key=QLineEdit(self.profile['account_key']);self.key.setPlaceholderText('例如登录列表显示的 190****0971，可连同星号填写')
        self.enabled=QCheckBox('本轮启用');self.enabled.setChecked(self.profile['enabled'])
        form.addRow('账号备注',self.label);form.addRow('游戏登录列表标识',self.key);form.addRow(self.enabled)
        note=QLabel('只使用游戏已保存的登录状态，不保存密码或验证码。请先在游戏登录列表确认账号；显示标识相同的账号无法可靠区分。');note.setWordWrap(True);box.addWidget(note)
        box.addWidget(QLabel('任务按下列顺序执行；列表为空时仅登录。'));self.steps=QListWidget();box.addWidget(self.steps)
        row=QHBoxLayout()
        for label,callback in (('添加任务',lambda:self.edit_step(True)),('修改',lambda:self.edit_step(False)),('移除',self.remove_step),('上移',lambda:self.move_step(-1)),('下移',lambda:self.move_step(1))):
            b=QPushButton(label);b.clicked.connect(callback);row.addWidget(b)
        box.addLayout(row);self.error=QLabel();self.error.setWordWrap(True);box.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);box.addWidget(buttons);self.refresh()
        buttons.button(QDialogButtonBox.Save).setText('保存');buttons.button(QDialogButtonBox.Cancel).setText('取消')
    def refresh(self,selected=0):
        self.steps.clear();self.steps.addItems([step_text(s) for s in self.profile['steps']]);self.steps.setCurrentRow(selected)
    def edit_step(self,new):
        index=self.steps.currentRow()
        if new and len(self.profile['steps'])>=8:self.error.setText('每个账号最多8项任务。');return
        if not new and index<0:return
        dialog=StepDialog(self,None if new else self.profile['steps'][index])
        if dialog.exec():
            if new:self.profile['steps'].append(dialog.value);index=len(self.profile['steps'])-1
            else:self.profile['steps'][index]=dialog.value
            self.refresh(index)
    def remove_step(self):
        index=self.steps.currentRow()
        if index>=0:self.profile['steps'].pop(index);self.refresh(max(0,index-1))
    def move_step(self,offset):
        a=self.steps.currentRow();b=a+offset
        if 0<=a<len(self.profile['steps']) and 0<=b<len(self.profile['steps']):
            self.profile['steps'][a],self.profile['steps'][b]=self.profile['steps'][b],self.profile['steps'][a];self.refresh(b)
    def save(self):
        self.profile.update(label=self.label.text(),account_key=self.key.text(),enabled=self.enabled.isChecked())
        try:self.value=normalize_accounts([self.profile])[0]
        except ValueError as exc:self.error.setText(str(exc));return
        self.accept()


class AccountsPage(QWidget):
    def __init__(self,path,start,parent=None):
        super().__init__(parent);self.path=path;self.start=start;self.profiles=[]
        box=QVBoxLayout(self);box.addWidget(QLabel('多账号 · 各自配置，依次执行',objectName='section'))
        note=QLabel('先把账号登录并保存在游戏的切换账号列表，再在这里填写对应标识。执行时前台切号；各账号只用自然体力，失败即停。运行中修改配置只影响下一轮。');note.setWordWrap(True);box.addWidget(note)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['启用','账号备注','登录标识','任务顺序']);self.table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers);box.addWidget(self.table)
        row=QHBoxLayout()
        for label,callback in (('添加账号',lambda:self.edit(True)),('修改',lambda:self.edit(False)),('移除',self.remove),('上移',lambda:self.move(-1)),('下移',lambda:self.move(1))):
            button=QPushButton(label,objectName='secondary');button.clicked.connect(callback);row.addWidget(button)
        box.addLayout(row);self.note=QLabel();self.note.setWordWrap(True);box.addWidget(self.note)
        self.start_button=QPushButton('执行启用的账号');self.start_button.setObjectName('start_multiaccount');self.start_button.clicked.connect(lambda:self.start('multiaccount',{'accounts':deepcopy(self.profiles)}));box.addWidget(self.start_button)
        box.addWidget(QLabel('停止使用顶部“停止任务”；重试请在“运行记录”选择本轮，已核验完成的账号和步骤会跳过。',objectName='muted'))
        try:self.profiles=load_accounts(path)
        except (ValueError,OSError) as exc:self.note.setText('配置未载入：'+str(exc))
        self.refresh()
    def refresh(self,index=0):
        self.table.setRowCount(len(self.profiles))
        for n,p in enumerate(self.profiles):
            for col,value in enumerate(('是' if p['enabled'] else '否',p['label'],p['account_key'],' → '.join(step_text(s) for s in p['steps']) or '仅登录')):
                item=QTableWidgetItem(value);item.setToolTip(value);self.table.setItem(n,col,item)
        if self.profiles:self.table.selectRow(min(index,len(self.profiles)-1))
    def persist(self,profiles,index=0):
        try:save_accounts(self.path,profiles)
        except (ValueError,OSError) as exc:self.note.setText(str(exc));return
        self.profiles=normalize_accounts(profiles);self.note.setText('已保存到本机。');self.refresh(index)
    def edit(self,new):
        index=self.table.currentRow()
        if not new and index<0:return
        dialog=AccountDialog(self,None if new else self.profiles[index])
        if dialog.exec():
            rows=deepcopy(self.profiles)
            if new:rows.append(dialog.value);index=len(rows)-1
            else:rows[index]=dialog.value
            self.persist(rows,index)
    def remove(self):
        index=self.table.currentRow()
        if index>=0:rows=deepcopy(self.profiles);rows.pop(index);self.persist(rows,max(0,index-1))
    def move(self,offset):
        a=self.table.currentRow();b=a+offset
        if 0<=a<len(self.profiles) and 0<=b<len(self.profiles):
            rows=deepcopy(self.profiles);rows[a],rows[b]=rows[b],rows[a];self.persist(rows,b)
