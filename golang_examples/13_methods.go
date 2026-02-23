// Файл: 13_methods.go
// Приклади методів у Go
// Методи - це функції, прив'язані до конкретного типу (зазвичай структури)

package main

import "fmt"

// 1. Оголошення структури
type Rectangle struct {
	Width  float64
	Height float64
}

// 2. Метод для структури Rectangle
// Метод має отримувача (receiver) перед іменем методу
// У цьому випадку отримувач - це значення (value receiver)
func (r Rectangle) Area() float64 {
	return r.Width * r.Height
}

// 3. Метод з отримувачем-вказівником (pointer receiver)
// Дозволяє змінювати оригінальну структуру
func (r *Rectangle) Scale(factor float64) {
	r.Width *= factor
	r.Height *= factor
}

// 4. Метод для обчислення периметра
func (r Rectangle) Perimeter() float64 {
	return 2 * (r.Width + r.Height)
}

// 5. Тип може бути не тільки структурою
// Методи можна оголошувати для будь-якого типу, який визначений у тому ж пакеті
type MyFloat float64

// Метод для типу MyFloat
func (f MyFloat) Abs() float64 {
	if f < 0 {
		return float64(-f)
	}
	return float64(f)
}

func main() {
	// 6. Створення екземпляра структури
	rect := Rectangle{Width: 10, Height: 5}
	
	// 7. Виклик методу Area()
	area := rect.Area()
	fmt.Printf("Площа прямокутника: %.2f\n", area)
	
	// 8. Виклик методу Perimeter()
	perimeter := rect.Perimeter()
	fmt.Printf("Периметр прямокутника: %.2f\n", perimeter)
	
	// 9. Виклик методу з вказівником
	fmt.Printf("До масштабування: ширина=%.2f, висота=%.2f\n", rect.Width, rect.Height)
	rect.Scale(2.0) // Автоматичне перетворення значення на вказівник
	fmt.Printf("Після масштабування: ширина=%.2f, висота=%.2f\n", rect.Width, rect.Height)
	
	// 10. Використання методу для неструктурного типу
	f := MyFloat(-3.14)
	absValue := f.Abs()
	fmt.Printf("Абсолютне значення %.2f: %.2f\n", f, absValue)
	
	// 11. Методи з вказівниками та значеннями
	rect2 := &Rectangle{Width: 3, Height: 4} // rect2 - це вказівник
	// Go автоматично розіменовує вказівник при виклику методу з отримувачем-значенням
	area2 := rect2.Area()
	fmt.Printf("Площа прямокутника через вказівник: %.2f\n", area2)
	
	// 12. Різниця між отримувачами-значеннями та отримувачами-вказівниками
	rect3 := Rectangle{Width: 2, Height: 3}
	rect3Value := rect3  // Копія значення
	rect3Pointer := &rect3 // Вказівник на оригінал
	
	rect3Value.Scale(2) // Не змінить оригінальний rect3 (копія)
	rect3Pointer.Scale(2) // Змінить оригінальний rect3
	
	fmt.Printf("rect3 після масштабування: ширина=%.2f, висота=%.2f\n", rect3.Width, rect3.Height)
}

// Ключові моменти:
// 1. Методи оголошуються з отримувачем (receiver) перед іменем методу
// 2. Отримувач може бути значенням (value receiver) або вказівником (pointer receiver)
// 3. Value receiver працює з копією структури, pointer receiver - з оригіналом
// 4. Go автоматично конвертує між значеннями та вказівниками при виклику методів
// 5. Методи можна оголошувати для будь-якого типу в тому ж пакеті
// 6. Методи з вказівниками дозволяють змінювати оригінальний об'єкт
// 7. Методи зі значеннями безпечніші, але можуть бути менш ефективними для великих структур