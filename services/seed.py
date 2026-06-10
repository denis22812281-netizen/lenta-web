import logging
import os

import models
from config import MANAGERS_SEED

logger = logging.getLogger(__name__)

MANAGER_DEFAULTS = {
    "Гаврин Игорь":       {"photo": "img/managers/gavrin.png",  "position": "Руководитель проектов",                  "email": "igor.gavrin@lenta.com"},
    "Комаров Алексей":    {"photo": "img/managers/komarov.png", "position": "Директор по эксплуатации и реконструкции"},
    "Месмер Денис":       {"photo": "img/raccoon_mesmer.jpg",   "position": "Менеджер проектов",                       "email": "denis.mesmer@lenta.com"},
    "Митько Роберт":      {"email": "robert.mitko@lenta.com"},
    "Ловчиков Александр": {"email": "alexander.lovchikov@lenta.com"},
    "Валеев Борис":       {"email": "boris.valeev@lenta.com"},
    "Студеникин Сергей":  {"email": "sergey.studenikin@lenta.com"},
    "Косило Сергей":      {"email": "sergey.kosilo@lenta.com"},
    "Хачатурова Жанна":   {"email": "zhanna.hachaturova@lenta.com"},
    "Шевченко Наталья":   {"email": "nataiya.shevchenko@lenta.com"},
}

_DEFAULT_POSITION = "Менеджер проектов"

_VPK1 = [
    "Документация на произведённые работы предоставлена в полном объёме в печатном виде, согласно технического задания.",
    "Температурный режим на объекте обеспечивается, согласно условий технического задания с учётом времени года.",
    "Подъёмное оборудование для перегрузки товара смонтировано и введено в эксплуатацию.",
    "Холодильное оборудование запущено и выведено в режим, функционирует без аварий более 24 часов.",
    "Строительство подъездных путей окончено, препятствий для подъезда к зоне разгрузки нет.",
    "Системы пожарной безопасности смонтированы, находятся в исправном и автоматическом режиме, готовы к проведению комплексных испытаний.",
    "Электроснабжение объекта осуществляется по постоянной схеме подключения.",
    "Объект обеспечен всеми необходимыми коммунальными ресурсами, согласно условий договора аренды.",
    "Периметр объекта замкнут, все двери/ворота установлены, исправны.",
    "Лотки и кабельные трассы системы видеонаблюдения смонтированы, проводятся пуско-наладочные работы.",
    "Объект обеспечен доступом в интернет (один канал), зона приёмки товара оборудована всем необходимым, препятствий для приёма товара нет.",
    "Основные строительно-монтажные работы закончены.",
    "Лотки и кабельные трассы системы охранной сигнализации смонтированы, проводятся пуско-наладочные работы.",
    "Охрана объекта обеспечена сотрудником ЧОП.",
    "ДДА с распределением зон эксплуатационной ответственности предоставлен.",
    "Согласование контейнерной площадки со стороны местной администрации предоставлено от АРДД.",
    "Укомплектованность собственным персоналом не ниже 60%.",
]

_VPK2 = [
    "Технологическое оборудование полностью смонтировано и запущено.",
    "Системы пожарной безопасности находятся в полностью исправном состоянии, все неисправности устранены или признаны инженером ПБ не значительными и не влияющими на общую работоспособность системы.",
    "Рекламная вывеска смонтирована, в ночное время светится.",
    "Всё кассовое оборудование запущено и исправно, все IT коммуникации смонтированы, исправны.",
    "Входная группа готова для открытия объекта, наружные работы и благоустройство завершены.",
    "Охранная сигнализация смонтирована, исправна.",
    "Система видеонаблюдения смонтирована, исправна.",
    "Уличное освещение объекта смонтировано, исправно.",
    "Маркетинговое оформление СМ полностью закончено.",
    "Строительство парковки для клиентов (при наличии) окончено, препятствий для размещения автомобилей нет.",
    "Укомплектованность собственным персоналом не ниже 70%.",
    "Объект обеспечен доступом в интернет (два канала передачи данных).",
    "В зоне кассовой линейки должен быть обеспечен устойчивый сигнал сотовой связи (мобильное приложение ЛЕНТА запускается, существует возможность оплаты по СБП с личного мобильного телефона покупателя).",
]


def seed_all(db):
    _seed_managers(db)
    _seed_users(db)
    _seed_vpk_criteria(db)


def _seed_managers(db):
    existing_names = {m.name for m in db.query(models.Manager).all()}
    for name, is_leader in MANAGERS_SEED:
        if name not in existing_names:
            db.add(models.Manager(name=name, is_leader=is_leader))
    db.commit()

    for mgr in db.query(models.Manager).all():
        defaults = MANAGER_DEFAULTS.get(mgr.name, {})
        if defaults.get("photo") and not mgr.photo:
            mgr.photo = defaults["photo"]
        if not mgr.position:
            mgr.position = defaults.get("position", _DEFAULT_POSITION)
        if defaults.get("email") and not mgr.email:
            mgr.email = defaults["email"]
    db.commit()

    for mgr in db.query(models.Manager).all():
        key = mgr.name.replace(" ", "_")
        email_val = os.getenv(f"MANAGER_EMAIL_{key}", "").strip().lower()
        if email_val and mgr.email != email_val:
            mgr.email = email_val
        leader_val = os.getenv(f"MANAGER_LEADER_{key}", "").strip().lower()
        if leader_val in ("true", "1", "yes"):
            mgr.is_leader = True
        elif leader_val in ("false", "0", "no"):
            mgr.is_leader = False
    db.commit()


def _seed_users(db):
    admin_phone = os.getenv("ADMIN_PHONE", "")
    admin_name  = os.getenv("ADMIN_NAME", "Администратор")
    if admin_phone and db.query(models.PhoneWhitelist).count() == 0:
        db.add(models.PhoneWhitelist(
            phone=admin_phone, display_name=admin_name, is_admin=True))
        db.commit()

    seed_users_env = os.getenv("SEED_USERS", "")
    if seed_users_env:
        for entry in seed_users_env.split(","):
            parts = entry.strip().split(":")
            if len(parts) >= 2:
                ph, nm = parts[0].strip(), parts[1].strip()
                adm = len(parts) >= 3 and parts[2].strip().lower() == "true"
                if not db.query(models.PhoneWhitelist).filter(
                        models.PhoneWhitelist.phone == ph).first():
                    db.add(models.PhoneWhitelist(
                        phone=ph, display_name=nm, is_admin=adm))
        db.commit()


def _seed_vpk_criteria(db):
    if db.query(models.VpkCriterion).count() > 0:
        return
    for i, name in enumerate(_VPK1):
        db.add(models.VpkCriterion(vpk_type=1, name=name, order=i))
    for i, name in enumerate(_VPK2):
        db.add(models.VpkCriterion(vpk_type=2, name=name, order=i))
    db.commit()
