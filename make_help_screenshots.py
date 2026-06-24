"""Скриншоты для инструкции — полная анонимизация."""
import sys

sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

BASE  = "http://127.0.0.1:8765"
PHONE = "+79997303914"
PASS  = "Screen2026!"
OUT   = "static/img/help"

# ── Полная анонимизация ──────────────────────────────────────────────────────
ANON_JS = """() => {
    const SURNAMES = ['Митько','Ловчиков','Хачатурова','Косило','Студеникин',
                      'Шевченко','Валеев','Месмер','Гаврин','Комаров'];
    const NAMES    = ['Роберт','Александр','Жанна','Сергей','Наталья',
                      'Борис','Денис','Игорь','Алексей'];

    // 1. Скрываем все адреса (элементы с bi-geo-alt)
    document.querySelectorAll('.bi-geo-alt, [class*="address"], .project-address')
        .forEach(el => {
            const p = el.closest('small, span, div, p, td');
            if (p) p.style.visibility = 'hidden';
        });

    // 2. Ходим по текстовым узлам
    function walkText(node) {
        if (node.nodeType === 3) {
            let t = node.textContent;
            // Убираем цифры после ТК (номер объекта)
            t = t.replace(/ТК\\s+\\d+/g, 'ТК');
            // Убираем адресные строки
            if (/\\bул\\.?\\s|\\bпр\\.?\\s|проспект|шоссе|литер|поселок|поселение|район|\\bд\\.\\s*\\d/i.test(t)) {
                node.textContent = '';
                return;
            }
            // Заменяем фамилии
            SURNAMES.forEach(s => { t = t.replace(new RegExp(s + '(\\\\s+\\\\S+)?', 'g'), 'Менеджер'); });
            // Заменяем одиночные имена
            NAMES.forEach(n => { t = t.replace(new RegExp('\\\\b' + n + '\\\\b', 'g'), 'Проекта'); });
            node.textContent = t;
        } else if (node.nodeName !== 'SCRIPT' && node.nodeName !== 'STYLE') {
            node.childNodes.forEach(walkText);
        }
    }
    walkText(document.body);

    // 3. Блюрим телефоны и email
    document.querySelectorAll('[href^="tel:"], [href^="mailto:"], .phone, .email')
        .forEach(el => el.style.filter = 'blur(6px)');

    // 4. Колонка "ТК №" в таблице проектов — заменяем числа на "—"
    // Находим заголовок "ТК №", определяем индекс колонки
    document.querySelectorAll('table thead th').forEach((th, idx) => {
        if (th.textContent.includes('ТК') && th.textContent.includes('№')) {
            document.querySelectorAll('table tbody tr').forEach(tr => {
                const td = tr.querySelectorAll('td')[idx];
                if (td) td.textContent = '—';
            });
        }
    });

    // 5. В карточке проекта: ТК № value (dd после dt с "ТК")
    document.querySelectorAll('dt, .detail-label, td').forEach(el => {
        if (el.textContent.trim() === 'ТК №') {
            const val = el.nextElementSibling || el.closest('tr')?.querySelector('td:last-child');
            if (val) val.textContent = '—';
        }
    });

    // 6. В заголовке страницы убираем числа: "ТК 3566 Санкт-Петербург" -> "ТК Санкт-Петербург"
    document.querySelectorAll('h1, h2, .page-title, .breadcrumb-item, nav .text-truncate')
        .forEach(el => {
            el.childNodes.forEach(n => {
                if (n.nodeType === 3) n.textContent = n.textContent.replace(/ТК\\s+\\d+/g, 'ТК');
            });
        });
}"""

# ── Рейтинг менеджеров в executive ──────────────────────────────────────────
EXEC_ANON_JS = """() => {
    let i = 1;
    document.querySelectorAll('table tbody tr').forEach(tr => {
        const cells = tr.querySelectorAll('td');
        if (cells.length >= 2) {
            const nameCell = cells[1];
            const img = nameCell.querySelector('img');
            nameCell.innerHTML = (img ? img.outerHTML + ' ' : '') + 'Менеджер ' + i;
        }
        i++;
    });
}"""

def shot(page, name, wait=1500):
    page.wait_for_timeout(wait)
    page.evaluate(ANON_JS)
    page.wait_for_timeout(300)
    page.screenshot(path=f"{OUT}/{name}.png", full_page=False)
    print(f"  ✓ {name}.png")


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-proxy-server"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="ru-RU")
        page = ctx.new_page()

        # 01 — Логин (чистая страница — ДО входа)
        print("Скриншот логина...")
        page.goto(f"{BASE}/login")
        page.wait_for_timeout(1200)
        page.screenshot(path=f"{OUT}/01_login.png", full_page=False)
        print("  ✓ 01_login.png")

        # Логин
        print("Логин...")
        page.fill("input[name=phone]", PHONE)
        page.click("button[type=submit]")
        page.wait_for_selector("input[name=password]", timeout=10000)
        page.fill("input[name=password]", PASS)
        page.click("button[type=submit]")
        page.wait_for_url(f"{BASE}/", timeout=10000)
        print("  вошли")

        # 02 — Дашборд
        page.goto(f"{BASE}/")
        shot(page, "02_dashboard", 2000)

        # 03 — Реконструкции (убираем номера ТК и адреса)
        page.goto(f"{BASE}/reconstruct")
        shot(page, "03_projects_reconstruct", 2000)

        # 04 — Констракшн
        page.goto(f"{BASE}/construction")
        shot(page, "04_projects_construction", 2000)

        # 05 — Дедлайны (инжектируем данные Railway — 64 дедлайна)
        page.goto(f"{BASE}/deadlines")
        page.wait_for_timeout(2000)
        page.evaluate(ANON_JS)
        page.evaluate("""() => {
            // Обновляем счётчик дедлайнов проектов
            const badges = document.querySelectorAll('.data-card-header .badge');
            if (badges[0]) badges[0].textContent = '64';
            if (badges[1]) badges[1].textContent = '12';

            // Данные для инжекции (Railway-подобные, анонимизированные)
            const rows = [
                ['—','ТК Москва 1','Менеджер 1','Констракшн','Активный','15.06.2026','5 дней','dl-warn'],
                ['—','ТК Санкт-Петербург 3','Менеджер 3','Констракшн','Активный','17.06.2026','7 дней','dl-ok'],
                ['—','ТК Москва 5','Менеджер 2','Констракшн','Активный','20.06.2026','10 дней','dl-ok'],
                ['—','ТК Екатеринбург 2','Менеджер 5','Реконструкция','Активный','22.06.2026','12 дней','dl-ok'],
                ['—','ТК Новосибирск 1','Менеджер 4','Констракшн','Активный','25.06.2026','15 дней','dl-ok'],
                ['—','ТК Краснодар 2','Менеджер 6','Констракшн','Активный','28.06.2026','18 дней','dl-ok'],
                ['—','ТК Москва 8','Менеджер 1','Констракшн','Открыт','01.07.2026','21 дней','dl-ok'],
                ['—','ТК Ростов-на-Дону 1','Менеджер 7','Реконструкция','Активный','05.07.2026','25 дней','dl-ok'],
            ];

            // Удаляем empty-state если есть
            document.querySelectorAll('.empty-state').forEach(el => el.remove());

            // Находим первую data-card (дедлайны проектов)
            const card = document.querySelector('.data-card');
            if (!card) return;

            // Проверяем есть ли уже таблица, если нет — создаём
            let tbody = card.querySelector('tbody');
            if (!tbody) {
                const tableWrap = document.createElement('div');
                tableWrap.className = 'table-responsive';
                tableWrap.innerHTML = `<table class="table table-hover mb-0 align-middle">
                    <thead class="table-head">
                        <tr><th>ТК №</th><th>Название</th><th>Менеджер</th><th>Тип</th><th>Статус</th><th>Дата окончания</th><th>Осталось</th></tr>
                    </thead>
                    <tbody></tbody></table>`;
                card.appendChild(tableWrap);
                tbody = tableWrap.querySelector('tbody');
            }

            tbody.innerHTML = '';
            rows.forEach(([tk, name, mgr, type, status, date, left, cls]) => {
                const statusBadge = status === 'Открыт'
                    ? '<span class="badge bg-success"><i class="bi bi-check-lg me-1"></i>Открыт</span>'
                    : '<span class="badge bg-success">Активный</span>';
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="text-muted small">${tk}</td>
                    <td><span class="fw-semibold">${name}</span></td>
                    <td>${mgr}</td>
                    <td><span class="badge bg-light text-dark">${type}</span></td>
                    <td>${statusBadge}</td>
                    <td class="fw-semibold">${date}</td>
                    <td><span class="dl-badge ${cls}">${left}</span></td>`;
                tbody.appendChild(tr);
            });
        }""")
        page.wait_for_timeout(300)
        page.screenshot(path=f"{OUT}/05_deadlines.png", full_page=False)
        print("  ✓ 05_deadlines.png")

        # 06 — Задачи (убираем имена)
        page.goto(f"{BASE}/tasks")
        shot(page, "06_tasks", 1500)

        # 07 — SMR (убираем ТК-номера, адреса, имена)
        page.goto(f"{BASE}/smr")
        shot(page, "07_smr", 1500)

        # 08 — ВПК
        page.goto(f"{BASE}/vpk")
        shot(page, "08_vpk", 1500)

        # 09 — Менеджеры (все имена)
        page.goto(f"{BASE}/managers")
        page.wait_for_timeout(1500)
        page.evaluate(ANON_JS)
        # Дополнительно: скрываем карточки менеджеров с именами
        page.add_style_tag(content="""
            .manager-card h5, .manager-card .name,
            .card-title, h5.fw-bold { filter: blur(6px) !important; }
            td:nth-child(3), td:nth-child(4) { filter: blur(6px) !important; }
        """)
        page.wait_for_timeout(300)
        page.screenshot(path=f"{OUT}/09_managers.png", full_page=False)
        print("  ✓ 09_managers.png")

        # 10 — AI
        page.goto(f"{BASE}/ai")
        shot(page, "10_ai", 1500)

        # 11 — Статистика
        page.goto(f"{BASE}/stats")
        shot(page, "11_stats", 2500)

        # 12 — Карточка проекта (убираем ТК-номер, адрес, имя менеджера)
        page.goto(f"{BASE}/reconstruct")
        page.wait_for_timeout(1200)
        first = page.locator("a[href*='/projects/']").first
        if first.count() > 0:
            href = first.get_attribute("href")
            page.goto(f"{BASE}{href}")
            shot(page, "12_project_detail", 2000)

        # 13 — Исполнительный дашборд
        page.goto(f"{BASE}/executive")
        page.wait_for_timeout(2000)
        page.evaluate(ANON_JS)
        page.evaluate(EXEC_ANON_JS)
        page.wait_for_timeout(300)
        page.screenshot(path=f"{OUT}/13_executive.png", full_page=False)
        print("  ✓ 13_executive.png")

        browser.close()
        print("\nГотово!")


if __name__ == "__main__":
    run()
