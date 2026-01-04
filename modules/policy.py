# modules/policy.py
class PermissionPolicy:
    def __init__(self, mode="ask"):
        self.mode = mode

    def should_ask(self):
        return self.mode == "ask"
