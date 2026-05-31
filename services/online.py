from datetime import datetime

# display_name -> datetime последнего пинга
ONLINE_USERS: dict[str, datetime] = {}
ONLINE_TIMEOUT = 120  # секунд без пинга = оффлайн
