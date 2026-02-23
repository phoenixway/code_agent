// Приклад 09: Методи в Go

package main

import "fmt"

// Структура для демонстрації методів
type Rectangle struct {
	width  float64
	height float64
}

// Метод з отримувачем значення (value receiver)
// Цей метод працює з копією структури
func (r Rectangle) Area() float64 {
	return r.width * r.height
}

// Метод з отримувачем вказівника (pointer receiver)
// Цей метод може змінювати оригінальну структуру
func (r *Rectangle) Scale(factor float64) {
	r.width *= factor
	r.height *= factor
}

// Метод для рядкового представлення
func (r Rectangle) String() string {
	return fmt.Sprintf("Прямокутник: ширина=%.2f, висота=%.2f, площа=%.2f", r.width, r.height, r.Area())
}

func main() {
	// Створюємо прямокутник
	rect := Rectangle{width: 10, height: 5}
	
	// Викликаємо метод Area() (value receiver)
	area := rect.Area()
	fmt.Printf("Площа прямокутника: %.2f\n", area)
	
	// Викликаємо метод Scale() (pointer receiver)
	// Зверніть увагу: Go автоматично перетворює значення на вказівник при виклику методу
	rect.Scale(2)
	fmt.Printf("Після масштабування: ширина=%.2f, висота=%.2f\n", rect.width, rect.height)
	
	// Викликаємо метод String()
	fmt.Println(rect)
	
	// Демонстрація різниці між value та pointer receivers
	rect2 := Rectangle{width: 3, height: 4}
	rect2Copy := rect2 // Копіюємо
	
	// Value receiver не змінює оригінал
	rect2.Area() // Просто обчислює площу
	fmt.Printf("rect2 після Area(): %v\n", rect2)
	
	// Pointer receiver змінює оригінал
	rect2Copy.Scale(1.5)
	fmt.Printf("rect2Copy після Scale(): %v\n", rect2Copy)
	
	// Методи можна викликати і на вказівниках
	ptr := &Rectangle{width: 7, height: 8}
	fmt.Printf("Площа через вказівник: %.2f\n", ptr.Area())
	
	// Важливе правило:
	// - Використовуйте pointer receivers, коли метод має змінювати структуру
	// - Використовуйте value receivers, коли метод тільки читає дані
	// - Для консистентності: якщо один метод має pointer receiver, всі методи цього типу повинні мати pointer receivers
}

// Додаткові приклади:

type Circle struct {
	radius float64
}

// Метод для обчислення площі кола
func (c Circle) Area() float64 {
	return 3.14159 * c.radius * c.radius
}

// Метод для зміни радіуса (pointer receiver)
func (c *Circle) SetRadius(r float64) {
	c.radius = r
}

// Методи можуть повертати будь-які типи
func (c Circle) Diameter() float64 {
	return 2 * c.radius
}

// Методи можуть приймати параметри
func (c Circle) IsLargerThan(other Circle) bool {
	return c.Area() > other.Area()
}