// Приклад 00: Базові типи даних в Go
// Цей файл пояснює основні типи даних, доступні в мові Go
// Для абсолютних початківців: тип даних - це те, якого виду інформацію може зберігати змінна

package main

import "fmt"

func main() {
    fmt.Println("Приклад 00: Базові типи даних в Go")
    fmt.Println("====================================")

    // 1. ЦІЛІ ЧИСЛА (Integer types)
    // Цілі числа без знаку (тільки додатні або нуль)
    var unsignedInt uint = 42
    var unsignedInt8 uint8 = 255    // від 0 до 255
    var unsignedInt16 uint16 = 65535 // від 0 до 65535
    var unsignedInt32 uint32 = 4294967295
    var unsignedInt64 uint64 = 18446744073709551615

    // Цілі числа зі знаком (можуть бути від'ємними)
    var signedInt int = -42
    var signedInt8 int8 = -128      // від -128 до 127
    var signedInt16 int16 = -32768  // від -32768 до 32767
    var signedInt32 int32 = -2147483648
    var signedInt64 int64 = -9223372036854775808

    fmt.Println("\n1. Цілі числа:")
    fmt.Printf("   Без знаку: uint = %d, uint8 = %d, uint16 = %d, uint32 = %d, uint64 = %d\n", unsignedInt, unsignedInt8, unsignedInt16, unsignedInt32, unsignedInt64)
    fmt.Printf("   Зі знаком: int = %d, int8 = %d, int16 = %d\n", signedInt, signedInt8, signedInt16)

    // 2. ЧИСЛА З ПЛАВАЮЧОЮ КОМОЮ (Floating-point types)
    // Використовуються для десяткових чисел
    var float32Num float32 = 3.14159
    var float64Num float64 = 3.141592653589793

    fmt.Println("\n2. Числа з плаваючою комою:")
    fmt.Printf("   float32: %.5f\n", float32Num)
    fmt.Printf("   float64: %.15f\n", float64Num)

    // 3. БУЛЕВИЙ ТИП (Boolean type)
    // Може приймати тільки два значення: true (істина) або false (хибність)
    var isGoFun bool = true
    var isLearning bool = true
    var isEasy bool = false

    fmt.Println("\n3. Булевий тип:")
    fmt.Printf("   Go це весело? %t\n", isGoFun)
    fmt.Printf("   Я вивчаю Go? %t\n", isLearning)
    fmt.Printf("   Go легкий? %t\n", isEasy)

    // 4. РЯДКИ (Strings)
    // Рядки - це послідовності символів
    var greeting string = "Привіт, світ!"
    var name string = "Олексій"
    var emptyString string = "" // порожній рядок

    fmt.Println("\n4. Рядки:")
    fmt.Printf("   Привітання: %s\n", greeting)
    fmt.Printf("   Ім'я: %s\n", name)
    fmt.Printf("   Порожній рядок: '%s' (довжина: %d)\n", emptyString, len(emptyString))

    // 5. БАЙТИ ТА РУНИ (Bytes and Runes)
    // byte - це псевдонім для uint8, використовується для бінарних даних
    // rune - це псевдонім для int32, використовується для символів Unicode
    var singleByte byte = 'A' // ASCII символ
    var singleRune rune = 'Я' // Unicode символ
    // var unicodeHeart rune = '❤️' // емодзі - може викликати помилку в деяких середовищах

    fmt.Println("\n5. Байти та руни:")
    fmt.Printf("   Байт: %c (код: %d)\n", singleByte, singleByte)
    fmt.Printf("   Руна: %c (код: %d)\n", singleRune, singleRune)

    // 6. КОМПЛЕКСНІ ЧИСЛА (Complex numbers)
    // Використовуються в математиці та інженерії
    var complexNum complex64 = 3 + 4i
    var complexNum128 complex128 = 1.5 + 2.7i

    fmt.Println("\n6. Комплексні числа:")
    fmt.Printf("   complex64: %v\n", complexNum)
    fmt.Printf("   complex128: %v\n", complexNum128)

    // 7. НУЛЬОВІ ЗНАЧЕННЯ (Zero values)
    // Кожен тип має нульове значення, яке присвоюється за замовчуванням
    var defaultInt int          // 0
    var defaultFloat float64    // 0.0
    var defaultBool bool        // false
    var defaultString string    // "" (порожній рядок)
    var defaultComplex complex128 // (0+0i)

    fmt.Println("\n7. Нульові значення (за замовчуванням):")
    fmt.Printf("   int: %d\n", defaultInt)
    fmt.Printf("   float64: %.1f\n", defaultFloat)
    fmt.Printf("   bool: %t\n", defaultBool)
    fmt.Printf("   string: '%s'\n", defaultString)
    fmt.Printf("   complex128: %v\n", defaultComplex)

    fmt.Println("\n=== ВИСНОВОК ===")
    fmt.Println("Go має строгу типізацію - кожна змінна має певний тип.")
    fmt.Println("Основні типи: цілі числа, числа з плаваючою комою, булеві, рядки.")
    fmt.Println("Кожен тип має нульове значення, яке присвоюється за замовчуванням.")
}