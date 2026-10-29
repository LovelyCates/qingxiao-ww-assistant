"""Construct and render all pages; the task bridge is disabled before import use."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import sys
import json
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'manual_launcher')]
from PySide6.QtWidgets import QApplication,QScrollArea
import assistant
import legacy_panel
import qingxiao_panel as ui

def main():
    output=ROOT/'local-runs/smoke';output.mkdir(parents=True,exist_ok=True)
    calls=[]
    def bridge(panel,action,callback):
        calls.append(action)
        if action!='status':raise AssertionError('Smoke test attempted game dispatch')
        callback({'Ok':True,'Tasks':[]})
    app=QApplication([]);ui.configure_fonts(app);app.setStyleSheet(ui.STYLE)
    with tempfile.TemporaryDirectory(dir=output) as temp:
        runs=Path(temp)
        with patch.object(ui,'RUNS',runs),patch.object(legacy_panel,'RUNS',runs),patch.object(assistant,'CONFIG',runs/'assistant-settings.json'),patch.object(ui.Panel,'bridge',bridge):
            window=ui.Panel();window.timer.stop();window.show();rows=[]
            for width,height in [(1120,760),(1440,960)]:
                window.resize(width,height);app.processEvents()
                for index in range(window.pages.count()):
                    window.switch_page(index);app.processEvents();page=window.pages.widget(index)
                    overflow=max([s.horizontalScrollBar().maximum() for s in [page,*page.findChildren(QScrollArea)] if isinstance(s,QScrollArea)]+[0])
                    assert overflow==0,(width,index,overflow)
                    rows.append({'size':[width,height],'page':window.nav[index].text(),'overflow':overflow})
                    window.grab().save(str(output/f'{width}-{index}.png'))
            assert window.pages.count()==9 and len(window.buttons)==18
            assert window.active_id is None and not (runs/'pending-manual.json').exists()
            window.close();app.processEvents()
    result={'passed':True,'pages':9,'actions':18,'views':rows,'bridge_actions':calls,
            'interpreter':sys.executable,'python_prefix':sys.prefix,'python_base_prefix':sys.base_prefix,
            'source_root':str(ROOT),'personal_state_loaded':False,'game_dispatches':0}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'views':len(rows),'game_dispatches':0}))

if __name__=='__main__':main()
