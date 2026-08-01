def is_subscriber(required_tier):
    user = users.find_one({"id": 1})
    tiers = ["free", "starter", "pro"]
    return tiers.index(user["subscription"]) >= tiers.index(required_tier)
