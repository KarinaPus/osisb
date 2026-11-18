"""Rebuild report figures from measured CSV files; requires Pillow."""
import csv
import os
from pathlib import Path
from statistics import mean
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'report' / 'figures'
OUT.mkdir(parents=True, exist_ok=True)

def font(size):
    return ImageFont.truetype('C:/Windows/Fonts/times.ttf', size)

def load(mode):
    directory = Path(os.environ.get('REPORT_DATA_DIR', str(ROOT / 'data' / 'verified')))
    with (directory / (mode + '.csv')).open() as f:
        return list(csv.DictReader(f))

def chart(field, label, filename):
    im = Image.new('RGB', (1800, 1000), 'white')
    d = ImageDraw.Draw(im)
    series = []
    for mode, title, color in [('standard', '60 операций', '#1f5b96'),
                               ('individual', '685 операций', '#a53b28')]:
        rows = load(mode)
        points = [(n, mean(float(r[field]) for r in rows
                           if int(r['reader_count']) == n)) for n in range(3, 9)]
        series.append((title, color, points))
    ymax = max(v for _, _, pts in series for _, v in pts) * 1.15 or 1
    left, right, top, bottom = 190, 1690, 160, 820
    d.text((left, 25), label, font=font(38), fill='black')
    for i in range(6):
        value = ymax * i / 5
        y = bottom - (bottom - top) * i / 5
        d.line((left, y, right, y), fill='#cccccc', width=2)
        d.text((20, y-18), f'{value:.1f}', font=font(30), fill='black')
    d.line((left, top, left, bottom, right, bottom), fill='black', width=3)
    for n in range(3, 9):
        x = left + (n-3)*(right-left)/5
        d.text((x-10, bottom+20), str(n), font=font(32), fill='black')
    for j, (title, color, pts) in enumerate(series):
        coords = [(left+(n-3)*(right-left)/5,
                   bottom-v/ymax*(bottom-top)) for n, v in pts]
        d.line(coords, fill=color, width=5)
        for x, y in coords:
            d.ellipse((x-8, y-8, x+8, y+8), fill=color)
        x = 550 + j*550
        d.line((x, 110, x+80, 110), fill=color, width=6)
        d.text((x+95, 88), title, font=font(32), fill='black')
    d.text((650, 920), 'Число читателей', font=font(36), fill='black')
    im.save(OUT / filename)

def diagram():
    im = Image.new('RGB', (1800, 1050), 'white')
    d = ImageDraw.Draw(im)
    def box(x, y, text):
        d.rectangle((x, y, x+700, y+120), outline='black', width=3)
        d.multiline_text((x+20, y+15), text, font=font(32), fill='black')
    def arrow(x1, y1, x2, y2):
        d.line((x1, y1, x2, y2), fill='black', width=3)
        d.polygon([(x2,y2),(x2-10,y2-18),(x2+10,y2-18)], fill='black')
    box(60,40,'ЧИТАТЕЛЬ\nMutex счётчика: захват')
    box(60,240,'Первый читатель: захват Semaphore\nУвеличение счётчика, возврат Mutex')
    box(60,440,'Совместное чтение\nНовые читатели могут присоединиться')
    box(60,640,'Mutex: уменьшение счётчика\nПоследний читатель: возврат Semaphore')
    box(1030,240,'ПИСАТЕЛЬ\nОжидание Semaphore ресурса')
    box(1030,440,'Исключительная запись\nДругие участники ресурс не используют')
    box(1030,640,'Возврат Semaphore\nСледующая операция или завершение')
    for x, ys in [(410, [160,360,560]), (1380, [360,560])]:
        for y in ys:
            arrow(x,y,x,y+80)
    d.text((130,860),'Mutex защищает счётчик группы читателей.',font=font(36),fill='black')
    d.text((130,920),'Semaphore (1, 1) разделяет группу читателей и писателя.',font=font(36),fill='black')
    im.save(OUT / 'interaction.png')

if __name__ == '__main__':
    chart('elapsed_ms', 'Время выполнения, мс', 'elapsed.png')
    chart('average_writer_wait_ms', 'Среднее ожидание писателя, мс', 'wait.png')
    diagram()
