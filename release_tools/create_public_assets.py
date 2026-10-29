"""Render original geometric SVG assets, without game-character references."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtGui import QGuiApplication,QImage,QPainter
from PySide6.QtSvg import QSvgRenderer
from PIL import Image

def main():
    app=QGuiApplication([])
    folder=Path(__file__).resolve().parents[1]/'manual_launcher/assets'
    folder.mkdir(exist_ok=True)
    icon='''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect width="256" height="256" rx="60" fill="#24796e"/><path d="M38 112 Q83 60 128 112 T218 112 M38 146 Q83 94 128 146 T218 146 M38 180 Q83 128 128 180 T218 180" fill="none" stroke="#e9f8ef" stroke-width="14" stroke-linecap="round"/><circle cx="183" cy="61" r="14" fill="#ddc38a"/></svg>'''
    background='''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><defs><linearGradient id="g"><stop stop-color="#f3faf5"/><stop offset="1" stop-color="#bbd9cf"/></linearGradient></defs><rect width="1280" height="720" fill="url(#g)"/><path d="M0 560 Q180 420 360 560 T720 560 T1080 560 T1440 560 V720 H0" fill="#a4c7bc"/><path d="M0 640 Q210 500 420 640 T840 640 T1260 640 V720 H0" fill="#72aa99"/><circle cx="1080" cy="185" r="65" fill="#f7f3da"/></svg>'''
    for name,svg,size in [('app-icon',icon,(256,256)),('app-background',background,(1280,720))]:
        (folder/(name+'.svg')).write_text(svg,encoding='utf-8')
        image=QImage(*size,QImage.Format_ARGB32);image.fill(0)
        painter=QPainter(image);QSvgRenderer(svg.encode()).render(painter);painter.end()
        assert image.save(str(folder/(name+'.png')))
    with Image.open(folder/'app-icon.png') as image:image.save(folder/'app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    (folder/'PUBLIC-ASSETS.txt').write_text('Original geometric SVGs and rendered icons created for this project. No game character reference is used. Final project license applies; see RELEASE_STATUS.md.\n',encoding='utf-8')
    print('Rendered 2 original SVGs, 2 PNGs and one application ICO.')

if __name__=='__main__':main()
