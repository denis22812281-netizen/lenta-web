"""
Нагрузочные тесты Lenta.PM — запуск через locust.

Быстрый старт:
    pip install locust
    locust -f tests/locustfile.py --host=https://lenta-web.up.railway.app

Локально с UI:
    locust -f tests/locustfile.py --host=http://localhost:8000
    # открыть http://localhost:8089

Headless (CI):
    locust -f tests/locustfile.py --host=http://localhost:8000 \
           --headless -u 20 -r 2 --run-time 60s \
           --csv=load_results
"""
import random
from locust import HttpUser, task, between


PHONE = "+79997303914"
PASSWORD = "test1234"

SEARCH_QUERIES = ["651", "Москва", "реконструкция", "ВПК", "открытие", "ТК"]
PROJECT_TYPES = ["Реконструкция", "Констракшн"]


class ManagerUser(HttpUser):
    """Имитирует менеджера: просматривает дашборд, проекты, дедлайны, ищет."""
    wait_time = between(1, 4)

    def on_start(self):
        self.client.post("/login/check-phone", data={"phone": PHONE})
        r = self.client.post(
            "/login/enter",
            data={"phone": PHONE, "password": PASSWORD},
            allow_redirects=True,
        )
        if r.status_code not in (200, 302):
            self.environment.runner.quit()

    @task(6)
    def dashboard(self):
        self.client.get("/", name="/ (dashboard)")

    @task(5)
    def projects_list(self):
        self.client.get("/projects", name="/projects")

    @task(4)
    def deadlines(self):
        self.client.get("/deadlines", name="/deadlines")

    @task(3)
    def search_text(self):
        q = random.choice(SEARCH_QUERIES)
        self.client.get(f"/search?q={q}", name="/search?q=*")

    @task(2)
    def search_with_filters(self):
        pt = random.choice(PROJECT_TYPES)
        self.client.get(f"/search?project_type={pt}", name="/search?project_type=*")

    @task(3)
    def api_deadlines_check(self):
        self.client.get("/api/deadlines/check", name="/api/deadlines/check")

    @task(2)
    def tasks_list(self):
        self.client.get("/tasks", name="/tasks")

    @task(1)
    def managers_page(self):
        self.client.get("/managers", name="/managers")

    @task(1)
    def vpk_list(self):
        self.client.get("/vpk", name="/vpk")


class AdminUser(HttpUser):
    """Имитирует администратора/руководителя: смотрит аналитику, аудит, admin."""
    wait_time = between(2, 6)
    weight = 1  # 1 admin на ~5 managers

    def on_start(self):
        self.client.post("/login/check-phone", data={"phone": PHONE})
        self.client.post(
            "/login/enter",
            data={"phone": PHONE, "password": PASSWORD},
            allow_redirects=True,
        )

    @task(4)
    def dashboard(self):
        self.client.get("/", name="/ (dashboard)")

    @task(3)
    def analytics(self):
        self.client.get("/analytics", name="/analytics")

    @task(2)
    def audit_log(self):
        self.client.get("/admin/audit", name="/admin/audit")

    @task(2)
    def deadlines(self):
        self.client.get("/deadlines", name="/deadlines")

    @task(1)
    def health_check(self):
        with self.client.get("/health", catch_response=True, name="/health") as r:
            if r.status_code == 200 and "ok" in r.text:
                r.success()
            else:
                r.failure(f"Health check failed: {r.status_code}")
