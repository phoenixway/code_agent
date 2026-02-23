// Файл: 04_functions.go
// Приклади функцій у Go для початківців
// Функції - це блоки коду, які виконують певну задачу і можуть бути викликані багаторазово

package main

import (
	"fmt"
	"strings"
)

func main() {
	fmt.Println("=== Приклади функцій у Go ===")
	
	// 1. Проста функція без параметрів та повернення значення
	fmt.Println("\n1. Проста функція без параметрів:")
	sayHello()
	
	// 2. Функція з одним параметром
	fmt.Println("\n2. Функція з одним параметром:")
	greetPerson("Олександр")
	
	// 3. Функція з декількома параметрами
	fmt.Println("\n3. Функція з декількома параметрами:")
	sum := addNumbers(5, 3)
	fmt.Printf("5 + 3 = %d\n", sum)
	
	// 4. Функція, що повертає декілька значень
	fmt.Println("\n4. Функція, що повертає декілька значень:")
	quotient, remainder := divide(10, 3)
	fmt.Printf("10 / 3 = %d (остача: %d)\n", quotient, remainder)
	
	// 5. Функція з іменованими поверненнями значеннями
	fmt.Println("\n5. Функція з іменованими поверненнями значеннями:")
	area := calculateRectangleArea(4, 5)
	fmt.Printf("Площа прямокутника 4x5 = %.2f\n", area)
	
	// 6. Функція з варіативним параметром (змінна кількість аргументів)
	fmt.Println("\n6. Функція з варіативним параметром:")
	total := sumAll(1, 2, 3, 4, 5)
	fmt.Printf("Сума чисел 1,2,3,4,5 = %d\n", total)
	
	// 7. Рекурсивна функція (функція, що викликає сама себе)
	fmt.Println("\n7. Рекурсивна функція (факторіал):")
	factorial5 := factorial(5)
	fmt.Printf("Факторіал 5 = %d\n", factorial5)
	
	// 8. Анонімна функція (функція без імені)
	fmt.Println("\n8. Анонімна функція:")
	double := func(x int) int {
		return x * 2
	}
	fmt.Printf("Подвоєння числа 7: %d\n", double(7))
	
	// 9. Функція як значення (функції - це first-class citizens у Go)
	fmt.Println("\n9. Функція як значення:")
	operation := addNumbers // присвоюємо функцію змінній
	result := operation(10, 20)
	fmt.Printf("10 + 20 = %d\n", result)
	
	// 10. Замикання (closure) - функція, що запам'ятовує змінні з навколишнього контексту
	fmt.Println("\n10. Замикання (closure):")
	counter := createCounter()
	fmt.Printf("Лічильник: %d\n", counter())
	fmt.Printf("Лічильник: %d\n", counter())
	fmt.Printf("Лічильник: %d\n", counter())
}

// 1. Проста функція без параметрів та повернення значення
func sayHello() {
	fmt.Println("Привіт, світ!")
}

// 2. Функція з одним параметром
func greetPerson(name string) {
	fmt.Printf("Привіт, %s!\n", name)
}

// 3. Функція з декількома параметрами
func addNumbers(a int, b int) int {
	return a + b
}

// 4. Функція, що повертає декілька значень
func divide(dividend int, divisor int) (int, int) {
	quotient := dividend / divisor
	remainder := dividend % divisor
	return quotient, remainder
}

// 5. Функція з іменованими поверненнями значеннями
// Імена змінних оголошуються в сигнатурі функції
func calculateRectangleArea(width float64, height float64) (area float64) {
	area = width * height
	return // повертаємо area без явного вказання
}

// 6. Функція з варіативним параметром
// ...int означає, що функція приймає нуль або більше цілих чисел
func sumAll(numbers ...int) int {
	total := 0
	for _, num := range numbers {
		total += num
	}
	return total
}

// 7. Рекурсивна функція
func factorial(n int) int {
	if n <= 1 {
		return 1
	}
	return n * factorial(n-1)
}

// 10. Функція, що створює замикання
func createCounter() func() int {
	count := 0
	return func() int {
		count++
		return count
	}
}

// Додатковий приклад: функція з різними типами параметрів
func processText(text string, times int) string {
	return strings.Repeat(text, times)
}

// Примітка: У Go немає підтримки параметрів за замовчуванням та перевантаження функцій
// Кожна функція має унікальне ім'я в межах пакету