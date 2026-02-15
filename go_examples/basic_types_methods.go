// basic_types_methods.go
// Файл демонструє основні типи, структури та методи в мові Go
// This file demonstrates basic types, structures and methods in Go language

package main

import (
    "fmt"
)

// ============================================
// 1. БАЗОВІ ТИПИ (Basic Types)
// ============================================
// Go має кілька вбудованих базових типів:
// - Цілі числа: int, int8, int16, int32, int64, uint, uint8, uint16, uint32, uint64
// - Числа з плаваючою точкою: float32, float64
// - Комплексні числа: complex64, complex128
// - Логічний тип: bool
// - Рядки: string
// - Байти: byte (псевдонім для uint8)
// - Руни: rune (псевдонім для int32, представляє Unicode код-пойнт)

func demonstrateBasicTypes() {
    fmt.Println("=== Демонстрація базових типів ===")
    
    // Цілі числа
    var age int = 30
    var count uint = 100
    
    // Числа з плаваючою точкою
    var price float64 = 19.99
    
    // Логічний тип
    var isActive bool = true
    
    // Рядки
    var name string = "Іван"
    
    // Байти та руни
    var firstByte byte = 'A' // ASCII код 'A' = 65
    var firstRune rune = 'Я' // Unicode код української літери
    
    fmt.Printf("Вік: %d (тип: %T)\n", age, age)
    fmt.Printf("Кількість: %d (тип: %T)\n", count, count)
    fmt.Printf("Ціна: %.2f (тип: %T)\n", price, price)
    fmt.Printf("Активний: %t (тип: %T)\n", isActive, isActive)
    fmt.Printf("Ім'я: %s (тип: %T)\n", name, name)
    fmt.Printf("Байт: %d (символ: %c) (тип: %T)\n", firstByte, firstByte, firstByte)
    fmt.Printf("Руна: %d (символ: %c) (тип: %T)\n", firstRune, firstRune, firstRune)
}

// ============================================
// 2. СТРУКТУРИ (Structs)
// ============================================
// Структури в Go - це колекції полів. Вони схожі на класи в інших мовах,
// але без успадкування (замість цього використовується композиція).

// Person - структура, що представляє людину
// Кожне поле має назву та тип
// Поля з великої літери - експортовані (доступні з інших пакетів)
// Поля з малої літери - приватні (доступні тільки в поточному пакеті)
type Person struct {
    FirstName string // Публічне поле
    LastName  string // Публічне поле
    age       int    // Приватне поле (починається з малої літери)
    Email     string // Публічне поле
}

// ============================================
// 3. МЕТОДИ З VALUE RECEIVER
// ============================================
// Методи в Go - це функції, прив'язані до певного типу.
// Value receiver отримує КОПІЮ об'єкта, тому зміни всередині методу
// не впливають на оригінальний об'єкт.

// GetFullName - метод з value receiver
// (p Person) - це receiver, вказує що метод належить типу Person
// Value receiver працює з копією об'єкта
func (p Person) GetFullName() string {
    // Ми можемо читати поля структури
    return fmt.Sprintf("%s %s", p.FirstName, p.LastName)
}

// GetAge - метод з value receiver для отримання віку
// Оскільки age - приватне поле, ми можемо отримати його значення
// тільки через метод того ж пакета
func (p Person) GetAge() int {
    return p.age
}

// CelebrateBirthday - метод з value receiver для зміни віку
// УВАГА: Оскільки це value receiver, ми працюємо з КОПІЄЮ об'єкта!
// Зміни не будуть відображені в оригінальному об'єкті
func (p Person) CelebrateBirthday() {
    p.age++ // Це змінює копію, не оригінал!
    fmt.Printf("Всередині CelebrateBirthday (value receiver): вік став %d\n", p.age)
}

// ============================================
// 4. МЕТОДИ З POINTER RECEIVER
// ============================================
// Pointer receiver отримує ПОСИЛАННЯ на об'єкт (вказівник),
// тому зміни всередині методу впливають на оригінальний об'єкт.

// CelebrateBirthdayPtr - метод з pointer receiver
// (*Person) - це pointer receiver, вказує що метод отримує вказівник на Person
// Pointer receiver працює з оригінальним об'єктом
func (p *Person) CelebrateBirthdayPtr() {
    p.age++ // Це змінює оригінальний об'єкт!
    fmt.Printf("Всередині CelebrateBirthdayPtr (pointer receiver): вік став %d\n", p.age)
}

// UpdateEmail - метод з pointer receiver для оновлення email
func (p *Person) UpdateEmail(newEmail string) {
    p.Email = newEmail // Змінюємо оригінальний об'єкт
}

// ============================================
// 5. КОНСТРУКТОРИ (Constructor functions)
// ============================================
// У Go немає спеціального синтаксису для конструкторів, але прийнято
// створювати функції з назвою New<TypeName> або New<TypeName>With<Params>

// NewPerson - конструктор для створення нової Person
// Повертає вказівник на Person для ефективності (щоб уникнути копіювання)
func NewPerson(firstName, lastName string, age int) *Person {
    // Створюємо новий об'єкт Person та повертаємо вказівник на нього
    return &Person{
        FirstName: firstName,
        LastName:  lastName,
        age:       age,
        Email:     fmt.Sprintf("%s.%s@example.com", firstName, lastName),
    }
}

// ============================================
// 6. ДЕМОНСТРАЦІЯ РОБОТИ
// ============================================
func demonstrateStructsAndMethods() {
    fmt.Println("\n=== Демонстрація структур та методів ===")
    
    // Створення об'єкта через конструктор
    person := NewPerson("Марія", "Петренко", 25)
    
    fmt.Printf("Створено особу: %s\n", person.GetFullName())
    fmt.Printf("Вік: %d\n", person.GetAge())
    fmt.Printf("Email: %s\n", person.Email)
    
    // Демонстрація value receiver (копія)
    fmt.Println("\n--- Value receiver (копія) ---")
    fmt.Printf("Початковий вік: %d\n", person.GetAge())
    person.CelebrateBirthday() // Викликаємо метод з value receiver
    fmt.Printf("Вік після CelebrateBirthday: %d (НЕ змінився!)\n", person.GetAge())
    
    // Демонстрація pointer receiver (оригінал)
    fmt.Println("\n--- Pointer receiver (оригінал) ---")
    fmt.Printf("Початковий вік: %d\n", person.GetAge())
    person.CelebrateBirthdayPtr() // Викликаємо метод з pointer receiver
    fmt.Printf("Вік після CelebrateBirthdayPtr: %d (Змінився!)\n", person.GetAge())
    
    // Оновлення email через pointer receiver
    fmt.Println("\n--- Оновлення email ---")
    person.UpdateEmail("maria.petrenko@newdomain.com")
    fmt.Printf("Новий email: %s\n", person.Email)
    
    // Альтернативний спосіб виклику методів з pointer receiver
    fmt.Println("\n--- Альтернативний виклик pointer receiver ---")
    // Go автоматично конвертує value у pointer при виклику методу з pointer receiver
    var person2 Person = Person{FirstName: "Олег", LastName: "Іваненко", age: 30}
    person2.CelebrateBirthdayPtr() // Go автоматично бере адресу: (&person2).CelebrateBirthdayPtr()
    fmt.Printf("Вік person2: %d\n", person2.GetAge())
}

// ============================================
// 7. КОГИ ВИКОРИСТОВУВАТИ VALUE VS POINTER RECEIVER
// ============================================
/*
ВИБІР МІЖ VALUE ТА POINTER RECEIVER:

Value receiver (копія) використовуйте коли:
1. Метод НЕ змінює стан об'єкта
2. Об'єкт малий (невелика структура) і копіювання дешеве
3. Ви хочете гарантувати, що оригінальний об'єкт не зміниться
4. Працюєте з базовими типами або маленькими структурами

Pointer receiver (посилання) використовуйте коли:
1. Метод ЗМІНЮЄ стан об'єкта
2. Об'єкт великий (велика структура) і копіювання дороге
3. Структура містить поля, які не можна копіювати (наприклад, mutex)
4. Ви хочете узгодженості: якщо хоч один метод має pointer receiver,
   то всі методи цього типу повинні мати pointer receiver

ЗАУВАЖЕННЯ: Go автоматично конвертує value у pointer при виклику методу,
тому ви можете викликати метод з pointer receiver на value.
Але НЕ навпаки: не можна викликати метод з value receiver на pointer
без розіменування (*pointer).methodName()
*/

// ============================================
// MAIN ФУНКЦІЯ
// ============================================
func main() {
    fmt.Println("ПРОГРАМА ДЕМОНСТРАЦІЇ ТИПІВ ТА МЕТОДІВ У GO")
    fmt.Println("============================================")
    
    demonstrateBasicTypes()
    demonstrateStructsAndMethods()
    
    fmt.Println("\n=== Висновки ===")
    fmt.Println("1. Value receiver працює з копією об'єкта")
    fmt.Println("2. Pointer receiver працює з оригінальним об'єктом")
    fmt.Println("3. Go автоматично конвертує value→pointer при виклику методів")
    fmt.Println("4. Для зміни стану об'єкта використовуйте pointer receiver")
}
