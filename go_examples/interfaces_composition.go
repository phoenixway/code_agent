// interfaces_composition.go
// Файл демонструє роботу з інтерфейсами та композицією в мові Go
// Інтерфейси в Go - це набір методів, які тип має реалізувати
// Композиція (embedding) дозволяє включати одну структуру в іншу
package main

import (
    "fmt"
    "math"
)

// ============================================
// 1. ОСНОВИ ІНТЕРФЕЙСІВ
// ============================================

// Shape - інтерфейс для геометричних фігур
// Інтерфейс оголошує набір методів, які мають бути реалізовані
// Будь-який тип, що реалізує всі методи інтерфейсу, автоматично задовольняє цей інтерфейс
type Shape interface {
    Area() float64      // Метод для обчислення площі
    Perimeter() float64 // Метод для обчислення периметра
    Name() string       // Метод для отримання назви фігури
}

// Circle - структура, що представляє коло
type Circle struct {
    Radius float64
}

// Реалізація методів інтерфейсу Shape для Circle
// Circle автоматично задовольняє інтерфейс Shape, бо реалізує всі його методи

// Area - обчислює площу кола (π * r²)
func (c Circle) Area() float64 {
    return math.Pi * c.Radius * c.Radius
}

// Perimeter - обчислює довжину кола (2 * π * r)
func (c Circle) Perimeter() float64 {
    return 2 * math.Pi * c.Radius
}

// Name - повертає назву фігури
func (c Circle) Name() string {
    return "Circle"
}

// Rectangle - структура, що представляє прямокутник
type Rectangle struct {
    Width, Height float64
}

// Реалізація методів інтерфейсу Shape для Rectangle

// Area - обчислює площу прямокутника (width * height)
func (r Rectangle) Area() float64 {
    return r.Width * r.Height
}

// Perimeter - обчислює периметр прямокутника (2 * (width + height))
func (r Rectangle) Perimeter() float64 {
    return 2 * (r.Width + r.Height)
}

// Name - повертає назву фігури
func (r Rectangle) Name() string {
    return "Rectangle"
}

// ============================================
// 2. ПУСТИЙ ІНТЕРФЕЙС interface{}
// ============================================

// Пустий інтерфейс interface{} не має жодних методів
// Кожен тип автоматично задовольняє пустий інтерфейс
// Це аналог типу any в інших мовах або void* у C

// PrintAnything - функція, що приймає будь-який тип через пустий інтерфейс
func PrintAnything(value interface{}) {
    fmt.Printf("Type: %T, Value: %v\n", value, value)
}

// ============================================
// 3. КОМПОЗИЦІЯ (EMBEDDING) СТРУКТУР
// ============================================

// Композиція в Go - це спосіб включити одну структуру в іншу
// Це дозволяє повторно використовувати код та створювати ієрархії

// Person - базова структура для особи
type Person struct {
    Name string
    Age  int
}

// Метод для Person
func (p Person) Greet() string {
    return fmt.Sprintf("Hello, I'm %s, %d years old", p.Name, p.Age)
}

// Employee - структура співробітника, яка включає (embed) Person
// Employee має всі поля та методи Person
// Це не успадкування, а композиція
type Employee struct {
    Person    // Вбудована структура Person (композиція)
    Company   string
    Position  string
    Salary    float64
}

// Метод тільки для Employee
func (e Employee) WorkInfo() string {
    return fmt.Sprintf("%s works at %s as %s", e.Name, e.Company, e.Position)
}

// Manager - структура менеджера, яка включає Employee
// Має всі поля та методи Person та Employee
type Manager struct {
    Employee          // Вбудована структура Employee
    Department string
    TeamSize   int
}

// ============================================
// 4. TYPE ASSERTIONS ТА TYPE SWITCHES
// ============================================

// Type assertion - перетворення значення інтерфейсу на конкретний тип
func DescribeShape(s Shape) {
    // Type assertion: перевірка, чи s є Circle
    if circle, ok := s.(Circle); ok {
        fmt.Printf("This is a Circle with radius %.2f\n", circle.Radius)
    } else if rect, ok := s.(Rectangle); ok {
        fmt.Printf("This is a Rectangle %.2fx%.2f\n", rect.Width, rect.Height)
    } else {
        fmt.Println("Unknown shape type")
    }
}

// Type switch - перемикач для різних типів у інтерфейсі
func ProcessValue(v interface{}) {
    switch val := v.(type) {
    case int:
        fmt.Printf("Integer: %d (doubled: %d)\n", val, val*2)
    case string:
        fmt.Printf("String: '%s' (length: %d)\n", val, len(val))
    case Circle:
        fmt.Printf("Circle with area: %.2f\n", val.Area())
    case bool:
        fmt.Printf("Boolean: %v (negated: %v)\n", val, !val)
    default:
        fmt.Printf("Unknown type: %T\n", val)
    }
}

// ============================================
// 5. ІНТЕРФЕЙСИ З МЕТОДАМИ
// ============================================

// Stringer - стандартний інтерфейс з пакету fmt
// Тип, що реалізує String(), може бути виведений fmt.Println
// Це приклад інтерфейсу з одним методом
type Stringer interface {
    String() string
}

// Book - структура книги з реалізацією Stringer
// Реалізація Stringer дозволяє використовувати Book з fmt.Println
type Book struct {
    Title  string
    Author string
    Pages  int
}

// String - реалізація методу інтерфейсу Stringer
func (b Book) String() string {
    return fmt.Sprintf("\"%s\" by %s (%d pages)", b.Title, b.Author, b.Pages)
}

// ============================================
// ОСНОВНА ФУНКЦІЯ
// ============================================

func main() {
    fmt.Println("=== ІНТЕРФЕЙСИ ТА КОМПОЗИЦІЯ В GO ===\n")

    // 1. Демонстрація інтерфейсів
    fmt.Println("1. Робота з інтерфейсом Shape:")
    
    shapes := []Shape{
        Circle{Radius: 5.0},
        Rectangle{Width: 4.0, Height: 6.0},
        Circle{Radius: 2.5},
    }
    
    for _, shape := range shapes {
        fmt.Printf("%s: Area=%.2f, Perimeter=%.2f\n", 
            shape.Name(), shape.Area(), shape.Perimeter())
    }
    
    // 2. Демонстрація пустого інтерфейсу
    fmt.Println("\n2. Пустий інтерфейс interface{}:")
    PrintAnything(42)
    PrintAnything("Hello, Go!")
    PrintAnything(3.14159)
    PrintAnything(Circle{Radius: 10})
    
    // 3. Демонстрація композиції
    fmt.Println("\n3. Композиція структур:")
    
    emp := Employee{
        Person:   Person{Name: "John Doe", Age: 30},
        Company:  "TechCorp",
        Position: "Software Engineer",
        Salary:   75000.0,
    }
    
    mgr := Manager{
        Employee:   emp,
        Department: "Engineering",
        TeamSize:   8,
    }
    
    // Виклик методів з вбудованих структур
    fmt.Println(emp.Greet())      // Метод з Person
    fmt.Println(emp.WorkInfo())   // Метод з Employee
    fmt.Println(mgr.Greet())      // Метод з Person (через Employee)
    fmt.Println(mgr.WorkInfo())   // Метод з Employee
    fmt.Printf("Manager department: %s, team size: %d\n", mgr.Department, mgr.TeamSize)
    
    // 4. Демонстрація type assertions та switches
    fmt.Println("\n4. Type assertions та type switches:")
    
    DescribeShape(Circle{Radius: 7})
    DescribeShape(Rectangle{Width: 3, Height: 4})
    
    ProcessValue(100)
    ProcessValue("Golang")
    ProcessValue(true)
    ProcessValue(Circle{Radius: 3})
    
    // 5. Демонстрація інтерфейсу Stringer
    fmt.Println("\n5. Інтерфейс Stringer:")
    
    book := Book{
        Title:  "The Go Programming Language",
        Author: "Alan A. A. Donovan & Brian W. Kernighan",
        Pages:  380,
    }
    
    // Book автоматично реалізує Stringer через метод String()
    fmt.Println(book) // Викликається book.String() автоматично
    
    fmt.Println("\n=== ПРИКЛАДИ ЗАВЕРШЕНО ===")
}

// ============================================
// КЛЮЧОВІ ВИСНОВКИ:
// ============================================
// 1. Інтерфейси в Go визначають поведінку, а не дані
// 2. Тип автоматично задовольняє інтерфейс, якщо реалізує всі його методи
// 3. Пустий інтерфейс interface{} може містити будь-яке значення
// 4. Композиція (embedding) дозволяє повторно використовувати код
// 5. Type assertions дозволяють отримати конкретний тип з інтерфейсу
// 6. Type switches - зручний спосіб обробки різних типів у інтерфейсі
// 7. Стандартні інтерфейси (як Stringer) дозволяють інтеграцію з бібліотеками