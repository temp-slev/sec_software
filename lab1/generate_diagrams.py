"""Генератор диаграмм лабораторной работы №1.

Строит три диаграммы в двух форматах: .excalidraw (открывается на excalidraw.com)
и .svg/.png (для вставки в отчёт). Запуск: python generate_diagrams.py
"""
import json
import math
import random
from xml.sax.saxutils import escape

BLUE, GREEN, ORANGE, PURPLE, GRAY, BLACK = "#1971c2", "#2f9e44", "#e8590c", "#9c36b5", "#868e96", "#1e1e1e"
FILL = {"int": "#d0ebff", "ext": "#b2f2bb", "hyb": "#ffd8a8", "db": "#fff3bf", "reg": "#e5dbff",
        "none": "transparent", "zone": "#f8f9fa", "actor": "#ffec99"}
FS = 16


class Diagram:
    def __init__(self, name, w, h):
        self.name, self.w, self.h = name, w, h
        self.items = []
        self.seed = 1

    # ---------- примитивы ----------
    def box(self, x, y, w, h, text="", fill="int", stroke=BLACK, kind="rectangle", dashed=False,
            fs=FS, top=False, sw=2):
        b = dict(t="shape", kind=kind, x=x, y=y, w=w, h=h, text=text, fill=FILL.get(fill, fill),
                 stroke=stroke, dashed=dashed, fs=fs, top=top, sw=sw)
        self.items.append(b)
        return b

    def text(self, x, y, text, color=BLACK, fs=FS, anchor="start"):
        self.items.append(dict(t="text", x=x, y=y, text=text, color=color, fs=fs, anchor=anchor))

    def arrow(self, p, q, label="", color=BLUE, dashed=False, both=False, label_dx=0, label_dy=-8,
              fs=13, plain=False):
        self.items.append(dict(t="arrow", p=p, q=q, label=label, color=color, dashed=dashed,
                               both=both, dx=label_dx, dy=label_dy, fs=fs, plain=plain))

    # ---------- геометрия ----------
    @staticmethod
    def center(b):
        return b["x"] + b["w"] / 2, b["y"] + b["h"] / 2

    @staticmethod
    def edge(b, toward):
        cx, cy = Diagram.center(b)
        dx, dy = toward[0] - cx, toward[1] - cy
        if dx == 0 and dy == 0:
            return cx, cy
        sx = (b["w"] / 2) / abs(dx) if dx else float("inf")
        sy = (b["h"] / 2) / abs(dy) if dy else float("inf")
        s = min(sx, sy)
        return cx + dx * s, cy + dy * s

    def link(self, a, b, fwd="", back="", color=BLUE, dashed=False, off=11, fs=13):
        """Пара стрелок между блоками a и b: a->b (fwd) и b->a (back)."""
        ca, cb = self.center(a), self.center(b)
        dx, dy = cb[0] - ca[0], cb[1] - ca[1]
        n = math.hypot(dx, dy)
        nx, ny = -dy / n, dx / n
        for sign, lab, src, dst in ((1, fwd, a, b), (-1, back, b, a)):
            if not lab and sign == -1 and not back:
                continue
            o = off * sign if back else 0
            sc, dc = self.center(src), self.center(dst)
            sc2, dc2 = (sc[0] + nx * o, sc[1] + ny * o), (dc[0] + nx * o, dc[1] + ny * o)
            if sign == -1:  # для обратной стрелки сторона зеркальна
                sc2, dc2 = (sc[0] + nx * o, sc[1] + ny * o), (dc[0] + nx * o, dc[1] + ny * o)
            p = self.edge(src, dc2)
            q = self.edge(dst, sc2)
            p = (p[0] + nx * o, p[1] + ny * o)
            q = (q[0] + nx * o, q[1] + ny * o)
            half_w = len(lab) * fs * 0.3
            ox = nx * sign * (14 + half_w * abs(nx)) if back else 0
            oy = ny * 14 * sign if back else -10
            self.items.append(dict(t="arrow", p=p, q=q, label=lab, color=color, dashed=dashed,
                                   both=False, dx=ox, dy=oy, fs=fs))

    # ---------- SVG ----------
    def svg(self):
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
             f'viewBox="0 0 {self.w} {self.h}" font-family="Helvetica, Arial, sans-serif">',
             '<rect width="100%" height="100%" fill="#ffffff"/>', '<defs>']
        for c in (BLUE, GREEN, ORANGE, PURPLE, GRAY, BLACK):
            o.append(f'<marker id="m{c[1:]}" markerWidth="10" markerHeight="10" refX="9" refY="5" '
                     f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
        o.append("</defs>")
        for it in self.items:
            if it["t"] == "shape":
                dash = ' stroke-dasharray="9 6"' if it["dashed"] else ""
                if it["kind"] == "ellipse":
                    o.append(f'<ellipse cx="{it["x"] + it["w"] / 2}" cy="{it["y"] + it["h"] / 2}" '
                             f'rx="{it["w"] / 2}" ry="{it["h"] / 2}" fill="{it["fill"]}" '
                             f'stroke="{it["stroke"]}" stroke-width="{it["sw"]}"{dash}/>')
                else:
                    o.append(f'<rect x="{it["x"]}" y="{it["y"]}" width="{it["w"]}" height="{it["h"]}" '
                             f'rx="8" fill="{it["fill"]}" stroke="{it["stroke"]}" '
                             f'stroke-width="{it["sw"]}"{dash}/>')
                lines = it["text"].split("\n") if it["text"] else []
                lh = it["fs"] * 1.25
                if it["top"]:
                    y0 = it["y"] + 8 + it["fs"]
                else:
                    y0 = it["y"] + it["h"] / 2 - (len(lines) - 1) * lh / 2 + it["fs"] * 0.35
                for i, ln in enumerate(lines):
                    o.append(f'<text x="{it["x"] + it["w"] / 2}" y="{y0 + i * lh}" text-anchor="middle" '
                             f'font-size="{it["fs"]}" fill="{BLACK}">{escape(ln)}</text>')
            elif it["t"] == "text":
                for i, ln in enumerate(it["text"].split("\n")):
                    o.append(f'<text x="{it["x"]}" y="{it["y"] + it["fs"] + i * it["fs"] * 1.25}" '
                             f'font-size="{it["fs"]}" fill="{it["color"]}" '
                             f'text-anchor="{it["anchor"]}">{escape(ln)}</text>')
            else:
                dash = ' stroke-dasharray="8 6"' if it["dashed"] else ""
                cid = it["color"][1:]
                ms = f' marker-start="url(#m{cid})"' if it["both"] else ""
                me = "" if it.get("plain") else f' marker-end="url(#m{cid})"'
                o.append(f'<line x1="{it["p"][0]:.1f}" y1="{it["p"][1]:.1f}" x2="{it["q"][0]:.1f}" '
                         f'y2="{it["q"][1]:.1f}" stroke="{it["color"]}" stroke-width="2"{dash}'
                         f'{me}{ms}/>')
                if it["label"]:
                    mx = (it["p"][0] + it["q"][0]) / 2 + it["dx"]
                    my = (it["p"][1] + it["q"][1]) / 2 + it["dy"]
                    for i, ln in enumerate(it["label"].split("\n")):
                        yy = my + i * it["fs"] * 1.2
                        o.append(f'<text x="{mx:.1f}" y="{yy:.1f}" text-anchor="middle" font-size="{it["fs"]}" '
                                 f'fill="#ffffff" stroke="#ffffff" stroke-width="5" font-weight="bold">'
                                 f'{escape(ln)}</text>')
                        o.append(f'<text x="{mx:.1f}" y="{yy:.1f}" text-anchor="middle" font-size="{it["fs"]}" '
                                 f'fill="{it["color"]}" font-weight="bold">{escape(ln)}</text>')
        o.append("</svg>")
        return "\n".join(o)

    # ---------- Excalidraw ----------
    def excalidraw(self):
        els = []
        rnd = random.Random(7)

        def base(typ, x, y, w, h, stroke, bg, dashed=False, sw=2):
            return {"id": f"e{len(els)}", "type": typ, "x": x, "y": y, "width": w, "height": h,
                    "angle": 0, "strokeColor": stroke, "backgroundColor": bg, "fillStyle": "solid",
                    "strokeWidth": sw, "strokeStyle": "dashed" if dashed else "solid", "roughness": 0,
                    "opacity": 100, "groupIds": [], "frameId": None,
                    "roundness": {"type": 3} if typ == "rectangle" else None,
                    "seed": rnd.randint(1, 2 ** 31), "version": 1, "versionNonce": rnd.randint(1, 2 ** 31),
                    "isDeleted": False, "boundElements": [], "updated": 1, "link": None, "locked": False}

        def txt(x, y, text, color, fs, container=None, align="left", valign="top", w=None):
            lines = text.split("\n")
            tw = w or max(len(l) for l in lines) * fs * 0.58
            th = len(lines) * fs * 1.25
            e = base("text", x, y, tw, th, color, "transparent")
            e.update({"text": text, "fontSize": fs, "fontFamily": 2, "textAlign": align,
                      "verticalAlign": valign, "containerId": container, "originalText": text,
                      "autoResize": True, "lineHeight": 1.25, "roundness": None})
            return e

        for it in self.items:
            if it["t"] == "shape":
                typ = "ellipse" if it["kind"] == "ellipse" else "rectangle"
                s = base(typ, it["x"], it["y"], it["w"], it["h"], it["stroke"], it["fill"],
                         it["dashed"], it["sw"])
                els.append(s)
                if it["text"]:
                    lines = it["text"].split("\n")
                    tw = max(len(l) for l in lines) * it["fs"] * 0.58
                    th = len(lines) * it["fs"] * 1.25
                    if it["top"]:
                        t = txt(it["x"] + (it["w"] - tw) / 2, it["y"] + 8, it["text"], BLACK, it["fs"],
                                None, "center")
                    else:
                        t = txt(it["x"] + (it["w"] - tw) / 2, it["y"] + (it["h"] - th) / 2, it["text"],
                                BLACK, it["fs"], s["id"], "center", "middle")
                        s["boundElements"].append({"id": t["id"], "type": "text"})
                    els.append(t)
            elif it["t"] == "text":
                els.append(txt(it["x"], it["y"], it["text"], it["color"], it["fs"]))
            else:
                p, q = it["p"], it["q"]
                a = base("arrow", p[0], p[1], q[0] - p[0], q[1] - p[1], it["color"], "transparent",
                         it["dashed"])
                a.update({"points": [[0, 0], [q[0] - p[0], q[1] - p[1]]], "lastCommittedPoint": None,
                          "startBinding": None, "endBinding": None, "startArrowhead":
                          "arrow" if it["both"] else None,
                          "endArrowhead": None if it.get("plain") else "arrow", "roundness": None})
                els.append(a)
                if it["label"]:
                    mx = (p[0] + q[0]) / 2 + it["dx"]
                    my = (p[1] + q[1]) / 2 + it["dy"]
                    w = len(it["label"]) * it["fs"] * 0.58
                    els.append(txt(mx - w / 2, my - it["fs"] * 0.9, it["label"], it["color"], it["fs"]))
        return {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
                "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}

    def save(self, folder):
        with open(f"{folder}/{self.name}.excalidraw", "w", encoding="utf-8") as f:
            json.dump(self.excalidraw(), f, ensure_ascii=False, indent=1)
        with open(f"{folder}/{self.name}.svg", "w", encoding="utf-8") as f:
            f.write(self.svg())
        import cairosvg
        cairosvg.svg2png(bytestring=self.svg().encode(), write_to=f"{folder}/{self.name}.png",
                         output_width=self.w * 1.5)


def legend(d, x, y, rows):
    d.box(x, y, 330, 30 + len(rows) * 28, "Легенда", "none", GRAY, top=True, fs=15)
    for i, (color, label, kind) in enumerate(rows):
        yy = y + 52 + i * 28
        if kind == "line":
            d.arrow((x + 15, yy), (x + 70, yy), "", color, plain=(color == BLACK))
        else:
            d.box(x + 15, yy - 10, 55, 20, "", kind, BLACK, sw=1)
        d.text(x + 82, yy - 10, label, BLACK, 14)


# =====================================================================
# 1. Use Case
# =====================================================================
def use_case():
    d = Diagram("1_use_case", 1700, 1160)
    d.box(280, 20, 1000, 1110, "Система онлайн-обучения EduCloud", "none", BLACK, top=True, fs=20)

    def actor(y, name):
        return d.box(40, y, 180, 70, name, "actor")

    st, te, ad, tx = actor(165, "Студент"), actor(560, "Преподаватель"), actor(800, "Администратор"), \
        actor(1000, "Технический\nспециалист")

    def uc(x, y, name, w=230, fill="int"):
        return d.box(x, y, w, 64, name, fill, kind="ellipse")

    auth = d.box(300, 420, 200, 70, "Авторизоваться", "reg", kind="ellipse")
    s1 = uc(620, 70, "Просмотреть курсы")
    s2 = uc(620, 160, "Оплатить курс")
    s3 = uc(620, 250, "Скачать материалы")
    s4 = uc(620, 340, "Просмотреть\nархивные лекции")
    disc = uc(950, 300, "Применить скидку", 220, "reg")
    t1 = uc(620, 520, "Загрузить материал")
    t2 = uc(620, 610, "Обновить курс")
    t3 = uc(620, 700, "Просмотреть статистику")
    a1 = uc(620, 800, "Управлять пользователями")
    a2 = uc(620, 890, "Управлять платежами")
    x1 = uc(620, 980, "Мониторить состояние\nсервисов (логи, метрики)", 250)
    x2 = uc(620, 1060, "Перезапускать сервисы", 250)

    pay = d.box(1340, 160, 220, 64, "Платёжный шлюз\n(Stripe)", "ext")
    mail = d.box(1340, 610, 220, 64, "Почтовый сервер\n(SendGrid)", "ext")

    def conn(a, b):
        pa, pb = d.center(a), d.center(b)
        d.arrow(d.edge(a, pb), d.edge(b, pa), "", BLACK, plain=True)

    for s_ in (s1, s2, s3, s4, auth):
        conn(st, s_)
    for s_ in (t1, t2, t3, auth):
        conn(te, s_)
    for s_ in (a1, a2, auth):
        conn(ad, s_)
    for s_ in (x1, x2, auth):
        conn(tx, s_)

    def inc(a):
        pa, pb = d.center(a), d.center(auth)
        d.arrow(d.edge(a, pb), d.edge(auth, pa), "<<include>>", BLUE, True, label_dy=-6)

    for a_ in (s2, t1, a1, x1):
        inc(a_)
    pd, pa = d.center(disc), d.center(s2)
    d.arrow(d.edge(disc, pa), d.edge(s2, pd), "<<extend>>", ORANGE, True, label_dx=70, label_dy=-6)
    d.arrow(d.edge(s2, d.center(pay)), d.edge(pay, d.center(s2)), "оплата", GREEN, False, True,
            label_dy=-8)
    d.arrow(d.edge(t2, d.center(mail)), d.edge(mail, d.center(t2)), "уведомление", GREEN, False,
            True, label_dy=-8)
    legend(d, 1330, 800, [(BLACK, "Ассоциация актёр – вариант", "line"),
                          (BLUE, "<<include>>", "line"),
                          (ORANGE, "<<extend>>", "line"),
                          (GREEN, "Внешняя система", "line")])
    d.text(1330, 960, "«Авторизоваться» включается\n(<<include>>) во все остальные\nварианты использования;\n"
           "на схеме показано для\nпо одному варианту каждой роли.", GRAY, 14)
    return d


# =====================================================================
# 2. DFD
# =====================================================================
def dfd():
    d = Diagram("2_dfd", 1760, 1000)
    W, H = 200, 70
    web = d.box(30, 420, W, H, "Веб-клиент\n(React)", "actor")
    gw = d.box(380, 420, W, H, "API Gateway", "int")
    reg = d.box(380, 90, W, H, "Service Registry\n(Eureka / Consul)", "reg")
    auth = d.box(760, 90, W, H, "Auth Service", "int")
    course = d.box(760, 330, W, H, "Course Service", "int")
    pay = d.box(760, 520, W, H, "Payment Service", "int")
    noti = d.box(760, 740, W, H, "Notification Service", "int")
    redis = d.box(1150, 90, W, H, "Redis Cache", "db")
    pg = d.box(1150, 330, W, H, "PostgreSQL DB", "db")
    stripe = d.box(1150, 520, W, H, "Stripe API\n(внешняя система)", "ext")
    sg = d.box(1150, 740, W, H, "SendGrid API\n(внешняя система)", "ext")
    sftp = d.box(380, 740, W, H, "SFTP Server\n(локальный ДЦ)", "hyb")

    d.link(web, gw, "HTTP запросы (REST)", "Возвращает ответ (JSON)", BLUE)
    d.link(gw, auth, "Запрашивает аутентификацию", "Возвращает JWT", BLUE)
    d.link(auth, redis, "Сохраняет сессию", "Проверяет сессию", BLUE)
    d.link(gw, course, "Запрашивает материалы", "Возвращает уроки", BLUE)
    d.link(course, pg, "Читает и пишет курсы (CRUD)", "Возвращает данные", BLUE)
    d.link(gw, pay, "Передаёт запрос на оплату", "Возвращает статус оплаты", BLUE)
    d.link(pay, stripe, "Отправляет платёжное требование", "Подтверждает платёж", GREEN)
    d.link(pay, noti, "Отправляет команду\nна уведомление", "", BLUE)
    d.link(noti, sg, "Отправляет письмо", "Возвращает статус", GREEN)
    d.link(gw, sftp, "Запрашивает архивные файлы", "Передаёт файлы", ORANGE)
    d.link(auth, reg, "Регистрирует адрес", "", PURPLE)
    d.link(course, reg, "Регистрирует адрес", "", PURPLE)
    d.link(gw, reg, "Запрашивает адреса", "Возвращает адреса", PURPLE)
    legend(d, 1400, 840, [(BLUE, "Внутренний трафик", "line"), (GREEN, "Внешние системы", "line"),
                          (ORANGE, "Гибридный доступ (VPN)", "line"),
                          (PURPLE, "Service Discovery", "line")])
    return d


# =====================================================================
# 3. Deployment
# =====================================================================
def deployment():
    d = Diagram("3_deployment", 1900, 1060)
    d.box(30, 30, 270, 310, "Клиентские устройства", "zone", GRAY, top=True, fs=17)
    web = d.box(60, 90, 210, 80, "Браузер\n(Web Client, React)", "actor")
    mob = d.box(60, 220, 210, 80, "Мобильное устройство\n(React Native)", "actor")
    net = d.box(340, 80, 150, 70, "Интернет", "none", GRAY, kind="ellipse")
    d.box(540, 30, 940, 990, "AWS (публичное облако) — кластер Kubernetes (k8s)", "none", BLUE,
          top=True, fs=18, sw=3)
    lb = d.box(850, 80, 320, 70, "Load Balancer\n(Ingress, HTTPS 443)", "int")
    d.box(570, 230, 440, 260, "Availability Zone 1", "zone", BLUE, top=True, dashed=True)
    d.box(1010, 230, 440, 260, "Availability Zone 2", "zone", BLUE, top=True, dashed=True)
    d.box(590, 290, 190, 70, "Pod Auth Service\n(реплика 1)", "int")
    d.box(800, 290, 190, 70, "Pod Course Service\n(реплика 1)", "int")
    d.box(1030, 290, 190, 70, "Pod Auth Service\n(реплика 2)", "int")
    d.box(1240, 290, 190, 70, "Pod Course Service\n(реплика 2)", "int")
    d.box(590, 390, 190, 70, "Pod Payment Service", "int")
    d.box(1240, 390, 190, 70, "Pod Notification\nService", "int")
    d.box(580, 640, 580, 170, "Слой данных (StatefulSet)", "zone", BLUE, top=True, dashed=True)
    d.box(600, 700, 250, 80, "PostgreSQL\n(порт 5432)", "db")
    d.box(880, 700, 250, 80, "Redis\n(порт 6379)", "db")
    d.box(1220, 640, 230, 80, "VPN Gateway", "hyb")
    d.text(560, 960, "Kubernetes (k8s): поды развёрнуты Deployment-ами, базы данных — StatefulSet", GRAY, 14)
    d.box(1590, 300, 280, 330, "Локальный дата-центр (On-Premise)", "zone", ORANGE, top=True, fs=16)
    fw = d.box(1620, 370, 220, 70, "Firewall", "hyb")
    sftp = d.box(1620, 500, 220, 80, "SFTP-сервер\n(архив лекций)", "hyb")

    d.arrow((270, 130), (340, 105), "", BLUE)
    d.arrow((270, 260), (380, 150), "", BLUE)
    d.arrow((490, 115), (850, 115), "HTTPS (443)", BLUE, label_dy=-10)
    d.arrow((950, 150), (790, 230), "REST/HTTP :8080", BLUE, label_dx=-60, label_dy=-6)
    d.arrow((1070, 150), (1230, 230), "REST/HTTP :8080", BLUE, label_dx=60, label_dy=-6)
    d.arrow((750, 490), (750, 640), "TCP 5432, 6379", BLUE, label_dx=-65)
    d.arrow((1150, 490), (950, 640), "TCP 5432, 6379", BLUE, label_dx=75, label_dy=-20)
    d.arrow((1335, 490), (1335, 640), "SFTP (22)", ORANGE, label_dx=50)
    d.arrow((1450, 660), (1620, 420), "VPN-туннель\nSFTP, порт 22", ORANGE, True, True,
            label_dx=-20, label_dy=-30)
    d.arrow((1730, 440), (1730, 500), "SFTP :22", ORANGE, label_dx=45)
    legend(d, 40, 740, [(BLUE, "Облако AWS / внутренний трафик", "line"),
                        (ORANGE, "Гибридный канал (VPN)", "line"),
                        ("#d0ebff", "Контейнеры (поды)", "int"), ("#fff3bf", "Хранилища данных", "db"),
                        ("#ffd8a8", "Локальная инфраструктура", "hyb")])
    return d


if __name__ == "__main__":
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "diagrams")
    os.makedirs(out, exist_ok=True)
    for build in (use_case, dfd, deployment):
        build().save(out)
    print("готово:", sorted(os.listdir(out)))
