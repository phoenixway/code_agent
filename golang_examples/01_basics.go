// Основні концепції Go для початківців
// Цей файл демонструє базовий синтаксис, оголошення змінних та типи даних

package main

import "fmt"

func main() {
    // 1. Оголошення змінних
    // Go має кілька способів оголошення змінних
    
    // Спосіб 1: з явним вказівкам типу
    var name string = "Анна"
    var age int = 25
    var height float64 = 1.75
    var isStudent bool = true
    
    fmt.Println("=== Оголошення змінних ===")
    fmt.Printf("Ім'я: %s, Вік: %d, Зріст: %.2f, Студент: %v\n", name, age, height, isStudent)
    
    // Спосіб 2: тип визначається автоматично (type inference)
    var city = "Київ"        // string
    var population = 2800000 // int
    var temperature = 22.5   // float64
    
    fmt.Printf("Місто: %s, Населення: %d, Температура: %.1f\n", city, population, temperature)
    
    // Спосіб 3: коротке оголошення (тільки всередині функцій)
    country := "Україна"
    year := 2024
    pi := 3.14159
    
    fmt.Printf("Країна: %s, Рік: %d, Число Пі: %.5f\n", country, year, pi)
    
    // 2. Константи
    const gravity = 9.81
    const daysInWeek = 7
    const appName = "Go Приклади"
    
    fmt.Println("\n=== Константи ===")
    fmt.Printf("Гравітація: %.2f, Днів у тижні: %d, Назва: %s\n", gravity, daysInWeek, appName)
    
    // 3. Основні типи даних
    fmt.Println("\n=== Типи даних ===")
    
    // Цілі числа
    var int8Example int8 = 127        // від -128 до 127
    var int16Example int16 = 32767    // від -32768 до 32767
    var int32Example int32 = 2147483647
    var int64Example int64 = 9223372036854775807
    var uintExample uint = 255        // беззнакове ціле
    
    fmt.Printf("int8: %d, int16: %d, int32: %d, int64: %d, uint: %d\n", 
        int8Example, int16Example, int32Example, int64Example, uintExample)
    
    // Дійсні числа
    var float32Example float32 = 3.1415927
    var float64Example float64 = 3.141592653589793
    
    fmt.Printf("float32: %.7f, float64: %.15f\n", float32Example, float64Example)
    
    // Комплексні числа
    var complexExample complex128 = complex(3, 4) // 3 + 4i
    fmt.Printf("Комплексне число: %v\n", complexExample)
    
    // 4. Рядки
    fmt.Println("\n=== Рядки ===")
    
    greeting := "Привіт, світ!"
    multiLine := `Це багаторядковий
рядок, який може містити
лапки "без екранування"`
    
    fmt.Println(greeting)
    fmt.Println(multiLine)
    
    // Довжина рядка
    fmt.Printf("Довжина рядка 'Привіт': %d\n", len("Привіт"))
    
    // Конкатенація
    firstName := "Іван"
    lastName := "Петров"
    fullName := firstName + " " + lastName
    fmt.Printf("Повне ім'я: %s\n", fullName)
    
    // 5. Нульові значення (zero values)
    fmt.Println("\n=== Нульові значення ===")
    
    var zeroInt int
    var zeroFloat float64
    var zeroString string
    var zeroBool bool
    
    fmt.Printf("int: %d, float64: %.1f, string: '%s', bool: %v\n", 
        zeroInt, zeroFloat, zeroString, zeroBool)
    
    // 6. Конвертація типів
    fmt.Println("\n=== Конвертація типів ===")
    
    var a int = 42
    var b float64 = float64(a) // Конвертація int -> float64
    var c int = int(b)         // Конвертація float64 -> int (втрачається дробова частина)
    
    fmt.Printf("a (int): %d, b (float64): %.1f, c (int): %d\n", a, b, c)
    
    // Конвертація рядка
    strNumber := "123"
    // Для конвертації рядка в число використовуємо strconv пакет
    // (це буде показано в іншому прикладі)
    
    fmt.Println("\n=== Висновок ===")
    fmt.Println("1. Go - статично типізована мова")
    fmt.Println("2. Змінні можна оголошувати кількома способами")
    fmt.Println("3. Кожен тип має нульове значення")
    fmt.Println("4. Конвертація типів вимагає явного перетворення")
}