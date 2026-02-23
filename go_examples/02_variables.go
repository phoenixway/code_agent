// Приклад 02: Змінні та типи даних
// Цей файл показує різні способи оголошення змінних та основні типи даних в Go
// Для абсолютних початківців: змінна - це іменована область пам'яті, де зберігаються дані

package main

import "fmt"

func main() {
    fmt.Println("=== ПРИКЛАД 02: ЗМІННІ ТА ТИПИ ДАНИХ ===")
    fmt.Println("Для абсолютних початківців: цей приклад показує основи роботи зі змінними")
    fmt.Println()
    
    // 1. ОГОЛОШЕННЯ ЗМІННИХ
    // В Go існують декілька способів оголошення змінних
    
    // Спосіб 1: Оголошення з вказівкою типу
    var name string = "Андрій"
    var age int = 25
    var height float64 = 1.75
    var isStudent bool = true
    
    fmt.Println("1. Оголошення з вказівкою типу:")
    fmt.Printf("   Ім'я: %s, Вік: %d, Зріст: %.2f, Студент: %v\n", name, age, height, isStudent)
    
    // Спосіб 2: Оголошення без вказівки типу (компілятор сам визначає тип)
    var city = "Київ"      // тип string
    var population = 2800000 // тип int
    var temperature = 22.5   // тип float64
    
    fmt.Println("\n2. Оголошення без вказівки типу:")
    fmt.Printf("   Місто: %s, Населення: %d, Температура: %.1f\n", city, population, temperature)
    
    // Спосіб 3: Коротке оголошення за допомогою :=
    // Працює тільки всередині функцій
    country := "Україна"
    year := 2024
    pi := 3.14159
    
    fmt.Println("\n3. Коротке оголошення (:=):")
    fmt.Printf("   Країна: %s, Рік: %d, Число Пі: %.5f\n", country, year, pi)
    
    // 2. ОСНОВНІ ТИПИ ДАНИХ
    fmt.Println("\n4. Основні типи даних:")
    
    // Цілі числа
    var smallNumber int8 = 127          // від -128 до 127
    var normalNumber int = 1000         // залежить від архітектури (32 або 64 біти)
    var bigNumber int64 = 9223372036854775807
    
    // Числа з плаваючою комою
    var smallFloat float32 = 3.14159
    var bigFloat float64 = 3.141592653589793
    
    // Булевий тип
    var isTrue bool = true
    var isFalse bool = false
    
    // Рядки
    var greeting string = "Привіт, світ!"
    var emptyString string = "" // порожній рядок
    
    fmt.Printf("   Цілі числа: int8=%d, int=%d, int64=%d\n", smallNumber, normalNumber, bigNumber)
    fmt.Printf("   Дробові числа: float32=%.5f, float64=%.15f\n", smallFloat, bigFloat)
    fmt.Printf("   Булеві значення: %t, %t\n", isTrue, isFalse)
    fmt.Printf("   Рядки: \"%s\", порожній: \"%s\"\n", greeting, emptyString)
    
    // 3. НУЛЬОВІ ЗНАЧЕННЯ
    // Кожен тип має нульове значення, яке присвоюється за замовчуванням
    var defaultInt int          // 0
    var defaultFloat float64    // 0.0
    var defaultBool bool        // false
    var defaultString string    // "" (порожній рядок)
    
    fmt.Println("\n5. Нульові значення (значення за замовчуванням):")
    fmt.Printf("   int: %d, float64: %.1f, bool: %t, string: \"%s\"\n", 
        defaultInt, defaultFloat, defaultBool, defaultString)
    
    // 4. КОНВЕРСІЯ ТИПІВ
    fmt.Println("\n6. Конверсія типів (перетворення одного типу в інший):")
    
    var integerNumber int = 42
    var floatNumber float64 = float64(integerNumber) // конвертація int в float64
    var stringNumber string = fmt.Sprintf("%d", integerNumber) // конвертація int в string
    
    fmt.Printf("   Оригінал: %d (тип int)\n", integerNumber)
    fmt.Printf("   У float64: %.1f\n", floatNumber)
    fmt.Printf("   У string: \"%s\"\n", stringNumber)
    
    fmt.Println("\n=== ПОРАДИ ДЛЯ ПОЧАТКІВЦІВ ===")
    fmt.Println("1. Використовуйте коротке оголошення (:=) всередині функцій")
    fmt.Println("2. Для глобальних змінних використовуйте var")
    fmt.Println("3. Надавайте змінним зрозумілі імена (наприклад, userName, itemCount)")
    fmt.Println("4. Go - мова зі статичною типізацією: тип змінної не можна змінити після оголошення")
    fmt.Println("5. Компілятор Go часто сам визначає тип, тому не завжди потрібно вказувати його явно")
}