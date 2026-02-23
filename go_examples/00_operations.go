// Приклад 00: Операції в Go
// Цей файл пояснює основні операції, які використовуються зі змінними та константами
// Для абсолютних початківців: операції - це дії, які ми виконуємо над даними

package main

import "fmt"

func main() {
    fmt.Println("=== ПРИКЛАД 00: ОПЕРАЦІЇ В GO ===")
    fmt.Println("Для абсолютних початківців: цей приклад показує основні операції")
    fmt.Println()
    
    // 1. АРИФМЕТИЧНІ ОПЕРАЦІЇ (Arithmetic operations)
    // Використовуються для математичних обчислень
    fmt.Println("1. АРИФМЕТИЧНІ ОПЕРАЦІЇ:")
    
    a := 10
    b := 3
    
    fmt.Printf("   a = %d, b = %d\n", a, b)
    fmt.Printf("   Додавання (a + b): %d + %d = %d\n", a, b, a + b)
    fmt.Printf("   Віднімання (a - b): %d - %d = %d\n", a, b, a - b)
    fmt.Printf("   Множення (a * b): %d * %d = %d\n", a, b, a * b)
    fmt.Printf("   Ділення (a / b): %d / %d = %d (цілочисельне ділення)\n", a, b, a / b)
    fmt.Printf("   Остача від ділення (a %% b): %d %% %d = %d\n", a, b, a % b)
    
    // Ділення з плаваючою комою
    c := 10.0
    d := 3.0
    fmt.Printf("   Ділення з плаваючою комою (c / d): %.1f / %.1f = %.2f\n", c, d, c / d)
    
    // Інкремент та декремент
    x := 5
    x++ // збільшення на 1 (тепер x = 6)
    x-- // зменшення на 1 (тепер x = 5 знову)
    fmt.Printf("   Інкремент (x++): збільшує значення на 1\n")
    fmt.Printf("   Декремент (x--): зменшує значення на 1\n")
    
    // 2. ОПЕРАЦІЇ ПОРІВНЯННЯ (Comparison operations)
    // Порівнюють два значення та повертають true або false
    fmt.Println("\n2. ОПЕРАЦІЇ ПОРІВНЯННЯ (повертають true/false):")
    
    fmt.Printf("   a == b (рівність): %d == %d = %t\n", a, b, a == b)
    fmt.Printf("   a != b (нерівність): %d != %d = %t\n", a, b, a != b)
    fmt.Printf("   a > b (більше): %d > %d = %t\n", a, b, a > b)
    fmt.Printf("   a < b (менше): %d < %d = %t\n", a, b, a < b)
    fmt.Printf("   a >= b (більше або дорівнює): %d >= %d = %t\n", a, b, a >= b)
    fmt.Printf("   a <= b (менше або дорівнює): %d <= %d = %t\n", a, b, a <= b)
    
    // 3. ЛОГІЧНІ ОПЕРАЦІЇ (Logical operations)
    // Використовуються з булевими значеннями (true/false)
    fmt.Println("\n3. ЛОГІЧНІ ОПЕРАЦІЇ (працюють з true/false):")
    
    isSunny := true
    isWarm := false
    
    fmt.Printf("   isSunny = %t, isWarm = %t\n", isSunny, isWarm)
    fmt.Printf("   Логічне І (AND): isSunny && isWarm = %t\n", isSunny && isWarm)
    fmt.Printf("   Логічне АБО (OR): isSunny || isWarm = %t\n", isSunny || isWarm)
    fmt.Printf("   Логічне НЕ (NOT): !isSunny = %t\n", !isSunny)
    
    // Практичний приклад
    age := 18
    hasLicense := true
    canDrive := age >= 18 && hasLicense
    fmt.Printf("\n   Практичний приклад:\n")
    fmt.Printf("   Вік: %d, Має права: %t\n", age, hasLicense)
    fmt.Printf("   Може керувати авто (вік >= 18 І має права): %t\n", canDrive)
    
    // 4. ПОБІТОВІ ОПЕРАЦІЇ (Bitwise operations)
    // Працюють з бітами чисел (для просунутих користувачів)
    fmt.Println("\n4. ПОБІТОВІ ОПЕРАЦІЇ (для ознайомлення):")
    
    m := 5  // 0101 в двійковій системі
    n := 3  // 0011 в двійковій системі
    
    fmt.Printf("   m = %d (0101), n = %d (0011)\n", m, n)
    fmt.Printf("   Побітове І (AND): m & n = %d (0101 & 0011 = 0001)\n", m & n)
    fmt.Printf("   Побітове АБО (OR): m | n = %d (0101 | 0011 = 0111)\n", m | n)
    fmt.Printf("   Побітове виключне АБО (XOR): m ^ n = %d (0101 ^ 0011 = 0110)\n", m ^ n)
    fmt.Printf("   Побітовий зсув вліво: m << 1 = %d (0101 << 1 = 1010)\n", m << 1)
    fmt.Printf("   Побітовий зсув вправо: m >> 1 = %d (0101 >> 1 = 0010)\n", m >> 1)
    
    // 5. ОПЕРАЦІЇ ПРИСВОЄННЯ (Assignment operations)
    fmt.Println("\n5. ОПЕРАЦІЇ ПРИСВОЄННЯ:")
    
    value := 10
    fmt.Printf("   Початкове значення: value = %d\n", value)
    
    value += 5  // еквівалентно value = value + 5
    fmt.Printf("   Після value += 5: value = %d\n", value)
    
    value -= 3  // еквівалентно value = value - 3
    fmt.Printf("   Після value -= 3: value = %d\n", value)
    
    value *= 2  // еквівалентно value = value * 2
    fmt.Printf("   Після value *= 2: value = %d\n", value)
    
    value /= 4  // еквівалентно value = value / 4
    fmt.Printf("   Після value /= 4: value = %d\n", value)
    
    // 6. ОПЕРАТОРИ ПРОСТОРУ ІМЕН (для ознайомлення)
    fmt.Println("\n6. ІНШІ ОПЕРАТОРИ (для ознайомлення):")
    fmt.Println("   - Оператор адреси (&): отримує адресу пам'яті змінної")
    fmt.Println("   - Оператор розіменування (*): отримує значення за адресою")
    fmt.Println("   - Оператор отримання довжини (len): довжина масиву, зрізу, рядка")
    fmt.Println("   - Оператор отримання ємності (cap): ємність зрізу")
    
    fmt.Println("\n=== ВИСНОВОК ===")
    fmt.Println("Операції в Go подібні до математичних операцій, але мають свої особливості.")
    fmt.Println("Найважливіші для початківців: арифметичні, порівняння та логічні операції.")
}