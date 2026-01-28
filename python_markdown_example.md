# Складний Markdown з Python кодом

Цей файл демонструє складний Markdown формат з включенням Python коду.

## Розділ 1: Базовий Python код

Ось простий приклад функції на Python:

```python
def greet(name: str) -> str:
    """Повертає привітання."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greet("World"))
```

## Розділ 2: Складніші приклади

### Клас з методами

```python
import math
from typing import List


class Vector:
    """Простий клас для векторних операцій."""
    
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
    
    def magnitude(self) -> float:
        """Обчислює довжину вектора."""
        return math.sqrt(self.x**2 + self.y**2)
    
    def dot(self, other: 'Vector') -> float:
        """Скалярний добуток."""
        return self.x * other.x + self.y * other.y
    
    def __add__(self, other: 'Vector') -> 'Vector':
        """Додавання векторів."""
        return Vector(self.x + other.x, self.y + other.y)
    
    def __repr__(self) -> str:
        return f"Vector({self.x}, {self.y})"


# Використання
v1 = Vector(3, 4)
v2 = Vector(1, 2)
print(f"{v1} + {v2} = {v1 + v2}")
print(f"Magnitude of {v1}: {v1.magnitude():.2f}")
```

## Розділ 3: Таблиці та списки

| Операція | Приклад коду | Результат |
|----------|--------------|-----------|
| Додавання | `v1 + v2` | `Vector(4, 6)` |
| Скалярний добуток | `v1.dot(v2)` | `11` |
| Довжина | `v1.magnitude()` | `5.0` |

### Список функцій, які можна реалізувати:

1. **Нормалізація вектора**
   ```python
   def normalize(self) -> 'Vector':
       mag = self.magnitude()
       if mag == 0:
           return Vector(0, 0)
       return Vector(self.x / mag, self.y / mag)
   ```

2. **Відстань між векторами**
   ```python
   def distance_to(self, other: 'Vector') -> float:
       return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)
   ```

3. **Кут між векторами**
   ```python
   def angle_between(self, other: 'Vector') -> float:
       dot_product = self.dot(other)
       mag_product = self.magnitude() * other.magnitude()
       if mag_product == 0:
           return 0.0
       return math.acos(dot_product / mag_product)
   ```

## Розділ 4: Інтерактивний приклад з умовами

```python
import sys

def process_input(user_input: str) -> str:
    """Обробляє введення користувача."""
    if not user_input:
        return "Порожній ввід"
    
    # Складні перетворення
    words = user_input.split()
    if len(words) > 5:
        return "Забагато слів"
    
    # Генерація результату
    result = " ".join(word.upper() for word in words)
    return f"Результат: {result}"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_str = " ".join(sys.argv[1:])
    else:
        input_str = input("Введіть текст: ")
    
    output = process_input(input_str)
    print(output)
```

## Висновок

Цей файл показує, як можна поєднувати Markdown розмітку з Python кодом для створення документації, навчальних матеріалів або технічних нотаток.

> Примітка: Всі приклади коду є робочими та можуть бути виконані в середовищі Python 3.7+.
