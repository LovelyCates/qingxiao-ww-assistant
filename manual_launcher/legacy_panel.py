"""Click-to-run local Wuthering Waves panel. Opening it never starts a game job."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import traceback

from PySide6.QtCore import QProcess, QSharedMemory, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget)

from model import JOBS, MATERIALS, ROOT, RUNS, STAGES, STATES, atomic_json, make_request, read_json
from history import IncrementalTail

SHELL = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
BRIDGE = ROOT / 'manual_launcher/Task-Bridge.ps1'
STYLE = '''
QMainWindow,QWidget#surface {background:#f2f6f4;color:#173b32;}
QLabel {color:#25483e;} QLabel#heading {font-size:27px;font-weight:700;}
QLabel#badge {color:#08715d;background:#ddede5;padding:7px 13px;border-radius:12px;}
QLabel#subtle {color:#637c73;font-size:12px;} QLabel#cardTitle {font-size:16px;font-weight:650;}
QFrame#card,QFrame#status {background:white;border:1px solid #d7e3dc;border-radius:13px;}
QPushButton {background:#14775f;color:white;border:0;border-radius:7px;padding:9px 15px;font-weight:600;}
QPushButton:hover {background:#0d634f;} QPushButton:disabled {background:#c9d7cf;color:#6b7e74;}
QPushButton#secondary {background:#e7eeea;color:#244d3d;} QPushButton#secondary:hover {background:#d6e4dc;}
QPushButton#stop {background:#a74540;} QPushButton#stop:disabled {background:#e3d4d1;color:#917872;}
QComboBox,QSpinBox {background:#f8fbf9;border:1px solid #ccdcd2;border-radius:5px;padding:4px;color:#234b3d;min-height:21px;}
QPlainTextEdit {background:#18382e;color:#dcf0e4;border:0;border-radius:10px;padding:9px;font:11px Consolas;}
QScrollArea {border:0;background:transparent;} QScrollBar:vertical {width:8px;background:#e3ebe6;}
'''


class TaskScroll(QScrollArea):
    """Keep task cards readable when the console is narrowed."""
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, 'cards'):
            return
        columns = 2 if self.viewport().width() >= 610 else 1
        if columns == getattr(self, 'columns', None):
            return
        self.columns = columns
        for card in self.cards:
            self.grid.removeWidget(card)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)
        for n, card in enumerate(self.cards):
            self.grid.addWidget(card, n // columns, n % columns)
        self.grid.invalidate()
        self.grid.activate()
        self.widget().resize(self.viewport().width(), max(self.viewport().height(), self.widget().minimumSizeHint().height()))


class Panel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('鸣潮手动助手')
        self.resize(1170, 890)
        self.setMinimumSize(1010, 740)
        self.active_id = None
        self.active_task = None
        self.active_since = 0.0
        self.stopping = False
        self.report_path = None
        self.run_directory = None
        self.processes = []
        self.buttons = []
        self.controls = {}
        self.prefs = read_json(RUNS / 'manual-settings.json', {})
        self.last_log = ''
        self.tail = IncrementalTail()
        self.check_pending = False

        surface = QWidget(objectName='surface')
        self.setCentralWidget(surface)
        outer = QVBoxLayout(surface)
        outer.setContentsMargins(25, 22, 25, 20)
        outer.setSpacing(15)
        top = QHBoxLayout()
        top.addWidget(QLabel('鸣潮手动助手', objectName='heading'))
        top.addStretch()
        top.addWidget(QLabel('纯手动 · 无定时', objectName='badge'))
        outer.addLayout(top)
        outer.addWidget(QLabel('选择任务，点一下开始。已完成的日常和周常会跳过；刷本只用自然体力。', objectName='subtle'))
        body = QHBoxLayout()
        body.setSpacing(18)
        outer.addLayout(body, 1)

        scroll = TaskScroll()
        scroll.setWidgetResizable(True)
        cards = QWidget(objectName='surface')
        grid = QGridLayout(cards)
        scroll.grid = grid
        scroll.cards = []
        grid.setContentsMargins(0, 0, 6, 0)
        grid.setHorizontalSpacing(13)
        grid.setVerticalSpacing(13)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        descriptions = {
            'probe': '只检查活跃度并截图，不刷副本。',
            'daily': '未满活跃时补日常、领取奖励；周常另点。',
            'tacet': '按索拉指南列表序号刷声骸，体力不足即停。',
            'forgery': '刷武器／技能培养材料，请选择所需目标。',
            'simulation': '选择贝币或经验材料，不补充体力。',
            'weekly': '检查 6000 游历值，未完成时进入乐园。',
            'echo': '按次数刷取声骸；不领取耗体力的挑战奖励。',
            'nightmare': '按地图解锁情况刷梦魇／聚落；可限制目标数量。',
        }
        order = ('probe', 'daily', 'tacet', 'forgery', 'simulation', 'weekly', 'echo', 'nightmare')
        for n, action in enumerate(order):
            card = QFrame(objectName='card')
            scroll.cards.append(card)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(15, 12, 15, 12)
            layout.setSpacing(7)
            layout.addWidget(QLabel(JOBS[action][0], objectName='cardTitle'))
            desc = QLabel(descriptions[action], objectName='subtle')
            desc.setWordWrap(True)
            layout.addWidget(desc)
            settings = QHBoxLayout()
            if action in ('tacet', 'forgery'):
                settings.addWidget(QLabel('目标序号'))
                spin = QSpinBox()
                spin.setRange(1, 21 if action == 'tacet' else 20)
                spin.setValue(int(self.prefs.get(action + '_index', 1)))
                spin.setToolTip('按游戏 F2 指南的对应分类，从上到下数；请核对奖励材料。')
                self.controls[action + '_index'] = spin
                settings.addWidget(spin)
            elif action == 'simulation':
                combo = QComboBox()
                for label, value in MATERIALS.items():
                    combo.addItem(label, value)
                combo.setCurrentIndex(max(0, combo.findData(self.prefs.get('material', 'Shell Credit'))))
                self.controls['material'] = combo
                settings.addWidget(combo)
            elif action == 'echo':
                combo = QComboBox()
                for label, value in (('大世界 Boss', 'boss'), ('周本（只刷声骸）', 'weekly'), ('特殊梦魇', 'nightmare')):
                    combo.addItem(label, value)
                combo.setCurrentIndex(max(0, combo.findData(self.prefs.get('scope', 'boss'))))
                combo.setMinimumContentsLength(4)
                combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                combo.setMaximumWidth(130)
                self.controls['scope'] = combo
                index = QSpinBox()
                self.controls['echo_index'] = index
                index.setToolTip('对应分类中的目标序号')
                index.setFixedWidth(76)
                def update_range(_unused=None, box=combo, spin=index):
                    spin.setRange(1, {'boss': 20, 'weekly': 9, 'nightmare': 10}[box.currentData()])
                combo.currentIndexChanged.connect(update_range)
                update_range()
                index.setValue(int(self.prefs.get('echo_index', 1)))
                count = QSpinBox()
                count.setRange(1, 100)
                count.setSuffix(' 次')
                count.setValue(int(self.prefs.get('count', 5)))
                count.setFixedWidth(100)
                self.controls['count'] = count
                layout.addWidget(combo)
                settings.addWidget(QLabel('目标序号'))
                settings.addWidget(index)
                settings.addWidget(count)
            elif action == 'nightmare':
                combo = QComboBox()
                for label, value in (('梦魇＋残象聚落', 'all'), ('只刷梦魇净化', 'purification'), ('只刷残象聚落', 'nest')):
                    combo.addItem(label, value)
                combo.setCurrentIndex(max(0, combo.findData(self.prefs.get('kind', 'all'))))
                self.controls['kind'] = combo
                settings.addWidget(combo)
            else:
                label = '检测已实测' if action in ('probe', 'weekly') else '先检查完成状态，再按需执行'
                settings.addWidget(QLabel(label, objectName='subtle'))
            settings.addStretch()
            layout.addLayout(settings)
            button = QPushButton('开始' if action != 'probe' else '检查进度')
            button.setObjectName('start_' + action)
            button.clicked.connect(lambda checked=False, job=action: self.start_job(job))
            self.buttons.append(button)
            layout.addWidget(button)
            grid.addWidget(card, n // 2, n % 2)
        scroll.setWidget(cards)
        body.addWidget(scroll, 3)

        right = QVBoxLayout()
        body.addLayout(right, 2)
        status_box = QFrame(objectName='status')
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(19, 17, 19, 17)
        self.status = QLabel('准备就绪')
        self.status.setStyleSheet('font-size:21px;font-weight:650;')
        self.status.setWordWrap(True)
        status_layout.addWidget(self.status)
        self.details = QLabel('点击左侧任务后开始。打开助手不会启动游戏。')
        self.details.setWordWrap(True)
        self.details.setMinimumHeight(80)
        status_layout.addWidget(self.details)
        self.permission_note = QLabel('正在检查手动运行入口……', objectName='subtle')
        self.permission_note.setWordWrap(True)
        status_layout.addWidget(self.permission_note)
        self.stop_button = QPushButton('停止当前任务', objectName='stop')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_job)
        status_layout.addWidget(self.stop_button)
        self.report_button = QPushButton('查看本次结果', objectName='secondary')
        self.report_button.setEnabled(False)
        self.report_button.clicked.connect(self.open_report)
        status_layout.addWidget(self.report_button)
        folder = QPushButton('打开所有运行记录', objectName='secondary')
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(RUNS))))
        status_layout.addWidget(folder)
        right.addWidget(status_box)
        right.addWidget(QLabel('运行日志', objectName='subtle'))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText('任务开始后，这里显示实时日志。')
        right.addWidget(self.log, 1)
        note = QLabel('首次登录、验证码和更新提示请在游戏窗口完成。\n保留完整项目文件夹，并在偏好设置中选择游戏启动器。', objectName='subtle')
        note.setWordWrap(True)
        outer.addWidget(note)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(900)
        QTimer.singleShot(100, self.inspect_tasks)

    def bridge(self, action, callback):
        process = QProcess(self)
        self.processes.append(process)
        process.setProcessChannelMode(QProcess.MergedChannels)
        arguments = ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass',
                     '-File', str(BRIDGE), '-Action', action]
        if action != 'status':
            arguments += ['-TaskName', self.active_task or 'MC-Auto-probe', '-RequestId', self.active_id or '']
        def finished(code, exit_status):
            from shiboken6 import isValid
            if not isValid(process):
                return
            raw = bytes(process.readAllStandardOutput()).decode('utf-8-sig', errors='replace')
            try:
                rows = [line for line in raw.splitlines() if line.strip().startswith('{')]
                result = json.loads(rows[-1]) if rows else {'Ok': False, 'Error': raw.strip() or '无法读取运行入口'}
            except ValueError:
                result = {'Ok': False, 'Error': raw[-1500:]}
            callback(result)
            self.processes.remove(process)
            process.deleteLater()
        process.finished.connect(finished)
        process.start(str(SHELL), arguments)

    def inspect_tasks(self):
        def inspected(result):
            if not result.get('Ok'):
                self.permission_note.setText('手动入口检查失败：' + result.get('Error', '未知错误'))
                return
            tasks = result.get('Tasks', [])
            timed = any(t.get('Triggers', 0) for t in tasks)
            self.permission_note.setText('手动入口可用 · 没有定时触发' if not timed else '检测到自动触发，请检查项目任务设置')
            current = read_json(RUNS / 'manual-state.json', {})
            running_names = {t['Name'] for t in tasks if t.get('State') == 'Running'}
            if current.get('TaskName') in running_names and current.get('State') in ('starting', 'running'):
                self.active_id = current['RequestId']
                self.active_task = current['TaskName']
                self.active_since = time.monotonic()
                self.set_busy(True)
            elif running_names:
                self.permission_note.setText('已有游戏任务正在运行，请等待结束后再开始。')
            elif current.get('Report'):
                self.report_path = self.safe_path(current['Report'])
                self.report_button.setEnabled(bool(self.report_path and self.report_path.exists()))
        self.bridge('status', inspected)

    @staticmethod
    def safe_path(value):
        try:
            path = Path(value).resolve()
            path.relative_to(RUNS.resolve())
            return path
        except (ValueError, TypeError, OSError):
            return None

    def settings(self):
        result = {}
        for name, control in self.controls.items():
            result[name] = control.value() if isinstance(control, QSpinBox) else control.currentData()
        return result

    def set_busy(self, busy):
        for button in self.buttons:
            button.setEnabled(not busy)
        self.stop_button.setEnabled(busy and not self.stopping)

    def start_job(self, action):
        if self.active_id:
            return
        prefs = self.settings()
        index = prefs.get(action + '_index', 1)
        if action == 'echo':
            index = prefs['echo_index']
        request = make_request(action, index=index, material=prefs['material'],
                               count=prefs['count'], scope=prefs['scope'], kind=prefs['kind'])
        atomic_json(RUNS / 'manual-settings.json', prefs)
        atomic_json(RUNS / 'pending-manual.json', request)
        self.active_id = request['RequestId']
        self.active_task = JOBS[action][2]
        self.active_since = time.monotonic()
        self.stopping = False
        self.run_directory = self.report_path = None
        self.status.setText('正在启动：' + JOBS[action][0])
        self.details.setText('正在连接已打开的游戏；没有游戏进程时会尝试启动官方客户端。')
        self.log.clear()
        self.last_log = ''
        self.report_button.setEnabled(False)
        self.set_busy(True)
        def started(result):
            if not result.get('Ok'):
                self.cancel_pending()
                self.status.setText('未能开始')
                self.details.setText(result.get('Error', '请查看运行记录'))
                self.active_id = self.active_task = None
                self.set_busy(False)
        self.bridge('start', started)

    def cancel_pending(self):
        path = RUNS / 'pending-manual.json'
        pending = read_json(path, {})
        if pending.get('RequestId') == self.active_id:
            try:
                os.replace(path, RUNS / ('cancelled-' + self.active_id + '.json'))
            except OSError:
                pass

    def stop_job(self):
        if not self.active_id:
            return
        self.stopping = True
        self.stop_button.setEnabled(False)
        self.status.setText('正在停止')
        self.details.setText('停止本次脚本，保留游戏窗口。')
        if self.run_directory:
            atomic_json(self.run_directory / 'stop-request.json', {'RequestId': self.active_id, 'Stop': True})
        self.cancel_pending()
        # A running worker watches the stop file. The scheduler stop is only needed
        # before the worker has acknowledged its run directory.
        if not self.run_directory:
            self.bridge('stop', lambda result: self.finish_early_stop())

    def finish_early_stop(self):
        self.active_id = self.active_task = None
        self.stopping = False
        self.status.setText('已停止')
        self.details.setText('本次启动已取消。游戏窗口保留。')
        self.set_busy(False)

    def poll(self):
        if not self.active_id:
            return
        state = read_json(RUNS / 'manual-state.json', {})
        if state.get('RequestId') != self.active_id:
            if time.monotonic() - self.active_since > 30:
                self.cancel_pending()
                error = read_json(RUNS / 'wrapper-error.json', {})
                self.status.setText('启动未完成')
                self.details.setText(error.get('Error') or '请确认游戏没有停在权限、更新或登录提示中。')
                self.active_id = self.active_task = None
                self.set_busy(False)
            return
        self.report_path = self.safe_path(state.get('Report'))
        self.run_directory = self.safe_path(state.get('RunDirectory'))
        report = read_json(self.report_path, {}) if self.report_path else {}
        if self.report_path:
            self.report_button.setEnabled(self.report_path.with_suffix('.html').exists())
        status = report.get('status', 'STARTING')
        action = state.get('Action', 'probe')
        if not self.stopping:
            self.status.setText(('正在运行：' + JOBS.get(action, ('任务',))[0]) if status == 'STARTING' else STATES.get(status, status))
        finished = state.get('State') in ('completed', 'failed', 'cancelled', 'timeout')
        stage = STAGES.get(report.get('stage'))
        if finished or report.get('ended_at'):
            lines = ['本次任务已结束。']
            if stage:
                lines.append('最后进度：' + stage)
            if status in ('FAILED', 'TIMEOUT', 'NEEDS_REVIEW'):
                lines.append('请查看本次结果中的异常和截图；不会自动重试。')
        else:
            lines = [stage or '正在处理，请稍候']
        if report.get('activity_points') is not None:
            lines.append('日常活跃度：' + str(report['activity_points']) + ' / 100')
        if report.get('selected_echo_level') is not None:
            lines.append('当前声骸等级：+' + str(report['selected_echo_level']) + '；未消耗材料')
        if report.get('check_only') and report.get('discard_filter_verified'):
            lines.append(f'已核对弃置筛选，选中 {report["merge_selected_materials"]}/100 个；未提交融合')
        if report.get('weekly_progress_points') is not None:
            lines.append('本周游历值：' + str(report['weekly_progress_points']) + ' / 6000')
        if report.get('stamina_before') is not None:
            lines.append('初始自然体力：' + str(report['stamina_before']))
        if report.get('stamina_spent') is not None:
            lines.append('已核对消耗：' + str(report['stamina_spent']) + ' 点')
        if report.get('stamina_after') is not None:
            lines.append('剩余自然体力：' + str(report['stamina_after']))
        if state.get('Error'):
            lines.append(state['Error'])
        if not self.stopping:
            self.details.setText('\n'.join(lines))
        if self.run_directory:
            content, changed = self.tail.read(self.run_directory)
            if changed and content != self.last_log:
                self.last_log = content
                scroll = self.log.verticalScrollBar()
                position = scroll.value()
                follow = position >= scroll.maximum() - 2
                self.log.setPlainText(content)
                scroll.setValue(scroll.maximum() if follow else position)
        cancelled = status == 'CANCELLED' and report.get('ended_at')
        if finished or cancelled:
            if state.get('State') == 'timeout':
                self.status.setText('运行超时，已停止')
            elif self.stopping or cancelled:
                self.status.setText('已停止')
                self.details.setText('本次脚本已停止，游戏窗口保留。')
            elif state.get('State') == 'failed' and status == 'STARTING':
                self.status.setText('启动失败')
                self.details.setText(state.get('Error') or '请查看本次结果和日志。')
            self.active_id = self.active_task = None
            self.stopping = False
            self.set_busy(False)

    def open_report(self):
        if self.report_path:
            path = self.report_path.with_suffix('.html')
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event):
        if self.active_id:
            box = QMessageBox(self)
            box.setWindowTitle('当前任务仍在运行')
            box.setText('关闭助手时，如何处理当前任务？')
            stop = box.addButton('停止并关闭', QMessageBox.AcceptRole)
            background = box.addButton('继续后台运行', QMessageBox.DestructiveRole)
            back = box.addButton('返回面板', QMessageBox.RejectRole)
            box.setDefaultButton(back)
            box.exec()
            if box.clickedButton() == back:
                event.ignore()
                return
            if box.clickedButton() == stop:
                self.stop_job()
                if not self.run_directory:
                    event.ignore()
                    QTimer.singleShot(1500, self.close)
                    return
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont('Microsoft YaHei UI', 10))
    app.setStyleSheet(STYLE)
    lock = QSharedMemory('MC-Manual-Panel-G-AIGC-MC')
    if not lock.create(1):
        QMessageBox.information(None, '鸣潮手动助手', '助手已经打开，请从任务栏切回。')
        return 0
    window = Panel()
    window.show()
    return app.exec()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        RUNS.mkdir(parents=True, exist_ok=True)
        (RUNS / 'panel-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        raise
