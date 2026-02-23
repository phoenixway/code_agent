// Файл: 11_packages_imports.go
// Приклади роботи з пакетами та імпортами в Go
// Для абсолютних початківців

package main

// Імпорт стандартних пакетів
import (
	"fmt"
	"math"
	"strings"
	"time"
)

// Імпорт з псевдонімом (alias)
import str "strings"

// Імпорт з крапкою (не рекомендується для продакшн коду)
// import . "fmt" // Дозволяє використовувати функції fmt без префіксу

// Імпорт з підкресленням (для side effects, коли нам потрібна лише ініціалізація пакету)
// import _ "database/sql"

func main() {
	fmt.Println("=== Пакети та імпорти в Go ===")
	fmt.Println()

	// 1. Використання стандартних пакетів
	fmt.Println("1. Використання стандартних пакетів:")
	
	// Пакет fmt для форматування та виводу
	fmt.Printf("Число Пі: %.2f\n", math.Pi)
	
	// Пакет strings для роботи з рядками
	greeting := "Привіт, Світ!"
	fmt.Println("Верхній регістр:", strings.ToUpper(greeting))
	fmt.Println("Нижній регістр:", strings.ToLower(greeting))
	fmt.Println("Містить 'Світ':", strings.Contains(greeting, "Світ"))
	
	// Пакет time для роботи з часом
	now := time.Now()
	fmt.Println("Поточний час:", now.Format("2006-01-02 15:04:05"))
	
	// 2. Використання псевдонімів для пакетів
	fmt.Println("\n2. Використання псевдонімів для пакетів:")
	fmt.Println("Рядок з псевдонімом 'str':", str.ToUpper(greeting))
	
	// 3. Створення власних пакетів (приклад структури)
	fmt.Println("\n3. Створення власних пакетів:")
	fmt.Println("Уявімо, що ми маємо власний пакет 'calculator'")
	fmt.Println("Файлова структура могла б виглядати так:")
	fmt.Println("  calculator/")
	fmt.Println("    add.go      - функції додавання")
	fmt.Println("    subtract.go - функції віднімання")
	fmt.Println("    multiply.go - функції множення")
	fmt.Println("    divide.go   - функції ділення")
	fmt.Println("    calculator.go - основний файл пакету")
	
	// 4. Експорт функцій та змінних (Public vs Private)
	fmt.Println("\n4. Експорт функцій та змінних:")
	fmt.Println("У Go експорт визначається першою літерою імені:")
	fmt.Println("  - Велика літера: Public (експортується)")
	fmt.Println("  - Мала літера: Private (не експортується)")
	fmt.Println("Приклад уявного пакету calculator:")
	fmt.Println("  func Add(a, b int) int     // Public - можна імпортувати")
	fmt.Println("  func subtract(a, b int) int // Private - тільки всередині пакету")
	
	// 5. Ініціалізація пакету (init функція)
	fmt.Println("\n5. Ініціалізація пакету:")
	fmt.Println("Кожен пакет може мати функцію init(), яка викликається автоматично.")
	fmt.Println("Вона використовується для ініціалізації глобальних змінних, підключення до БД тощо.")
	fmt.Println("Приклад у файлі calculator.go:")
	fmt.Println("  package calculator")
	fmt.Println("  var Version string")
	fmt.Println("  func init() {")
	fmt.Println("    Version = \"1.0.0\"")
	fmt.Println("    fmt.Println(\"Пакет calculator ініціалізовано\")")
	fmt.Println("  }")
	
	// 6. Відносні та абсолютні імпорти
	fmt.Println("\n6. Відносні та абсолютні імпорти:")
	fmt.Println("  - Абсолютні: import \"github.com/user/project/pkg\"")
	fmt.Println("  - Відносні: import \"./mypackage\" (в межах одного модуля)")
	fmt.Println("  - Відносні: import \"../sibling\" (не рекомендується)")
	
	// 7. Модулі Go (go.mod)
	fmt.Println("\n7. Модулі Go (go.mod):")
	fmt.Println("Сучасні проекти Go використовують модулі для керування залежностями.")
	fmt.Println("Файл go.mod містить:")
	fmt.Println("  - Назву модуля (module github.com/user/project)")
	fmt.Println("  - Версію Go (go 1.21)")
	fmt.Println("  - Залежності (require github.com/lib/pq v1.10.9)")
	
	// Практичний приклад: проста утиліта
	fmt.Println("\n8. Практичний приклад: проста утиліта для форматування тексту")
	text := "  цей текст має зайві пробіли та неправильний регістр  "
	fmt.Println("Оригінальний текст:", text)
	
	// Використовуємо функції з різних пакетів
	trimmed := strings.TrimSpace(text)
	lower := strings.ToLower(trimmed)
	capitalized := strings.Title(lower)
	
	fmt.Println("Після обробки:", capitalized)
	
	fmt.Println("\n=== Кінець прикладів з пакетами та імпортами ===")
}

// Додаткові примітки:
// 1. У Go немає концепції "namespace" як в інших мовах
// 2. Імена пакетів повинні бути короткими та значущими
// 3. Краще мати багато маленьких пакетів, ніж один великий
// 4. Циклічні імпорти заборонені (пакет A імпортує B, а B імпортує A)
// 5. Використовуйте 'go mod tidy' для керування залежностями
// 6. Використовуйте 'go list ./...' для переліку всіх пакетів у проекті