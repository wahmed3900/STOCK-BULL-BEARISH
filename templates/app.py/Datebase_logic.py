from database import users

def get_user(user_id=1):
    return users.find_one({"id": user_id})
