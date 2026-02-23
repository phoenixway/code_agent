// Файл: 08_interfaces.go
// Приклади роботи з інтерфейсами в Go
// Інтерфейси - це набір методів, які тип повинен реалізувати

package main

import (
	"fmt"
	"math"
)

// ========== ОСНОВИ ІНТЕРФЕЙСІВ ==========

// Оголошення інтерфейсу
type Shape interface {
	Area() float64
	Perimeter() float64
}

// Структура Circle реалізує інтерфейс Shape
type Circle struct {
	Radius float64
}

// Метод Area для Circle
func (c Circle) Area() float64 {
	return math.Pi * c.Radius * c.Radius
}

// Метод Perimeter для Circle
func (c Circle) Perimeter() float64 {
	return 2 * math.Pi * c.Radius
}

// Структура Rectangle реалізує інтерфейс Shape
type Rectangle struct {
	Width, Height float64
}

// Метод Area для Rectangle
func (r Rectangle) Area() float64 {
	return r.Width * r.Height
}

// Метод Perimeter для Rectangle
func (r Rectangle) Perimeter() float64 {
	return 2 * (r.Width + r.Height)
}

// Функція, яка приймає будь-який Shape
func printShapeInfo(s Shape) {
	fmt.Printf("Площа: %.2f, Периметр: %.2f\n", s.Area(), s.Perimeter())
}

// ========== ПУСТИЙ ІНТЕРФЕЙС ==========
// Пустий інтерфейс interface{} може приймати будь-який тип
func describe(i interface{}) {
	fmt.Printf("Тип: %T, Значення: %v\n", i, i)
}

// ========== ПЕРЕВІРКА ТИПУ (TYPE ASSERTION) ==========
func assertExample() {
	var i interface{} = "hello"

	// Перевірка типу
	s, ok := i.(string)
	if ok {
		fmt.Printf("Значення string: %s\n", s)
	}

	// Або коротший запис
	if s, ok := i.(string); ok {
		fmt.Printf("Короткий запис: %s\n", s)
	}

	// Перевірка на інший тип (не вдасться)
	if _, ok := i.(int); !ok {
		fmt.Println("Це не int!")
	}
}

// ========== TYPE SWITCH ==========
func typeSwitchExample(i interface{}) {
	switch v := i.(type) {
	case int:
		fmt.Printf("Це int: %d\n", v)
	case string:
		fmt.Printf("Це string: %s\n", v)
	case bool:
		fmt.Printf("Це bool: %v\n", v)
	default:
		fmt.Printf("Невідомий тип: %T\n", v)
	}
}

// ========== ІНТЕРФЕЙС З МЕТОДАМИ ПОМИЛОК ==========
// Стандартний інтерфейс error
func divide(a, b float64) (float64, error) {
	if b == 0 {
		return 0, fmt.Errorf("ділення на нуль")
	}
	return a / b, nil
}

// ========== ВЛАСНИЙ ІНТЕРФЕЙС ==========
type Speaker interface {
	Speak() string
}

type Dog struct {
	Name string
}

func (d Dog) Speak() string {
	return "Гав! Мене звати " + d.Name
}

type Cat struct {
	Name string
}

func (c Cat) Speak() string {
	return "Мяу! Я " + c.Name
}

func makeSpeak(s Speaker) {
	fmt.Println(s.Speak())
}

func main() {
	fmt.Println("=== ОСНОВИ ІНТЕРФЕЙСІВ ===")
	
	circle := Circle{Radius: 5}
	rectangle := Rectangle{Width: 4, Height: 6}
	
	printShapeInfo(circle)
	printShapeInfo(rectangle)
	
	fmt.Println("\n=== ПУСТИЙ ІНТЕРФЕЙС ===")
	describe(42)
	describe("hello")
	describe(true)
	
	fmt.Println("\n=== ПЕРЕВІРКА ТИПУ ===")
	assertExample()
	
	fmt.Println("\n=== TYPE SWITCH ===")
	typeSwitchExample(123)
	typeSwitchExample("привіт")
	typeSwitchExample(false)
	typeSwitchExample(3.14)
	
	fmt.Println("\n=== ІНТЕРФЕЙС ПОМИЛОК ===")
	result, err := divide(10, 2)
	if err != nil {
		fmt.Println("Помилка:", err)
	} else {
		fmt.Printf("Результат: %.2f\n", result)
	}
	
	_, err = divide(10, 0)
	if err != nil {
		fmt.Println("Помилка:", err)
	}
	
	fmt.Println("\n=== ВЛАСНИЙ ІНТЕРФЕЙС ===")
	dog := Dog{Name: "Рекс"}
	cat := Cat{Name: "Мурка"}
	
	makeSpeak(dog)
	makeSpeak(cat)
	
	// Масив інтерфейсів
	speakers := []Speaker{dog, cat}
	for _, speaker := range speakers {
		makeSpeak(speaker)
	}
}
