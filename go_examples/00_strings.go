// Приклад 00: Робота з рядками в Go
// Рядки (строки) - це один з найбільш використовуваних типів даних в програмуванні.
// У Go рядок представлений типом string.

package main

import (
    "fmt"
    "strings"
    "strconv"
)

func main() {
    fmt.Println("=== ПРИКЛАД 00: РОБОТА З РЯДКАМИ ===")
    fmt.Println("Для абсолютних початківців: цей приклад показує основні операції з текстом")
    fmt.Println()
    
    // 1. ОСНОВИ РЯДКІВ
    fmt.Println("1. ОСНОВИ РЯДКІВ:")
    
    // Створення рядків
    greeting := "Привіт, світ!"
    name := "Олексій"
    emptyString := "" // порожній рядок
    
    fmt.Printf("   Привітання: %s\n", greeting)
    fmt.Printf("   Ім'я: %s\n", name)
    fmt.Printf("   Порожній рядок: '%s' (довжина: %d)\n", emptyString, len(emptyString))
    
    // Конкатенація (об'єднання) рядків
    fullGreeting := greeting + " Мене звати " + name
    fmt.Printf("   Об'єднаний рядок: %s\n", fullGreeting)
    
    // 2. ОПЕРАЦІЇ З РЯДКАМИ
    fmt.Println("\n2. ОПЕРАЦІЇ З РЯДКАМИ:")
    
    // Довжина рядка
    text := "Програмування на Go"
    length := len(text)
    fmt.Printf("   Рядок: '%s'\n", text)
    fmt.Printf("   Довжина (в байтах): %d\n", length)
    
    // Доступ до символів (індексація)
    firstChar := text[0] // перший символ
    fmt.Printf("   Перший символ: %c (код: %d)\n", firstChar, firstChar)
    
    // Зрізи рядків (substring)
    substring := text[0:11] // символи з 0 по 10
    fmt.Printf("   Зріз [0:11]: '%s'\n", substring)
    
    // 3. ФУНКЦІЇ З ПАКЕТУ STRINGS
    fmt.Println("\n3. ФУНКЦІЇ З ПАКЕТУ STRINGS:")
    
    // Перетворення регістру
    upper := strings.ToUpper(text)
    lower := strings.ToLower(text)
    fmt.Printf("   Верхній регістр: %s\n", upper)
    fmt.Printf("   Нижній регістр: %s\n", lower)
    
    // Заміна частини рядка
    replaced := strings.Replace(text, "Go", "Golang", 1)
    fmt.Printf("   Після заміни: %s\n", replaced)
    
    // Розділення рядка
    csv := "яблуко,банан,апельсин"
    fruits := strings.Split(csv, ",")
    fmt.Printf("   Розділений рядок: %v\n", fruits)
    fmt.Printf("   Перший фрукт: %s\n", fruits[0])
    
    // Пошук підрядка
    contains := strings.Contains(text, "програмування")
    index := strings.Index(text, "Go")
    fmt.Printf("   Містить 'програмування'? %t\n", contains)
    fmt.Printf("   Індекс 'Go': %d\n", index)
    
    // Обрізання пробілів
    spacedText := "   текст з пробілами   "
    trimmed := strings.TrimSpace(spacedText)
    fmt.Printf("   До обрізання: '%s'\n", spacedText)
    fmt.Printf("   Після обрізання: '%s'\n", trimmed)
    
    // 4. ПЕРЕТВОРЕННЯ ТИПІВ
    fmt.Println("\n4. ПЕРЕТВОРЕННЯ ТИПІВ:")
    
    // Число в рядок
    number := 42
    numberStr := strconv.Itoa(number) // Integer to ASCII
    fmt.Printf("   Число %d як рядок: '%s'\n", number, numberStr)
    
    // Рядок в число
    strNumber := "123"
    parsedNumber, err := strconv.Atoi(strNumber)
    if err == nil {
        fmt.Printf("   Рядок '%s' як число: %d\n", strNumber, parsedNumber)
    }
    
    // 5. БАГАТОРЯДКОВІ РЯДКИ
    fmt.Println("\n5. БАГАТОРЯДКОВІ РЯДКИ:")
    
    multiLine := `Це багаторядковий
рядок в Go.
Він зберігає всі переходи на новий рядок
та не потребує спеціальних символів.`
    
    fmt.Println("   Багаторядковий рядок:")
    fmt.Println(multiLine)
    
    // 6. ФОРМАТУВАННЯ РЯДКІВ
    fmt.Println("\n6. ФОРМАТУВАННЯ РЯДКІВ:")
    
    age := 25
    height := 1.75
    formatted := fmt.Sprintf("Вік: %d років, Зріст: %.2f метра", age, height)
    fmt.Printf("   Форматований рядок: %s\n", formatted)
    
    fmt.Println("\n=== ВИСНОВОК ===")
    fmt.Println("Рядки в Go - це потужний інструмент для роботи з текстом.")
    fmt.Println("Основні операції: конкатенація, зрізи, пошук, заміна.")
    fmt.Println("Пакети strings та strconv надають додаткові функції.")
}