"""Build the Word report after running the measured experiments."""
import csv
import math
import textwrap
from pathlib import Path
from statistics import mean
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from plot_report import chart, diagram, load

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'report'
OUT.mkdir(exist_ok=True)
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin, sec.right_margin = Cm(3), Cm(1.5)
sec.top_margin = sec.bottom_margin = Cm(2)
sec.footer_distance = Cm(1)
sec.different_first_page_header_footer = True
normal = doc.styles['Normal']
normal.font.name, normal.font.size = 'Times New Roman', Pt(14)
normal.paragraph_format.line_spacing = Pt(18)
normal.paragraph_format.first_line_indent = Cm(1.25)
normal.paragraph_format.space_after = Pt(0)
normal.paragraph_format.widow_control = True
def clean_style(st, face):
    rpr = st.element.get_or_add_rPr()
    fonts = rpr.find(qn('w:rFonts'))
    if fonts is None:
        fonts = OxmlElement('w:rFonts')
        rpr.insert(0, fonts)
    for key in list(fonts.attrib):
        del fonts.attrib[key]
    for key in ['ascii','hAnsi','eastAsia','cs']:
        fonts.set(qn('w:'+key), face)
    for border in st.element.findall('.//'+qn('w:pBdr')):
        border.getparent().remove(border)
clean_style(normal, 'Times New Roman')
for name in ['Title', 'Heading 1', 'Heading 2']:
    st = doc.styles[name]
    st.font.name, st.font.size = 'Times New Roman', Pt(14)
    st.font.bold = True
    st.font.color.rgb = RGBColor(0,0,0)
    st.paragraph_format.space_before = Pt(0)
    st.paragraph_format.space_after = Pt(18)
    st.paragraph_format.line_spacing = Pt(18)
    st.paragraph_format.first_line_indent = Cm(1.25)
    st.paragraph_format.keep_with_next = True
    clean_style(st, 'Times New Roman')
footer = sec.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
footer.paragraph_format.first_line_indent = Cm(0)
field = OxmlElement('w:fldSimple')
field.set(qn('w:instr'), 'PAGE')
footer._p.append(field)
page = 1
contents = []

def p(text='', center=False, size=None):
    par = doc.add_paragraph(text)
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.JUSTIFY
    if center:
        par.paragraph_format.first_line_indent = Cm(0)
    if size:
        for r in par.runs:
            r.font.size = Pt(size)
    return par

def heading(text, center=False, toc=True):
    par = doc.add_paragraph(text, 'Heading 1')
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    if center:
        par.paragraph_format.first_line_indent = Cm(0)
    if toc:
        contents.append((text, page))
    return par

def newpage():
    global page
    doc.add_page_break()
    page += 1

def table(headers, rows):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = 'Table Grid'
    for c, text in zip(t.rows[0].cells, headers):
        c.text = str(text)
    for values in rows:
        for c, value in zip(t.add_row().cells, values):
            c.text = str(value)
    for row in t.rows:
        for c in row.cells:
            for par in c.paragraphs:
                par.paragraph_format.first_line_indent = Cm(0)
                par.paragraph_format.line_spacing = Pt(14)
                for run in par.runs:
                    run.font.size = Pt(11)
        pr = row._tr.get_or_add_trPr()
        pr.append(OxmlElement('w:cantSplit'))
    t.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
    return t

def code(text):
    for line in text.splitlines():
        par = doc.add_paragraph()
        par.paragraph_format.first_line_indent = Cm(0)
        par.paragraph_format.line_spacing = Pt(10)
        par.paragraph_format.widow_control = False
        run = par.add_run(line or ' ')
        run.font.name, run.font.size = 'Consolas', Pt(8)

def fig(name, caption):
    par = p('', True)
    par.paragraph_format.line_spacing = 1
    par.add_run().add_picture(str(OUT/'figures'/name), width=Cm(16.3))
    p(caption, True, 12)

data = {mode: load(mode) for mode in ['standard','individual']}
for mode, rows in data.items():
    assert len(rows) == 18, (mode, len(rows))
    assert all(int(r['timeouts']) == int(r['invariant_violations']) == 0 for r in rows)
    assert all(int(r['successful_reads']) == int(r['reader_count'])*int(r['operations_per_participant']) for r in rows)
    assert all(int(r['successful_writes']) == 2*int(r['operations_per_participant']) for r in rows)
chart('elapsed_ms', 'Время выполнения, мс', 'elapsed.png')
chart('average_writer_wait_ms', 'Среднее ожидание писателя, мс', 'wait.png')
diagram()

p('Министерство образования Республики Беларусь', True)
p('Учреждение образования', True)
p('«Белорусский государственный университет\nинформатики и радиоэлектроники»', True)
p('Факультет ______________________________', True)
p('Кафедра _______________________________', True)
for _ in range(4): p()
title = doc.add_paragraph('ОТЧЁТ\nпо лабораторной работе № 4', 'Title')
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
title.paragraph_format.first_line_indent = Cm(0)
p('Взаимодействие процессов (потоков):\nвзаимное исключение и синхронизация', True)
p('Вариант 9 — Приоритет читателей', True)
p('Дисциплина: ОСиСП, часть 1', True)
for _ in range(3): p()
for text in ['Выполнила: студентка группы 453505',
             'Пушечникова Карина Валерьевна', 'Проверила: Сыс Анна Дмитриевна']:
    p(text).alignment = WD_ALIGN_PARAGRAPH.LEFT
for _ in range(3): p()
p('Минск 2026', True)
newpage()
heading('СОДЕРЖАНИЕ', True, False)
toc_anchor = doc.paragraphs[-1]
newpage()
heading('ВВЕДЕНИЕ', True)
p('В работе исследуется конкурентный доступ потоков к общему ресурсу на примере модели «Писатели–читатели». Реализован вариант с приоритетом читателей: несколько читателей могут работать одновременно, а запись требует исключительного доступа.')
p('Основная задача эксперимента — установить, как увеличение числа читателей с 3 до 8 влияет на ожидание двух писателей. Измерения проведены для стандартной нагрузки и индивидуальной нагрузки с STUDENT_ID = 125. Для каждой конфигурации выполнено три запуска.')
p('Разработанное приложение использует Mutex для защиты счётчика читателей и бинарный Semaphore для разграничения чтения и записи. Проверки во время выполнения контролируют отсутствие совместного чтения и записи и полноту выполненных операций.')
p('Все 36 измеренных запусков завершились без тайм-аутов и зарегистрированных нарушений инвариантов. Результаты характеризуют исследованную конечную нагрузку; отсутствие ошибок в опытах не означает гарантии справедливого обслуживания писателей при непрерывном поступлении читателей.')
newpage()
heading('1 ЦЕЛЬ РАБОТЫ')
p('Изучить механизмы взаимного исключения и синхронизации Windows API, реализовать согласованную работу потоков и экспериментально оценить влияние приоритета читателей на ожидание писателей.')
heading('2 ПОСТАНОВКА ИНДИВИДУАЛЬНОГО ЗАДАНИЯ')
p('Вариант 9. Реализовать модель «Писатели–читатели» с приоритетом читателей средствами Mutex и Semaphore. Новые читатели должны присоединяться к уже выполняющимся чтениям даже при наличии ожидающего писателя. Первый читатель блокирует доступ писателям, последний освобождает общий ресурс.')
p('Исследовать увеличение числа читателей с 3 до 8 при двух писателях. Основные параметры задаются без изменения исходного кода. Требуется регистрировать состояния и TID участников, собирать статистику, проверять корректность и обеспечивать завершение потоков.')
p('Для индивидуального эксперимента используются последние три цифры студенческого билета: STUDENT_ID = 125. Принято BASE_OPERATIONS = 60; в тексте варианта 9 численное значение этого параметра не задано. Тогда OPERATIONS = 60 + 125 · 5 = 685; SEED = 1000 + 125 · 97 = 13125.')
newpage()
heading('3 КРАТКИЕ ТЕОРЕТИЧЕСКИЕ СВЕДЕНИЯ')
p('Состояние гонки возникает, когда результат зависит от несогласованного порядка доступа потоков к общим данным. Взаимное исключение ограничивает доступ к критическому ресурсу, а синхронизация задаёт допустимый порядок операций.')
p('Mutex имеет владельца: освобождать его должен поток, выполнивший захват. Semaphore хранит счётчик разрешений; разрешение может вернуть другой поток [2, 3]. Это позволяет первому читателю захватить ресурс, а последнему — освободить его.')
p('Приоритет читателей допускает длительное ожидание писателя. Пока группа читателей непуста, новые чтения продлевают занятость ресурса. При непрерывном потоке запросов возможно голодание писателей. Тайм-аут выявляет длительное ожидание, но не превращает алгоритм в справедливую очередь.')
heading('4 АРХИТЕКТУРА ПРОГРАММЫ')
p('Приложение состоит из одного процесса. Options хранит параметры запуска; ReaderPreferenceLock реализует доступ к ресурсу; WinHandle и охранные объекты обеспечивают освобождение дескрипторов и блокировок. RuntimeState содержит атомарные счётчики, EventLogger сериализует журнал.')
p('run_trial создаёт участников и собирает результат одного опыта. run_mode перебирает конфигурации и повторы, записывает CSV. main выбирает стандартный и индивидуальный режимы. Потоки создаются средствами C++20 std::jthread; взаимное исключение ресурса реализовано Windows API.')
newpage()
heading('5 ПОТОКИ И ОБЩИЕ РЕСУРСЫ')
p('В каждом опыте создаются N читателей R1…RN и два писателя W1, W2. Каждый участник получает собственный генератор псевдослучайных задержек, уникальное обозначение и системный TID. Главный поток ожидает завершения всех участников.')
p('Общий ресурс shared_value — целое число. Писатель увеличивает его на единицу, читатель получает снимок значения. Счётчик active_readers_ защищён Mutex. Атомарные счётчики RuntimeState используются для статистики и проверки условий корректности.')
p('Дополнительный Mutex журнала защищает целостность строк вывода. std::latch разрешает запуск писателей после того, как каждый читатель начал первое чтение либо завершил попытку. Такая начальная организация обеспечивает присутствие читательской нагрузки, однако не гарантирует одновременного старта потоков.')
heading('6 МЕХАНИЗМЫ СИНХРОНИЗАЦИИ')
p('readers_mutex_ создаётся функцией CreateMutexW. Под ним изменяется число активных читателей. resource_ создаётся CreateSemaphoreW с начальным и максимальным счётчиком, равным 1. Группа читателей удерживает одно разрешение независимо от её размера.')
p('Ожидание выполняется WaitForSingleObject. Обрабатываются успешный захват, тайм-аут, отказ API и покинутый Mutex. ReleaseMutex и ReleaseSemaphore возвращают объекты в доступное состояние. CloseHandle вызывается после завершения потоков.')
newpage()
heading('7 АЛГОРИТМ РАБОТЫ')
p('Читатель захватывает Mutex счётчика. Если активных читателей нет, он ожидает Semaphore ресурса. После успешного захвата увеличивает счётчик и возвращает Mutex. Если группа уже активна, ожидание Semaphore пропускается: новый читатель присоединяется независимо от очереди писателей.')
code('''WinMutexGuard readers_guard(readers_mutex_.get(), timeout_ms, state_);
if (active_readers_ == 0) {
    SemaphoreGuard resource_guard(resource_.get(), remaining_ms, state_);
    resource_guard.relinquish_to_reader_group();
}
++active_readers_;
readers_guard.release();''')
p('После чтения участник снова захватывает Mutex, уменьшает счётчик и, если он стал нулевым, возвращает разрешение Semaphore. Mutex освобождается во всех штатных ветвях.')
code('''--active_readers_;
if (active_readers_ == 0) {
    ReleaseSemaphore(resource_.get(), 1, nullptr);
}
readers_guard.release();''')
p('Писатель ожидает тот же Semaphore, выполняет запись и возвращает разрешение. Счётчик читателей писателю не требуется. Фрагменты выше сокращены для объяснения; полный код с обработкой ошибок приведён в приложении Г.')
p('Порядок захвата исключает цикл ожидания: писатель не запрашивает Mutex читателей. У ожидающего первого читателя счётчик равен нулю, поэтому нет активной группы, которая должна захватить этот Mutex для возврата ресурса.')
newpage()
heading('8 СХЕМА ВЗАИМОДЕЙСТВИЯ')
p('На рисунке 1 показаны действия читателя и писателя. Ключевое условие — ожидание Semaphore только первым читателем. Освобождение ресурса выполняет последний участник группы.')
fig('interaction.png', 'Рисунок 1 — Взаимодействие читателей и писателя')
p('Рисунок сформирован скриптом scripts/plot_report.py. Редактируемое описание последовательности находится в diagrams/readers-writers.mmd; его текст приведён в приложении В. Эти исходники позволяют воспроизвести графические материалы.')
newpage()
heading('9 ИСПОЛЬЗОВАННЫЕ ФУНКЦИИ WINDOWS API')
p('Назначение основных функций приведено в таблице 1. Правила владения объектами и работы семафоров описаны в документации Microsoft [2–4].')
p('Таблица 1 — Функции Windows API', size=12)
table(['Функция', 'Назначение'], [
('CreateMutexW','Создание Mutex счётчика и Mutex журнала'),
('CreateSemaphoreW','Создание бинарного Semaphore ресурса'),
('WaitForSingleObject','Блокирующее ожидание с ограничением времени'),
('ReleaseMutex','Возврат Mutex потоком-владельцем'),
('ReleaseSemaphore','Возврат разрешения ресурса'),
('CloseHandle','Закрытие дескриптора объекта'),
('GetCurrentThreadId','Получение TID участника'),
('GetLastError','Диагностика отказа Windows API'),
('Sleep','Моделирование чтения, записи и пауз')])
p('Sleep не задаёт порядок доступа к общим данным. Фактическая задержка зависит от планировщика и разрешения системного таймера. Поэтому заданные 1–2 мс не следует считать измеренной продолжительностью операции.')
newpage()
heading('10 ПРОВЕРЯЕМЫЕ ИНВАРИАНТЫ')
p('Во время чтения writer_inside должен быть равен нулю. Перед записью атомарный переход writer_inside из 0 в 1 должен быть успешным, а число фактически выполняющихся чтений должно быть равно нулю. Нарушение приводит к регистрации ошибки и отмене дальнейшей работы.')
p('После завершения участников active_readers_, active_reader_operations и writer_inside должны быть равны нулю. Дополнительно shared_value должен совпадать с числом успешных записей. При отсутствии тайм-аутов проверяются ожидаемые количества чтений N · OPERATIONS и записей 2 · OPERATIONS.')
p('Дескрипторы закрываются после join. Ошибки освобождения включаются в итоговый счётчик нарушений. Результаты с тайм-аутами сохраняются отдельно от нарушений; тайм-аут означает незавершённую нагрузку, а не обязательно ошибку взаимного исключения.')
p('Короткая проверка tests/smoke.ps1 выполняет три запуска с тремя читателями, двумя писателями и тремя операциями. Ожидается 9 чтений и 6 записей в каждом запуске; проверка завершилась успешно.')
p('При проверке исходного проекта уточнён единый срок ожидания входа читателя: время, затраченное на Mutex, вычитается из оставшегося времени ожидания Semaphore. По истечении срока опыта новая операция не начинается. В CSV добавлены параметры конфигурации, в журнал — номер ресурса. Добавлено ожидание потоков при исключении во время их создания.')
newpage()
heading('11 МЕТОДИКА ЭКСПЕРИМЕНТОВ')
p('Сборка выполнена в Windows x64 компилятором MinGW-w64 GCC 15.2.0: g++ -std=c++20 -O2 -Wall -Wextra -pedantic src/main.cpp -o build/lab4.exe. Измеряется время steady_clock от создания состояния опыта до завершения потоков и закрытия объектов.')
p('Число читателей изменялось от 3 до 8 с шагом 1; число писателей равно 2. В стандартном режиме каждый участник выполняет 60 операций, в индивидуальном — 685. Базовые seed равны 42 и 13125; при каждом повторе seed увеличивается на единицу.')
p('Базовые задержки чтения, записи и паузы читателя равны 1 мс; случайная добавка равномерна от 0 до 1 мс. Тайм-аут ожидания равен 30000 мс, срок опыта — 60000 мс. Срок ограничивает начало и ожидание операций; завершение уже начатой операции и очистка могут увеличить фактическую длительность опыта.')
p('Команда воспроизведения: build/lab4.exe --mode both --student-id 125 --trials 3 --output-dir data/verified. Подробный журнал отключён для уменьшения влияния вывода на время. Для проверки состояний используется --verbose.')
p('Сохраняются время опыта, число операций, среднее и максимальное ожидание писателя, число тайм-аутов и нарушений, пропускная способность. Ожидание измеряется от запроса до успешного входа. Среднее рассчитывается только по успешным захватам; ожидания, закончившиеся тайм-аутом, в него не входят.')
p('Опыты выполнялись на одном компьютере в обычной рабочей среде. Seed воспроизводит последовательности задержек, но не порядок планирования потоков. Полученные времена могут изменяться при повторении; фоновая нагрузка и точность Sleep влияют на результат.')
newpage()
heading('12 ЭКСПЕРИМЕНТАЛЬНЫЕ РЕЗУЛЬТАТЫ')
for mode, title, num in [('standard','Стандартная нагрузка',2),('individual','Индивидуальная нагрузка',4)]:
    if mode == 'individual': newpage(); heading('12 ЭКСПЕРИМЕНТАЛЬНЫЕ РЕЗУЛЬТАТЫ', toc=False)
    p(f'Таблица {num} — {title}: время выполнения, мс', size=12)
    groups = [[r for r in data[mode] if int(r['reader_count']) == n] for n in range(3,9)]
    table(['Читатели','Запуск 1','Запуск 2','Запуск 3','Среднее'],
          [[str(n)]+[f"{float(r['elapsed_ms']):.2f}" for r in rows]+[f"{mean(float(r['elapsed_ms']) for r in rows):.2f}"] for n,rows in zip(range(3,9),groups)])
    p(f'Таблица {num+1} — {title}: профильные показатели', size=12)
    table(['Читатели','Чтения / записи¹','Среднее ожидание, мс²','Максимум, мс³','Операций/с²'],
          [[n, f"{rows[0]['successful_reads']} / {rows[0]['successful_writes']}",
            f"{mean(float(r['average_writer_wait_ms']) for r in rows):.3f}",
            f"{max(float(r['maximum_writer_wait_ms']) for r in rows):.3f}",
            f"{mean(float(r['throughput_ops_per_second']) for r in rows):.2f}"] for n,rows in zip(range(3,9),groups)])
    p('¹ В каждом из трёх запусков. ² Среднее трёх запусков. ³ Наибольшее единичное ожидание среди трёх запусков.', size=11)
    p('Во всех запусках тайм-ауты и нарушения инвариантов равны нулю. Необработанные результаты и параметры сохранены в data/verified/'+mode+'.csv.')
newpage()
heading('13 ГРАФИКИ И АНАЛИЗ РЕЗУЛЬТАТОВ')
fig('elapsed.png','Рисунок 2 — Время выполнения при изменении числа читателей')
def avg(mode,n,key):
    return mean(float(r[key]) for r in data[mode] if int(r['reader_count'])==n)
for mode,label in [('standard','стандартной'),('individual','индивидуальной')]:
    a,b=avg(mode,3,'elapsed_ms'),avg(mode,8,'elapsed_ms')
    p(f'При {label} нагрузке среднее время для 3 читателей составило {a:.2f} мс, для 8 читателей — {b:.2f} мс. Отношение времён равно {b/a:.3f}. Количество чтений при этом увеличилось в 8/3 раза, а количество записей осталось неизменным.')
p('Время не обязано возрастать пропорционально общему числу операций: чтения выполняются совместно, записи сериализованы. На результат влияют перекрытие чтений, переключения потоков и паузы между обращениями. Графики отражают средние трёх запусков, а не гарантированную зависимость.')
newpage()
heading('13 ГРАФИКИ И АНАЛИЗ РЕЗУЛЬТАТОВ', toc=False)
fig('wait.png','Рисунок 3 — Среднее ожидание писателей')
for mode,label in [('standard','стандартной'),('individual','индивидуальной')]:
    a,b=avg(mode,3,'average_writer_wait_ms'),avg(mode,8,'average_writer_wait_ms')
    p(f'При {label} нагрузке среднее ожидание писателя изменилось с {a:.3f} до {b:.3f} мс при переходе от 3 к 8 читателям. Изменение составляет {b-a:+.3f} мс.')
p('Ожидалось увеличение риска длительного ожидания писателей при росте группы читателей. В конечных опытах со встроенными паузами ресурс регулярно освобождается, поэтому зависимость может быть немонотонной и слабее ожидаемой. Среднее скрывает редкие длительные ожидания; для оценки риска дополнительно приведён максимум в профильных таблицах.')
p('Нулевое число тайм-аутов показывает завершение данной нагрузки, но не отсутствие голодания в общем случае. Для усиления читательского потока при защите можно уменьшить --reader-think-ms до 0 и повторить три запуска; такие результаты следует анализировать отдельно.')
newpage()
heading('ЗАКЛЮЧЕНИЕ', True)
p('Реализована модель варианта 9 с приоритетом читателей. Mutex защищает счётчик группы, бинарный Semaphore обеспечивает совместное чтение и исключительную запись. Новые читатели присоединяются к активной группе независимо от наличия ожидающих писателей.')
p('Выполнены стандартный и индивидуальный эксперименты с STUDENT_ID = 125: по шесть конфигураций и три запуска, всего 36 опытов. Все ожидаемые операции выполнены; тайм-ауты и нарушения проверяемых инвариантов не зарегистрированы. Построены графики времени выполнения и среднего ожидания писателя.')
p('Эксперимент показал, что рост количества читателей не приводит к обязательному пропорциональному росту времени опыта: чтения перекрываются, а доступ писателей определяется моментами опустошения группы. Конкретные времена зависят от планировщика и задержек. Приоритет читателей сохраняет теоретическую возможность голодания писателей, поэтому для требований справедливости нужен другой алгоритм.')
newpage()
heading('СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ', True)
sources = [
'1. Дипломные проекты (работы). Общие требования : СТП 01–2024. — Минск : БГУИР, 2024. — Разделы 2, 3. Электронная копия: https://ru.scribd.com/document/910898315 (дата обращения: 15.11.2026).',
'2. Microsoft. Mutex Objects [Электронный ресурс]. — URL: https://learn.microsoft.com/en-us/windows/win32/sync/mutex-objects (дата обращения: 15.11.2026).',
'3. Microsoft. Semaphore Objects [Электронный ресурс]. — URL: https://learn.microsoft.com/en-us/windows/win32/sync/semaphore-objects (дата обращения: 15.11.2026).',
'4. Microsoft. Using Semaphore Objects [Электронный ресурс]. — URL: https://learn.microsoft.com/en-us/windows/win32/sync/using-semaphore-objects (дата обращения: 15.11.2026).',
'5. Лабораторная работа 4. Взаимодействие процессов (потоков): взаимное исключение и синхронизация. — Электронные материалы СЭО, ОСиСП. Часть 1. — Текст задания, предоставленный студенткой.'
]
for s in sources: p(s, size=12)
newpage()
heading('ПРИЛОЖЕНИЕ Б', True)
heading('Сведения о репозитории Git', True, False)
p('Адрес репозитория: ____________________________________')
p('Ветка: ______________________________________________')
p('Хеш итогового коммита: _______________________________')
p('Доступ преподавателю: ________________________________')
p('Состав материалов: src/main.cpp — программа; tests/smoke.ps1 — короткая проверка; data/verified/*.csv — измерения; scripts/plot_report.py — построение рисунков; scripts/make_report.py — сборка отчёта; diagrams/readers-writers.mmd — описание последовательности; report — отчёт и рисунки.')
p('История разработки предоставляется средствами Git. Контрольные версии проектирования, реализации, синхронизации и экспериментальной части должны соответствовать фактической последовательности выполненных работ.')

def listing_appendix(letter, title, files):
    first = True
    for path in files:
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        wrapped=[]
        for line in lines:
            wrapped.extend(textwrap.wrap(line.expandtabs(4), width=112, replace_whitespace=False,
                          drop_whitespace=False, subsequent_indent='    ') or [''])
        for start in range(0,len(wrapped),62):
            newpage()
            if first:
                heading('ПРИЛОЖЕНИЕ '+letter, True)
                heading(title, True, False)
                first=False
            else:
                heading('Продолжение приложения '+letter, True, False)
            p(str(path.relative_to(ROOT)) + f' — фрагмент {start//62+1}', size=11)
            code('\n'.join(wrapped[start:start+62]))

listing_appendix('В','Листинг кода генерации графических материалов',
                 [ROOT/'scripts/plot_report.py',ROOT/'diagrams/readers-writers.mmd'])
listing_appendix('Г','Листинг кода исходного задания',[ROOT/'src/main.cpp'])

# Populate a static TOC using the explicit, verified page layout.
anchor = toc_anchor._p
for text, number in contents:
    par = OxmlElement('w:p')
    anchor.addnext(par)
    from docx.text.paragraph import Paragraph
    entry = Paragraph(par, toc_anchor._parent)
    entry.paragraph_format.first_line_indent = Cm(0)
    entry.paragraph_format.line_spacing = Pt(18)
    tabs=entry.paragraph_format.tab_stops
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
    tabs.add_tab_stop(Cm(16.4), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
    run=entry.add_run(text.capitalize()+'\t'+str(number))
    run.font.size=Pt(11)
    anchor=par
doc.core_properties.title='Лабораторная работа 4 Вариант 9 Приоритет читателей'
doc.core_properties.author='Пушечникова Карина Валерьевна'
doc.core_properties.subject='ОСиСП'
target=OUT/'Отчет_ЛР4_Вариант_9_Пушечникова.docx'
doc.save(target)
print(target)
print('Planned pages:',page)
