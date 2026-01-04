# modules/healer.py
class HealerModule:
    @staticmethod
    def generate_healing_prompt(file_path, error, content):
        return f"Patch failed for {file_path}.\nError: {error}\nCurrent file state:\n{content}\nPlease provide a correct JSON patch."
