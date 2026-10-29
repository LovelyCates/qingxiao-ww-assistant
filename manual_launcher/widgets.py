"""Lightweight native painted visualizations; no browser or chart runtime."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QLinearGradient
from PySide6.QtWidgets import QWidget, QSizePolicy
from history import SUCCESS

class Hero(QWidget):
    def __init__(self, image, parent=None):
        super().__init__(parent)
        self.source = QPixmap(str(image))
        self.setMinimumHeight(290)
        self.setMaximumHeight(350)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        from PySide6.QtGui import QPainterPath
        path=QPainterPath();path.addRoundedRect(QRectF(self.rect()),26,26);p.setClipPath(path)
        if not self.source.isNull():
            size=self.source.size().scaled(self.size(),Qt.KeepAspectRatioByExpanding)
            p.drawPixmap(QRectF((self.width()-size.width())/2,0,size.width(),size.height()),self.source,QRectF(self.source.rect()))
        fade=QLinearGradient(0,0,self.width()*0.75,0)
        fade.setColorAt(0,QColor(244,250,246,245));fade.setColorAt(0.56,QColor(244,250,246,200));fade.setColorAt(1,QColor(244,250,246,0))
        p.fillRect(self.rect(),fade)

class ProgressRing(QWidget):
    def __init__(self, title, total, parent=None):
        super().__init__(parent);self.title=title;self.total=total;self.value=None;self.setMinimumSize(160,170)
    def setValue(self,value):
        if value!=self.value:self.value=value;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        side=min(self.width()-30,120);rect=QRectF((self.width()-side)/2,10,side,side)
        pen=QPen(QColor('#e0ece7'),9);pen.setCapStyle(Qt.RoundCap);p.setPen(pen);p.drawArc(rect,0,5760)
        if self.value is not None:
            p.setPen(QPen(QColor('#2e8478'),9,Qt.SolidLine,Qt.RoundCap));p.drawArc(rect,90*16,-int(min(1,self.value/self.total)*5760))
        p.setPen(QColor('#163f42'));p.setFont(QFont('Microsoft YaHei UI',22,QFont.Bold))
        p.drawText(rect,Qt.AlignCenter,'—' if self.value is None else str(self.value))
        p.setFont(QFont('Microsoft YaHei UI',10));p.drawText(QRectF(0,side+25,self.width(),30),Qt.AlignCenter,self.title)

class RunChart(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.records=[];self.setMinimumHeight(150)
    def setRecords(self,records):
        signature=[(r.get('_run'),r.get('status')) for r in records[:12]]
        if signature!=[(r.get('_run'),r.get('status')) for r in self.records]:
            self.records=list(records[:12]);self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setPen(QColor('#6c8581'));p.setFont(QFont('Microsoft YaHei UI',9))
        if not self.records:p.drawText(self.rect(),Qt.AlignCenter,'运行任务后，这里显示真实耗时与结果');return
        records=list(reversed(self.records));width=(self.width()-30)/len(records)
        durations=[]
        from datetime import datetime
        for r in records:
            try:seconds=max(1,(datetime.fromisoformat(r['ended_at'])-datetime.fromisoformat(r['started_at'])).total_seconds())
            except (KeyError,ValueError):seconds=0
            durations.append(seconds)
        maximum=max(durations+[1]);height=self.height()-40
        for n,(r,seconds) in enumerate(zip(records,durations)):
            color='#69b9a9' if r.get('status') in SUCCESS else '#d5af69' if r.get('status')=='CANCELLED' else '#b97e7c'
            bar=max(3,height*seconds/maximum);x=15+n*width
            p.setPen(Qt.NoPen);p.setBrush(QColor(color));p.drawRoundedRect(QRectF(x,height-bar,max(5,width-12),bar),5,5)
            p.setPen(QColor('#637c73'));p.drawText(QRectF(x,height+5,width-8,24),Qt.AlignCenter,f'{seconds:.0f}s')
