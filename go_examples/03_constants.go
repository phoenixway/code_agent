// Приклад 03: Константи в Go
// Константи - це змінні, які не можуть змінюватися після оголошення.
// Вони використовуються для значень, які повинні залишатися незмінними протягом виконання програми.
//
// Основні поняття для абсолютних початківців:
// 1. Константа - як коробка з написом "Не відкривати", в якій лежить значення
// 2. Після того, як ми поклали значення в цю коробку, ми не можемо його змінити
// 3. Константи допомагають уникнути помилок, коли значення не повинно змінюватися
// 4. Константи можуть бути числовими, рядковими або булевими

package main

import (
    "fmt"
    "math"
)

func main() {
    fmt.Println("=== ПРИКЛАД 03: КОНСТАНТИ ===")
    fmt.Println("Для абсолютних початківців: константи - це незмінні значення")
    fmt.Println()
    
    // 1. Оголошення констант з явним вказівкам типу
    const pi float64 = 3.141592653589793
    const appName string = "Моя перша програма на Go"
    const isLearning bool = true
    
    fmt.Println("1. Константи з явним типом:")
    fmt.Printf("   Число Пі: %.5f\n", pi)
    fmt.Printf("   Назва програми: %s\n", appName)
    fmt.Printf("   Я вивчаю Go? %t\n", isLearning)
    fmt.Println()
    
    // 2. Оголошення констант без явного вказівки типу (тип визначається автоматично)
    const maxUsers = 1000          // тип int
    const temperature = 36.6       // тип float64
    const greeting = "Привіт!"     // тип string
    
    fmt.Println("2. Константи без явного типу (тип визначається автоматично):")
    fmt.Printf("   Максимальна кількість користувачів: %d\n", maxUsers)
    fmt.Printf("   Нормальна температура тіла: %.1f°C\n", temperature)
    fmt.Printf("   Привітання: %s\n", greeting)
    fmt.Println()
    
    // 3. Константи можуть бути обчислені під час компіляції
    const circleArea = pi * 10 * 10  // площа кола з радіусом 10
    const total = maxUsers * 2      // подвоєна кількість користувачів
    
    fmt.Println("3. Обчислені константи (обчислюються під час компіляції):")
    fmt.Printf("   Площа кола з радіусом 10: %.2f\n", circleArea)
    fmt.Printf("   Подвоєна кількість користувачів: %d\n", total)
    fmt.Println()
    
    // 4. Групування констант
    const (
        monday = 1
        tuesday = 2
        wednesday = 3
        thursday = 4
        friday = 5
        saturday = 6
        sunday = 7
    )
    
    fmt.Println("4. Групування констант (дні тижня):")
    fmt.Printf("   Понеділок: %d, Вівторок: %d, Середа: %d\n", monday, tuesday, wednesday)
    fmt.Println()
    
    // 5. Константи з ітератором iota (спеціальне значення для послідовних констант)
    const (
        red = iota   // 0
        green        // 1
        blue         // 2
        yellow       // 3
    )
    
    const (
        readPermission = 1 << iota  // 1 << 0 = 1
        writePermission             // 1 << 1 = 2
        executePermission           // 1 << 2 = 4
    )
    
    fmt.Println("5. Константи з iota (автоматична нумерація):")
    fmt.Printf("   Кольори: червоний=%d, зелений=%d, синій=%d, жовтий=%d\n", red, green, blue, yellow)
    fmt.Printf("   Права доступу: читання=%d, запис=%d, виконання=%d\n", readPermission, writePermission, executePermission)
    fmt.Println()
    
    // 6. Вбудовані константи в Go
    fmt.Println("6. Вбудовані константи в Go:")
    fmt.Printf("   Число Пі з пакету math: %.15f\n", math.Pi)
    fmt.Printf("   Найбільше int64: %d\n", math.MaxInt64)
    fmt.Printf("   Найменше float64: %e\n", math.SmallestNonzeroFloat64)
    fmt.Println()
    
    // 7. Практичний приклад: конвертація одиниць вимірювання
    const (
        metersInKilometer = 1000
        centimetersInMeter = 100
        hoursInDay = 24
        minutesInHour = 60
        secondsInMinute = 60
    )
    
    distanceInMeters := 5000
    distanceInKilometers := float64(distanceInMeters) / metersInKilometer
    
    fmt.Println("7. Практичний приклад: конвертація одиниць вимірювання")
    fmt.Printf("   %d метрів = %.2f кілометрів\n", distanceInMeters, distanceInKilometers)
    fmt.Printf("   Секунд у добі: %d\n", hoursInDay * minutesInHour * secondsInMinute)
    
    fmt.Println("\n=== ВИСНОВОК ===")
    fmt.Println("Константи корисні для:")
    fmt.Println("1. Зберігання значень, які не повинні змінюватися")
    fmt.Println("2. Покращення читабельності коду (замість \"магічних чисел\")")
    fmt.Println("3. Уникнення помилок при зміні значень")
    fmt.Println("4. Групування пов'язаних значень")
}