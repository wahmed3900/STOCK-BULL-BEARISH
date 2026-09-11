from database import watchlist, alerts
from datetime import datetime
import random

def check_alerts():
    user_watchlist = watchlist.find()

    for entry in user_watchlist:
        user_id = entry["user_id"]
        for symbol in entry["symbols"]:

            # Fake alert logic (replace with real stock API)
            price_change = random.uniform(-5, 5)

            if abs(price_change) >= 3:
                alerts.insert_one({
                    "user_id": user_id,
                    "symbol": symbol,
                    "type": "price_spike",
                    "message": f"{symbol} moved {price_change:.2f}%",
                    "timestamp": datetime.utcnow()
                })
