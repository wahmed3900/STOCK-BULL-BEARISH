def is_subscriber(required_tier):
    user = get_user()
    tiers = ["free", "starter", "pro"]
    return tiers.index(user["subscription"]) >= tiers.index(required_tier)
